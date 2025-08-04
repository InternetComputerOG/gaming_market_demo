import pytest
from decimal import Decimal
from typing import List, Dict, Any
from typing_extensions import TypedDict

from app.engine.lob_matching import (
    get_pool_key,
    get_tick_from_key,
    is_opt_in_from_key,
    add_to_lob_pool,
    cancel_from_pool,
    cross_match_binary,
    match_market_order,
)
from app.engine.state import EngineState, BinaryState, get_binary, update_subsidies
from app.engine.params import EngineParams
from app.utils import usdc_amount, price_value, validate_size, safe_divide

@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 3,
        'z': Decimal('10000'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('10000') / Decimal('3') / Decimal('2'),
        'mu_start': Decimal('1'),
        'mu_end': Decimal('1'),
        'nu_start': Decimal('1'),
        'nu_end': Decimal('1'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.001'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.1'),
        'f': Decimal('0.01'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'tick_size': Decimal('0.01'),
        'cm_enabled': True,
        'f_match': Decimal('0.005'),
        'af_enabled': True,
        'sigma': Decimal('0.5'),
        'af_cap_frac': Decimal('0.1'),
        'af_max_pools': 3,
        'af_max_surplus': Decimal('0.05'),
        'mr_enabled': False,
        'vc_enabled': True,
        'interpolation_mode': 'continue',
    }

@pytest.fixture
def init_state(default_params: EngineParams) -> EngineState:
    subsidy_per = default_params['z'] / Decimal(default_params['n_outcomes'])
    q0 = default_params['q0']
    state: EngineState = {
        'binaries': [
            {
                'outcome_i': i,
                'V': Decimal('0'),
                'subsidy': subsidy_per,
                'L': subsidy_per,
                'q_yes': q0,
                'q_no': q0,
                'virtual_yes': Decimal('0'),
                'seigniorage': Decimal('0'),
                'active': True,
                'lob_pools': {
                    'YES': {'buy': {}, 'sell': {}},
                    'NO': {'buy': {}, 'sell': {}},
                },
            } for i in range(1, default_params['n_outcomes'] + 1)
        ],
        'pre_sum_yes': Decimal(default_params['n_outcomes']) * Decimal('0.5'),
    }
    return state

def test_get_pool_key():
    assert get_pool_key(50, True) == 50
    assert get_pool_key(50, False) == -50
    assert get_pool_key(0, True) == 0
    assert get_pool_key(0, False) == 0  # Edge: 0 same

def test_get_tick_from_key():
    assert get_tick_from_key(50) == 50
    assert get_tick_from_key(-50) == 50
    assert get_tick_from_key(0) == 0

def test_is_opt_in_from_key():
    assert is_opt_in_from_key(50) is True
    assert is_opt_in_from_key(-50) is False
    assert is_opt_in_from_key(0) is True  # Positive or zero as opt-in

def test_add_to_lob_pool(init_state: EngineState, default_params: EngineParams):
    state = init_state
    add_to_lob_pool(state, 1, 'YES', True, 50, 'user1', Decimal('100'), True)
    binary = get_binary(state, 1)
    pool = binary['lob_pools']['YES']['buy'][50]
    # Buy pool volume = amount * price = 100 * 0.50 = 50 USDC
    assert pool['volume'] == Decimal('50.00')
    assert pool['shares']['user1'] == Decimal('100')  # Shares still track token amount

    # Add more same pool
    add_to_lob_pool(state, 1, 'YES', True, 50, 'user2', Decimal('50'), True)
    # Total volume = (100 + 50) * 0.50 = 75 USDC
    assert pool['volume'] == Decimal('75.00')
    assert pool['shares']['user1'] == Decimal('100')
    assert pool['shares']['user2'] == Decimal('50')

    # Non-opt-in
    add_to_lob_pool(state, 1, 'NO', False, 40, 'user3', Decimal('200'), False)
    pool_no = binary['lob_pools']['NO']['sell'][-40]
    assert pool_no['volume'] == Decimal('200')
    assert pool_no['shares']['user3'] == Decimal('200')

def test_cancel_from_pool(init_state: EngineState, default_params: EngineParams):
    state = init_state
    add_to_lob_pool(state, 1, 'YES', True, 50, 'user1', Decimal('100'), True)
    add_to_lob_pool(state, 1, 'YES', True, 50, 'user2', Decimal('50'), True)

    binary = get_binary(state, 1)
    returned = cancel_from_pool(state, 1, 'YES', True, 50, 'user1', True)
    assert returned == Decimal('100')  # Returns token amount
    pool = binary['lob_pools']['YES']['buy'][50]
    # Remaining volume = 50 tokens * $0.50 = $25 USDC
    assert pool['volume'] == Decimal('25.00')
    assert 'user1' not in pool['shares']
    assert pool['shares']['user2'] == Decimal('50')

    # Cancel all, clean pool
    cancel_from_pool(state, 1, 'YES', True, 50, 'user2', True)
    assert 50 not in binary['lob_pools']['YES']['buy']

    # Edge: Empty pool cancel
    with pytest.raises(ValueError):
        cancel_from_pool(state, 1, 'YES', True, 50, 'user3', True)

def test_cross_match_binary(init_state: EngineState, default_params: EngineParams):
    import copy
    state = copy.deepcopy(init_state)
    params = default_params.copy()
    params['tick_size'] = Decimal('0.01')
    tick_yes = 50  # $0.50
    tick_no = 60  # $0.60, sum=1.10 >=1
    add_to_lob_pool(state, 1, 'YES', True, tick_yes, 'buyer1', Decimal('100'), True)  # Buy YES at 0.50
    add_to_lob_pool(state, 1, 'NO', False, tick_no, 'seller1', Decimal('100'), True)  # Sell NO at 0.60

    fills = cross_match_binary(state, 1, params, 1000, 1)  # ts=1000, tick_id=1
    assert len(fills) == 1
    fill = fills[0]
    assert fill['size'] == Decimal('100')  # Min volume
    assert fill['price_yes'] == Decimal('0.50')
    assert fill['price_no'] == Decimal('0.60')
    assert fill['fee'] == Decimal('0.005') * Decimal('100') * (Decimal('0.50') + Decimal('0.60')) / Decimal('2')  # f_match * size * (p_y + p_n) / 2
    binary = get_binary(state, 1)
    # V increases by (price_yes + price_no) * fill - fee
    fee = Decimal('0.005') * Decimal('100') * (Decimal('0.50') + Decimal('0.60')) / Decimal('2')
    expected_v_increase = (Decimal('0.50') + Decimal('0.60')) * Decimal('100') - fee
    assert abs(Decimal(str(binary['V'])) - expected_v_increase) < Decimal('0.001')  # Allow small precision difference
    # Check token supplies increased by fill amount (allowing for float precision)
    expected_q_yes = float(default_params['q0'] + Decimal('100'))
    expected_q_no = float(default_params['q0'] + Decimal('100'))
    assert abs(binary['q_yes'] - expected_q_yes) < 0.001
    assert abs(binary['q_no'] - expected_q_no) < 0.001
    assert 50 not in binary['lob_pools']['YES']['buy']
    assert 60 not in binary['lob_pools']['NO']['sell']

    # Toggle off
    params['cm_enabled'] = False
    fills_off = cross_match_binary(state, 1, params, 1000, 1)
    assert len(fills_off) == 0

def test_match_market_order(init_state: EngineState, default_params: EngineParams):
    state = init_state
    add_to_lob_pool(state, 1, 'YES', False, 40, 'seller1', Decimal('200'), True)  # Sell YES at 0.40
    add_to_lob_pool(state, 1, 'YES', False, 50, 'seller2', Decimal('100'), True)  # Sell YES at 0.50

    fills, remaining = match_market_order(state, 1, True, True, Decimal('250'), default_params, 1000, 1)  # Buy YES market 250
    assert len(fills) == 2
    assert fills[0]['price'] == Decimal('0.40')  # Lowest first
    assert fills[0]['size'] == Decimal('200')
    assert fills[1]['price'] == Decimal('0.50')
    assert fills[1]['size'] == Decimal('50')
    assert remaining == Decimal('0')
    binary = get_binary(state, 1)
    assert 40 not in binary['lob_pools']['YES']['sell']
    assert binary['lob_pools']['YES']['sell'][50]['volume'] == Decimal('50')  # Partial

    # Invariant check
    update_subsidies(state, default_params)
    assert Decimal(str(binary['q_yes'])) + Decimal(str(binary['q_no'])) < Decimal('2') * Decimal(str(binary['L']))

    # Zero size
    with pytest.raises(ValueError):
        match_market_order(state, 1, True, True, Decimal('0'), default_params, 1000, 1)

def test_edge_cases(init_state: EngineState, default_params: EngineParams):
    state = init_state
    # Empty match
    fills, remaining = match_market_order(state, 1, True, True, Decimal('100'), default_params, 1000, 1)
    assert len(fills) == 0
    assert remaining == Decimal('100')

    # Inactive binary
    binary = get_binary(state, 1)
    binary['active'] = False
    with pytest.raises(ValueError):
        add_to_lob_pool(state, 1, 'YES', True, 50, 'user1', Decimal('100'), True)

    # Invalid tick
    with pytest.raises(ValueError):
        add_to_lob_pool(state, 1, 'YES', True, 0, 'user1', Decimal('100'), True)  # Tick 0 invalid?

    # Negative amount
    with pytest.raises(ValueError):
        add_to_lob_pool(state, 1, 'YES', True, 50, 'user1', Decimal('-10'), True)