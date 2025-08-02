import pytest
from decimal import Decimal
from typing import Dict, List, Tuple

from app.engine.autofill import (
    binary_search_max_delta,
    update_pool_and_get_deltas,
    apply_rebates,
    auto_fill,
    AutoFillEvent,
)
from app.engine.state import EngineState, BinaryState, get_binary, update_subsidies
from app.engine.params import EngineParams
from app.engine.amm_math import buy_cost_yes, sell_received_yes, get_effective_p_yes, get_effective_p_no
from app.engine.impact_functions import compute_f_i
from app.utils import usdc_amount, price_value, validate_size, safe_divide

# Fixtures
@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 3,
        'z': Decimal('10000.0'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('10000.0') / Decimal('3') / Decimal('2'),  # (Z/N)/2 per TDD
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
        'mu_end': Decimal('1.0'),
        'nu_start': Decimal('1.0'),
        'nu_end': Decimal('1.0'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.001'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.1'),
        'interpolation_mode': 'continue',
        'res_schedule': [],
        'total_duration': 3600,
        'final_winner': 1,
        'res_offsets': [],
        'freeze_durs': [],
        'elim_outcomes': [],
        'starting_balance': Decimal('10000.0'),
        'gas_fee': Decimal('0.0'),
        'batch_interval_ms': 1000,
    }

@pytest.fixture
def initial_state(default_params: EngineParams) -> EngineState:
    n_outcomes = default_params['n_outcomes']
    z_per = default_params['z'] / Decimal(n_outcomes)
    q0 = default_params['q0']
    binaries = []
    for i in range(1, n_outcomes + 1):
        binaries.append({
            'outcome_i': i,
            'V': Decimal('0'),
            'subsidy': z_per,
            'L': z_per,
            'q_yes': q0,
            'q_no': q0,
            'virtual_yes': Decimal('0'),
            'virtual_no': Decimal('0'),
            'seigniorage': Decimal('0'),
            'active': True,
            'lob_pools': {
                'YES': {
                    'buy': {},
                    'sell': {},
                },
                'NO': {
                    'buy': {},
                    'sell': {},
                },
            },
        })
    return {'binaries': binaries, 'pre_sum_yes': Decimal(n_outcomes) * (q0 / z_per)}

@pytest.fixture
def sample_binary(initial_state: EngineState) -> BinaryState:
    return get_binary(initial_state, 1)

def add_sample_pools(binary: BinaryState, is_yes: bool, is_buy: bool, tick: int, volume: Decimal, shares: Dict[str, Decimal]):
    side = 'YES' if is_yes else 'NO'
    direction = 'buy' if is_buy else 'sell'
    if tick not in binary['lob_pools'][side][direction]:
        binary['lob_pools'][side][direction][tick] = {'volume': Decimal('0'), 'shares': {}}
    binary['lob_pools'][side][direction][tick]['volume'] += volume
    for user, share in shares.items():
        binary['lob_pools'][side][direction][tick]['shares'][user] = binary['lob_pools'][side][direction][tick]['shares'].get(user, Decimal('0')) + share

# Tests
def test_binary_search_max_delta_buy_yes(default_params: EngineParams, sample_binary: BinaryState):
    pool_tick = Decimal('0.60')
    f_i = compute_f_i(default_params, default_params['zeta_start'], {'binaries': [sample_binary] * 3})
    max_high = Decimal('10000')
    delta = binary_search_max_delta(pool_tick, True, True, sample_binary, default_params, f_i, max_high)
    assert delta > Decimal('0')
    assert validate_size(delta) is None
    cost = buy_cost_yes(sample_binary, delta, default_params, f_i)
    # Simulate the price after the trade
    from app.engine.amm_math import get_new_p_yes_after_buy
    p_after = get_new_p_yes_after_buy(sample_binary, delta, cost, f_i)
    assert p_after <= pool_tick

def test_binary_search_max_delta_sell_yes(default_params: EngineParams, sample_binary: BinaryState):
    pool_tick = Decimal('0.80')
    f_i = compute_f_i(default_params, default_params['zeta_start'], {'binaries': [sample_binary] * 3})
    max_high = Decimal('10000')
    delta = binary_search_max_delta(pool_tick, False, True, sample_binary, default_params, f_i, max_high)
    assert delta > Decimal('0')
    received = sell_received_yes(sample_binary, delta, default_params, f_i)
    # Simulate the price after the trade
    from app.engine.amm_math import get_new_p_yes_after_sell
    p_after = get_new_p_yes_after_sell(sample_binary, delta, received, f_i)
    assert p_after >= pool_tick

