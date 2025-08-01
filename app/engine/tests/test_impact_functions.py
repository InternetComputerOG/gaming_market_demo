import pytest
from decimal import Decimal, getcontext
from typing import Dict, Optional
from typing_extensions import TypedDict

from app.engine.impact_functions import (
    compute_dynamic_params,
    compute_f_i,
    apply_own_impact,
    apply_cross_impacts,
    get_new_prices_after_impact,
    apply_asymptotic_penalty,
)
from app.engine.state import EngineState, BinaryState, init_state, get_binary, update_subsidies, get_p_yes, get_p_no
from app.engine.params import EngineParams
from app.utils import safe_divide, price_value

getcontext().prec = 28

@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 3,
        'z': Decimal('10000.0'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('1666.666666666666666666666667'),
        'f': Decimal('0.01'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'tick_size': Decimal('0.01'),
        'f_match': Decimal('0.005'),
        'sigma': Decimal('0.5'),
        'af_cap_frac': Decimal('0.1'),
        'af_max_pools': 3,
        'af_max_surplus': Decimal('0.05'),
        'cm_enabled': True,
        'af_enabled': True,
        'mr_enabled': False,
        'vc_enabled': True,
        'mu_start': Decimal('1.0'),
        'mu_end': Decimal('2.0'),
        'nu_start': Decimal('1.0'),
        'nu_end': Decimal('1.0'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.002'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.05'),
        'interpolation_mode': 'continue',
        'res_schedule': [],
        'total_duration': 3600,
        'final_winner': 1,
        'res_offsets': [],
        'freeze_durs': [],
        'elim_outcomes': [],
        'starting_balance': Decimal('1000.0'),
        'gas_fee': Decimal('0.0'),
        'batch_interval_ms': 1000,
    }

@pytest.fixture
def initial_state(default_params: EngineParams) -> EngineState:
    return init_state(default_params)

def test_compute_dynamic_params_linear(default_params: EngineParams):
    params = default_params.copy()
    params['total_duration'] = 1000
    current_time = 500
    dyn = compute_dynamic_params(params, current_time)
    assert dyn['mu'] == Decimal('1.5')  # (1.0 + 2.0)/2
    assert dyn['zeta'] == Decimal('0.075')  # 0.1 + 0.5*(0.05-0.1)

def test_compute_dynamic_params_clamp(default_params: EngineParams):
    dyn = compute_dynamic_params(default_params, 0)
    assert dyn['mu'] == Decimal('1.0')
    dyn_end = compute_dynamic_params(default_params, 4000)
    assert dyn_end['mu'] == Decimal('2.0')

def test_compute_dynamic_params_reset_mode(default_params: EngineParams):
    params = default_params.copy()
    params['mr_enabled'] = True
    params['interpolation_mode'] = 'reset'
    params['res_schedule'] = [1, 1]
    # Assume uniform rounds, total_duration / (len(res_schedule)+1)
    per_round_dur = params['total_duration'] // (len(params['res_schedule']) + 1)
    dyn = compute_dynamic_params(params, 600, round_num=1)  # t=600 in round 1, fraction=600/1200=0.5 if 3 rounds
    # But since logic approximates, test mid
    assert dyn['mu'] == Decimal('1.5')

def test_compute_f_i(initial_state: EngineState, default_params: EngineParams):
    zeta = Decimal('0.1')
    f_i = compute_f_i(default_params, zeta, initial_state)
    assert f_i == Decimal('0.8')  # 1 - 2*0.1, N_active=3

def test_compute_f_i_inactive(initial_state: EngineState, default_params: EngineParams):
    state = initial_state.copy()
    state['binaries'][2]['active'] = False
    zeta = Decimal('0.1')
    f_i = compute_f_i(default_params, zeta, state)
    assert f_i == Decimal('0.9')  # N_active=2, 1-1*0.1

def test_apply_own_impact_buy_yes(initial_state: EngineState, default_params: EngineParams):
    state = initial_state.copy()
    binary = get_binary(state, 0)
    initial_v = binary['V']
    initial_l = binary['L']
    X = Decimal('100.0')
    f_i = Decimal('0.8')
    apply_own_impact(state, 0, X, is_buy=True, is_yes=True, f_i=f_i, params=default_params)
    binary = get_binary(state, 0)
    assert binary['V'] == initial_v + f_i * X
    update_subsidies(state, default_params)
    assert binary['subsidy'] == max(Decimal(0), default_params['z'] / Decimal(default_params['n_outcomes']) - default_params['gamma'] * binary['V'])
    assert binary['L'] == binary['V'] + binary['subsidy']

def test_apply_own_impact_sell_no(initial_state: EngineState, default_params: EngineParams):
    state = initial_state.copy()
    binary = get_binary(state, 0)
    initial_v = binary['V']
    X = Decimal('50.0')
    f_i = Decimal('0.8')
    apply_own_impact(state, 0, X, is_buy=False, is_yes=False, f_i=f_i, params=default_params)
    binary = get_binary(state, 0)
    assert binary['V'] == initial_v - f_i * X

def test_apply_cross_impacts_buy(initial_state: EngineState, default_params: EngineParams):
    state = initial_state.copy()
    initial_vs = [b['V'] for b in state['binaries']]
    X = Decimal('100.0')
    zeta = Decimal('0.1')
    apply_cross_impacts(state, 0, X, is_buy=True, zeta=zeta, params=default_params)
    for j in range(1, 3):
        assert state['binaries'][j]['V'] == initial_vs[j] + zeta * X
    assert state['binaries'][0]['V'] == initial_vs[0]  # No self

def test_apply_cross_impacts_sell_inactive(initial_state: EngineState, default_params: EngineParams):
    state = initial_state.copy()
    state['binaries'][2]['active'] = False
    initial_vs = [b['V'] for b in state['binaries']]
    X = Decimal('100.0')
    zeta = Decimal('0.1')
    apply_cross_impacts(state, 0, X, is_buy=False, zeta=zeta, params=default_params)
    assert state['binaries'][1]['V'] == initial_vs[1] - zeta * X
    assert state['binaries'][2]['V'] == initial_vs[2]  # Inactive ignored

def test_get_new_prices_after_impact_buy_yes(initial_state: EngineState, default_params: EngineParams):
    binary = get_binary(initial_state, 0).copy()
    delta = Decimal('100.0')
    X = Decimal('50.0')
    f_i = Decimal('0.8')
    new_p_yes, new_p_no = get_new_prices_after_impact(binary, delta, X, f_i, is_buy=True, is_yes=True)
    eff_delta = delta + binary['virtual_yes']  # But initial 0
    new_l = binary['L'] + f_i * X
    assert new_p_yes == safe_divide(binary['q_yes'] + delta + binary['virtual_yes'], new_l)
    assert new_p_no == safe_divide(binary['q_no'], new_l)

def test_get_new_prices_after_impact_sell_no_virtual(initial_state: EngineState, default_params: EngineParams):
    binary = get_binary(initial_state, 0).copy()
    binary['virtual_yes'] = Decimal('100.0')
    delta = Decimal('50.0')
    X = Decimal('30.0')
    f_i = Decimal('0.8')
    new_p_yes, new_p_no = get_new_prices_after_impact(binary, delta, X, f_i, is_buy=False, is_yes=False)
    new_l = binary['L'] - f_i * X
    assert new_p_yes == safe_divide(binary['q_yes'] + binary['virtual_yes'], new_l)
    assert new_p_no == safe_divide(binary['q_no'] - delta, new_l)

def test_apply_asymptotic_penalty_buy_overflow(default_params: EngineParams):
    X = Decimal('100.0')
    p_prime = Decimal('0.995')
    p_base = Decimal('0.99')  # But p_base not used directly, for buy p_base=p_max
    new_x = apply_asymptotic_penalty(X, p_prime, default_params['p_max'], is_buy=True, params=default_params)
    assert new_x == X * (p_prime / default_params['p_max']) ** default_params['eta']
    assert new_x > X

def test_apply_asymptotic_penalty_sell_underflow(default_params: EngineParams):
    X = Decimal('100.0')
    p_prime = Decimal('0.005')
    new_x = apply_asymptotic_penalty(X, p_prime, default_params['p_min'], is_buy=False, params=default_params)
    assert new_x == X * (default_params['p_min'] / p_prime) ** default_params['eta']
    assert new_x < X

def test_apply_asymptotic_penalty_no_penalty(default_params: EngineParams):
    X = Decimal('100.0')
    p_prime = Decimal('0.5')
    new_x_buy = apply_asymptotic_penalty(X, p_prime, default_params['p_max'], is_buy=True, params=default_params)
    assert new_x_buy == X
    new_x_sell = apply_asymptotic_penalty(X, p_prime, default_params['p_min'], is_buy=False, params=default_params)
    assert new_x_sell == X