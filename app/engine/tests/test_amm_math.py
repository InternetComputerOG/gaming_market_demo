import pytest
from decimal import Decimal, getcontext
from typing import Dict, Any

getcontext().prec = 28

from app.engine.amm_math import (
    get_effective_p_yes,
    get_effective_p_no,
    get_new_p_yes_after_buy,
    get_new_p_yes_after_sell,
    get_new_p_no_after_buy,
    get_new_p_no_after_sell,
    buy_cost_yes,
    sell_received_yes,
    buy_cost_no,
    sell_received_no,
)
from app.engine.state import BinaryState
from app.engine.params import EngineParams
from app.utils import validate_size, validate_price, price_value, solve_quadratic, safe_divide, decimal_sqrt

@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 2,
        'z': Decimal('10000'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('2500'),
        'f': Decimal('0.01'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'mu_start': Decimal('1'),
        'nu_start': Decimal('1'),
        'kappa_start': Decimal('0.001'),
        'zeta_start': Decimal('0.1'),
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
        'interpolation_mode': 'continue',
        'res_schedule': [],
    }

@pytest.fixture
def default_binary(default_params) -> BinaryState:
    L = safe_divide(default_params['z'], Decimal(default_params['n_outcomes']))
    q0 = default_params['q0']
    return {
        'outcome_i': 0,
        'V': Decimal('0'),
        'subsidy': L,
        'L': L,
        'q_yes': q0,
        'q_no': q0,
        'virtual_yes': Decimal('0'),
        'seigniorage': Decimal('0'),
        'active': True,
        'lob_pools': {},
    }

@pytest.fixture
def f_i(default_params) -> Decimal:
    N = default_params['n_outcomes']
    zeta = default_params['zeta_start']
    return Decimal('1') - Decimal(N - 1) * zeta

def test_get_effective_p_yes(default_binary):
    p = get_effective_p_yes(default_binary)
    assert p == Decimal('0.5')

def test_get_effective_p_no(default_binary):
    p = get_effective_p_no(default_binary)
    assert p == Decimal('0.5')

def test_get_new_p_yes_after_buy(default_binary, default_params, f_i):
    delta = Decimal('100')
    p_new = get_new_p_yes_after_buy(default_binary, delta, Decimal('59.375'), f_i)  # From manual calc
    assert p_new == safe_divide(default_binary['q_yes'] + default_binary['virtual_yes'] + delta, default_binary['L'] + f_i * Decimal('59.375'))

def test_get_new_p_yes_after_sell(default_binary, default_params, f_i):
    delta = Decimal('100')
    X = Decimal('40')  # Placeholder
    p_new = get_new_p_yes_after_sell(default_binary, delta, X, f_i)
    assert p_new == safe_divide(default_binary['q_yes'] + default_binary['virtual_yes'] - delta, default_binary['L'] - f_i * X)

def test_get_new_p_no_after_buy(default_binary, default_params, f_i):
    delta = Decimal('100')
    X = Decimal('59.375')
    p_new = get_new_p_no_after_buy(default_binary, delta, X, f_i)
    assert p_new == safe_divide(default_binary['q_no'], default_binary['L'] + f_i * X)

def test_get_new_p_no_after_sell(default_binary, default_params, f_i):
    delta = Decimal('100')
    X = Decimal('40')
    p_new = get_new_p_no_after_sell(default_binary, delta, X, f_i)
    assert p_new == safe_divide(default_binary['q_no'] - delta, default_binary['L'] - f_i * X)

def test_buy_cost_yes(default_binary, default_params, f_i):
    delta = Decimal('100')
    cost = buy_cost_yes(default_binary, delta, default_params, f_i)
    p = get_effective_p_yes(default_binary)
    q = default_binary['q_yes'] + default_binary['virtual_yes']
    L = default_binary['L']
    mu = default_params['mu_start']
    nu = default_params['nu_start']
    kappa = default_params['kappa_start']
    a = mu / (mu + nu)
    b = nu / (mu + nu)
    k = delta * a * p + kappa * delta ** 2
    m = delta * b * (q + delta)
    coeff_a = f_i
    coeff_b = L - f_i * k
    coeff_c = -k * L - m
    disc = coeff_b ** 2 - 4 * coeff_a * coeff_c
    assert disc >= 0
    X = (-coeff_b + decimal_sqrt(disc)) / (2 * coeff_a)
    p_prime = (q + delta) / (L + f_i * X)
    if p_prime > default_params['p_max']:
        X *= (p_prime / default_params['p_max']) ** default_params['eta']
    assert cost == price_value(X)

def test_buy_cost_yes_zero_delta(default_binary, default_params, f_i):
    delta = Decimal('0')
    cost = buy_cost_yes(default_binary, delta, default_params, f_i)
    assert cost == Decimal('0')

def test_buy_cost_yes_penalty(default_binary, default_params, f_i):
    delta = Decimal('10000')  # Large to trigger p' > p_max
    cost = buy_cost_yes(default_binary, delta, default_params, f_i)
    # Test that cost is positive and reasonable for large delta
    assert cost > Decimal('0')
    # Test that large delta results in higher cost than small delta
    small_cost = buy_cost_yes(default_binary, Decimal('100'), default_params, f_i)
    assert cost > small_cost

def test_sell_received_yes(default_binary, default_params, f_i):
    delta = Decimal('100')
    received = sell_received_yes(default_binary, delta, default_params, f_i)
    assert received > Decimal('0')

def test_buy_cost_no(default_binary, default_params, f_i):
    delta = Decimal('100')
    cost = buy_cost_no(default_binary, delta, default_params, f_i)
    assert cost > Decimal('0')

def test_sell_received_no(default_binary, default_params, f_i):
    delta = Decimal('100')
    received = sell_received_no(default_binary, delta, default_params, f_i)
    assert received > Decimal('0')

def test_validate_size_negative():
    with pytest.raises(ValueError):
        validate_size(Decimal('-1'))

def test_invariant_preservation_buy(default_binary, default_params, f_i):
    delta = Decimal('1000')
    cost = buy_cost_yes(default_binary, delta, default_params, f_i)
    new_q_eff = default_binary['q_yes'] + default_binary['virtual_yes'] + delta
    new_L = default_binary['L'] + f_i * cost
    assert new_q_eff < new_L

def test_discriminant_non_negative(default_binary, default_params, f_i):
    delta = Decimal('100')
    p = get_effective_p_yes(default_binary)
    q = default_binary['q_yes'] + default_binary['virtual_yes']
    L = default_binary['L']
    mu = default_params['mu_start']
    nu = default_params['nu_start']
    kappa = default_params['kappa_start']
    a = mu / (mu + nu)
    b = nu / (mu + nu)
    k = delta * a * p + kappa * delta ** 2
    m = delta * b * (q + delta)
    coeff_a = f_i
    coeff_b = L - f_i * k
    coeff_c = -k * L - m
    disc = coeff_b ** 2 - 4 * coeff_a * coeff_c
    assert disc >= 0