def test_update_pool_and_get_deltas():
    pool = {'volume': Decimal('1000'), 'shares': {'user1': Decimal('600'), 'user2': Decimal('400')}}
    delta = Decimal('500')
    charge = Decimal('300')
    is_buy = True
    position_deltas, balance_deltas = update_pool_and_get_deltas(pool, delta, charge, is_buy)
    assert pool['volume'] == Decimal('500')
    assert sum(pool['shares'].values()) == Decimal('500')
    assert position_deltas['user1'] == Decimal('300')  # Pro-rata
    assert position_deltas['user2'] == Decimal('200')
    assert balance_deltas['user1'] == Decimal('-180') if is_buy else Decimal('180')

def test_apply_rebates():
    surplus = Decimal('100')
    sigma = Decimal('0.5')
    original_volume = Decimal('1000')
    shares = {'user1': Decimal('600'), 'user2': Decimal('400')}
    balance_deltas: Dict[str, Decimal] = {'user1': Decimal('0'), 'user2': Decimal('0')}
    apply_rebates(surplus, sigma, original_volume, shares, balance_deltas)
    assert balance_deltas['user1'] == Decimal('30')  # (1-0.5)*100 * 600/1000 = 30
    assert balance_deltas['user2'] == Decimal('20')

def test_auto_fill_buy_diversion(default_params: EngineParams, initial_state: EngineState):
    # Use the binary at index 1 (same as auto_fill will use)
    binary = initial_state['binaries'][1]
    add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})  # Tick 0.60 buy YES
    diversion = Decimal('100')
    total_surplus, events = auto_fill(initial_state, 1, diversion, default_params)
    assert total_surplus > Decimal('0')
    assert len(events) > 0
    event: AutoFillEvent = events[0]
    assert event['type'] == 'auto_fill'
    assert event['delta'] > Decimal('0')
    assert event['surplus'] > Decimal('0')
    update_subsidies(initial_state, default_params)
    assert binary['V'] > Decimal('0')  # Sigma surplus added
    assert binary['q_yes'] > default_params['q0']

def test_auto_fill_zero_diversion(default_params: EngineParams, initial_state: EngineState):
    total_surplus, events = auto_fill(initial_state, 1, Decimal('0'), default_params)
    assert total_surplus == Decimal('0')
    assert events == []

def test_auto_fill_no_pools(default_params: EngineParams, initial_state: EngineState):
    total_surplus, events = auto_fill(initial_state, 1, Decimal('100'), default_params)
    assert total_surplus == Decimal('0')
    assert events == []

def test_auto_fill_caps(default_params: EngineParams, initial_state: EngineState):
    binary = get_binary(initial_state, 1)
    for tick in [60, 61, 62, 63]:  # More than af_max_pools
        add_sample_pools(binary, True, True, tick, Decimal('1000'), {'user1': Decimal('1000')})
    diversion = Decimal('10000')  # Large to hit caps
    total_surplus, events = auto_fill(initial_state, 1, diversion, default_params)
    assert len(events) <= default_params['af_max_pools']
    assert total_surplus <= default_params['af_max_surplus'] * diversion / default_params['zeta_start']

def test_auto_fill_determinism(default_params: EngineParams, initial_state: EngineState):
    binary = get_binary(initial_state, 1)
    add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})
    add_sample_pools(binary, True, True, 50, Decimal('1000'), {'user1': Decimal('1000')})  # Should sort desc
    diversion = Decimal('100')
    total_surplus1, events1 = auto_fill(initial_state, 1, diversion, default_params)
    # Reset and rerun
    binary['lob_pools']['YES']['buy'] = {}  # Clear
    add_sample_pools(binary, True, True, 50, Decimal('1000'), {'user1': Decimal('1000')})  # Different order
    add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})
    total_surplus2, events2 = auto_fill(initial_state, 1, diversion, default_params)
    assert total_surplus1 == total_surplus2
    assert len(events1) == len(events2)

def test_auto_fill_negative_surplus(default_params: EngineParams, initial_state: EngineState):
    binary = get_binary(initial_state, 1)
    add_sample_pools(binary, True, True, 40, Decimal('1000'), {'user1': Decimal('1000')})  # Tick below p
    diversion = Decimal('100')
    total_surplus, events = auto_fill(initial_state, 1, diversion, default_params)
    assert total_surplus == Decimal('0')
    assert events == []  # Skip if surplus <=0

def test_auto_fill_invariants(default_params: EngineParams, initial_state: EngineState):
    binary = get_binary(initial_state, 1)
    add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})
    diversion = Decimal('100')
    auto_fill(initial_state, 1, diversion, default_params)
    update_subsidies(initial_state, default_params)
    assert binary['q_yes'] + binary['q_no'] < Decimal('2') * Decimal(str(binary['L']))
    assert binary['seigniorage'] >= Decimal('0')
    assert get_effective_p_yes(binary) < default_params['p_max']