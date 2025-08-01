import pytest
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from typing_extensions import TypedDict

from app.engine.orders import apply_orders, Order, Fill
from app.engine.state import EngineState, BinaryState, init_state, get_binary, get_p_yes, get_p_no, update_subsidies
from app.engine.params import EngineParams
from app.engine.amm_math import get_effective_p_yes, get_effective_p_no
from app.utils import usdc_amount, price_value, validate_size, validate_price, safe_divide

@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 3,
        'z': Decimal('10000'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('5000') / Decimal('3'),
        'mu_start': Decimal('2'),
        'mu_end': Decimal('1.5'),
        'nu_start': Decimal('1'),
        'nu_end': Decimal('1'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.0005'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.01'),
        'interpolation_mode': 'continue',
        'fee_rate': Decimal('0.01'),
        'f_match': Decimal('0.005'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'tick_size': Decimal('0.01'),
        'cm_enabled': True,
        'af_enabled': True,
        'sigma': Decimal('0.5'),
        'af_cap_frac': Decimal('0.1'),
        'af_max_pools': 3,
        'af_max_surplus': Decimal('0.05'),
        'mr_enabled': False,
        'vc_enabled': True,
    }

@pytest.fixture
def initial_state(default_params: EngineParams) -> EngineState:
    return init_state(default_params)

def test_apply_orders_zero_orders(initial_state: EngineState, default_params: EngineParams):
    fills, new_state, events = apply_orders(initial_state, [], default_params, 0)
    assert len(fills) == 0
    assert new_state == initial_state
    assert len(events) == 0

def test_apply_market_buy_yes_basic(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10'),
        'limit_price': None,
        'max_slippage': Decimal('0.05'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }]
    fills, new_state, events = apply_orders(initial_state, orders, default_params, 1000)
    assert len(fills) == 1
    fill = fills[0]
    assert fill['size'] == Decimal('10')
    assert Decimal('0.5') < fill['price'] < Decimal('0.51')  # Approximate post-impact
    binary = get_binary(new_state, 0)
    assert get_effective_p_yes(binary) > Decimal('0.5')
    assert len(events) > 0
    assert any(e['type'] == 'ORDER_FILLED' for e in events)

def test_apply_limit_add(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'LIMIT',
        'is_buy': True,
        'size': Decimal('10'),
        'limit_price': Decimal('0.6'),
        'max_slippage': None,
        'af_opt_in': True,
        'ts_ms': 1000,
    }]
    fills, new_state, events = apply_orders(initial_state, orders, default_params, 1000)
    assert len(fills) == 0
    binary = get_binary(new_state, 0)
    lob_pools = binary['lob_pools']['YES']['buy']
    tick = int(Decimal('0.6') / default_params['tick_size'])
    key = tick if orders[0]['af_opt_in'] else -tick
    assert lob_pools[key]['volume'] == Decimal('6')  # size * limit_price quantized
    assert 'user1' in lob_pools[key]['shares']
    assert any(e['type'] == 'ORDER_ACCEPTED' for e in events)

def test_limit_matching_with_market(initial_state: EngineState, default_params: EngineParams):
    # Add limit sell YES at 0.55
    limit_order: Order = {
        'order_id': 'limit1',
        'user_id': 'user2',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'LIMIT',
        'is_buy': False,
        'size': Decimal('20'),
        'limit_price': Decimal('0.55'),
        'max_slippage': None,
        'af_opt_in': False,
        'ts_ms': 1000,
    }
    _, state_after_limit, _ = apply_orders(initial_state, [limit_order], default_params, 1000)
    
    # Market buy YES 10
    market_order: Order = {
        'order_id': 'market1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10'),
        'limit_price': None,
        'max_slippage': Decimal('0.1'),
        'af_opt_in': False,
        'ts_ms': 2000,
    }
    fills, new_state, events = apply_orders(state_after_limit, [market_order], default_params, 2000)
    assert len(fills) == 1
    assert fills[0]['price'] == Decimal('0.55')
    assert fills[0]['size'] == Decimal('10')
    binary = get_binary(new_state, 0)
    lob_pools = binary['lob_pools']['YES']['sell']
    tick = int(Decimal('0.55') / default_params['tick_size'])
    key = -tick  # Since af_opt_in False
    assert lob_pools[key]['volume'] == Decimal('20') - Decimal('10')  # Remaining

def test_cross_matching_enabled(initial_state: EngineState, default_params: EngineParams):
    # Add limit buy YES at 0.6
    buy_yes: Order = {
        'order_id': 'buy_yes',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'LIMIT',
        'is_buy': True,
        'size': Decimal('10'),
        'limit_price': Decimal('0.6'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }
    # Add limit sell NO at 0.4 (complementary)
    sell_no: Order = {
        'order_id': 'sell_no',
        'user_id': 'user2',
        'outcome_i': 0,
        'yes_no': 'NO',
        'type': 'LIMIT',
        'is_buy': False,
        'size': Decimal('10'),
        'limit_price': Decimal('0.4'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }
    orders = [buy_yes, sell_no]
    fills, new_state, events = apply_orders(initial_state, orders, default_params, 1000)
    # Cross-match should occur
    assert len(fills) > 0
    fill = fills[0]
    assert fill['size'] == Decimal('10')
    assert Decimal('0.6') + Decimal('0.4') >= 1  # Condition
    binary = get_binary(new_state, 0)
    assert binary['q_yes'] > Decimal('5000') / Decimal('3')
    assert binary['q_no'] > Decimal('5000') / Decimal('3')

def test_auto_fill_triggered(initial_state: EngineState, default_params: EngineParams):
    # Setup to trigger diversion
    # Market buy YES 0 large to cause diversion to 1
    order: Order = {
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('100'),
        'max_slippage': Decimal('0.1'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }
    # Add opt-in limit buy YES 1 at high tick
    limit_order: Order = {
        'order_id': 'limit1',
        'user_id': 'user2',
        'outcome_i': 1,
        'yes_no': 'YES',
        'type': 'LIMIT',
        'is_buy': True,
        'size': Decimal('50'),
        'limit_price': Decimal('0.6'),
        'af_opt_in': True,
        'ts_ms': 500,
    }
    combined_orders = [limit_order, order]
    fills, new_state, events = apply_orders(initial_state, combined_orders, default_params, 1000)
    # Check auto-fill occurred
    assert any('AUTO_FILL' in str(e) for e in events)  # AutoFillEvent
    binary1 = get_binary(new_state, 1)
    assert binary1['q_yes'] > initial_state['binaries'][1]['q_yes']  # Filled

def test_dynamic_params_interpolation(initial_state: EngineState, default_params: EngineParams):
    # Set total_duration implicitly via interpolation
    # Assume total_duration = 10000 for test
    default_params['total_duration'] = 10000  # Add if needed
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10'),
        'max_slippage': Decimal('0.05'),
        'af_opt_in': False,
        'ts_ms': 5000,
    }]
    fills_start, _, _ = apply_orders(initial_state, orders, default_params, 0)  # t=0, zeta=0.1
    fills_mid, _, _ = apply_orders(initial_state, orders, default_params, 5000)  # t=0.5, zeta approx 0.055
    assert fills_start[0]['price'] != fills_mid[0]['price']  # Different impacts due to zeta change

def test_multi_res_active_count(default_params: EngineParams):
    default_params['mr_enabled'] = True
    state = init_state(default_params)
    # Deactivate one
    state['binaries'][2]['active'] = False
    # N_active = 2, zeta max 1/1=1, but clamped
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10'),
        'max_slippage': Decimal('0.05'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }]
    _, new_state, _ = apply_orders(state, orders, default_params, 1000)
    # Check diversion only to active (1)
    assert new_state['binaries'][1]['V'] > state['binaries'][1]['V']
    assert new_state['binaries'][2]['V'] == state['binaries'][2]['V']  # No diversion to inactive

def test_oversized_penalty(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10000'),  # Large to hit penalty
        'max_slippage': Decimal('0.5'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }]
    fills, new_state, _ = apply_orders(initial_state, orders, default_params, 1000)
    assert len(fills) == 1
    binary = get_binary(new_state, 0)
    p_yes = get_effective_p_yes(binary)
    assert p_yes < default_params['p_max']  # Penalty enforced
    assert p_yes > Decimal('0.9')  # Significant impact

def test_slippage_reject(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [{
        'order_id': 'order1',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('100'),
        'max_slippage': Decimal('0.001'),  # Tight
        'af_opt_in': False,
        'ts_ms': 1000,
    }]
    fills, new_state, events = apply_orders(initial_state, orders, default_params, 1000)
    assert len(fills) == 0
    assert new_state == initial_state
    assert any(e['type'] == 'ORDER_REJECTED' for e in events)

def test_solvency_invariant_after_batch(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [
        # Mix of buys/sells, limits/markets
        {
            'order_id': 'buy_yes_market',
            'user_id': 'user1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'MARKET',
            'is_buy': True,
            'size': Decimal('50'),
            'max_slippage': Decimal('0.1'),
            'af_opt_in': False,
            'ts_ms': 1000,
        },
        {
            'order_id': 'sell_no_limit',
            'user_id': 'user2',
            'outcome_i': 0,
            'yes_no': 'NO',
            'type': 'LIMIT',
            'is_buy': False,
            'size': Decimal('30'),
            'limit_price': Decimal('0.45'),
            'af_opt_in': True,
            'ts_ms': 2000,
        },
    ]
    _, new_state, _ = apply_orders(initial_state, orders, default_params, 2000)
    for binary in new_state['binaries']:
        q_yes_eff = binary['q_yes'] + binary['virtual_yes']
        assert q_yes_eff + binary['q_no'] < Decimal('2') * binary['L']
        assert q_yes_eff < binary['L']
        assert binary['q_no'] < binary['L']

def test_determinism_same_inputs(initial_state: EngineState, default_params: EngineParams):
    orders: List[Order] = [
        {
            'order_id': 'order1',
            'user_id': 'user1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'MARKET',
            'is_buy': True,
            'size': Decimal('10'),
            'max_slippage': Decimal('0.05'),
            'af_opt_in': False,
            'ts_ms': 2000,
        },
        {
            'order_id': 'order2',
            'user_id': 'user2',
            'outcome_i': 1,
            'yes_no': 'NO',
            'type': 'LIMIT',
            'is_buy': False,
            'size': Decimal('5'),
            'limit_price': Decimal('0.5'),
            'af_opt_in': True,
            'ts_ms': 1000,
        },
    ]
    fills1, state1, events1 = apply_orders(initial_state, orders, default_params, 2000)
    fills2, state2, events2 = apply_orders(initial_state, orders[:], default_params, 2000)  # Copy
    assert fills1 == fills2
    assert state1 == state2
    assert events1 == events2

def test_edge_zero_size_validation():
    with pytest.raises(ValueError):
        validate_size(Decimal('0'))

def test_edge_negative_diversion_autofill(initial_state: EngineState, default_params: EngineParams):
    # Sell to cause negative diversion (price rise in others)
    order: Order = {
        'order_id': 'sell_yes',
        'user_id': 'user1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': False,
        'size': Decimal('100'),
        'max_slippage': Decimal('0.1'),
        'af_opt_in': False,
        'ts_ms': 1000,
    }
    # Add opt-in limit sell YES 1 at low tick
    limit_order: Order = {
        'order_id': 'limit_sell',
        'user_id': 'user2',
        'outcome_i': 1,
        'yes_no': 'YES',
        'type': 'LIMIT',
        'is_buy': False,
        'size': Decimal('50'),
        'limit_price': Decimal('0.4'),
        'af_opt_in': True,
        'ts_ms': 500,
    }
    fills, new_state, events = apply_orders(initial_state, [limit_order, order], default_params, 1000)
    assert any('AUTO_FILL' in str(e) for e in events)  # Triggered on negative diversion
    binary1 = get_binary(new_state, 1)
    assert binary1['q_yes'] < initial_state['binaries'][1]['q_yes']  # Sold

def test_caps_prevent_cascades(initial_state: EngineState, default_params: EngineParams):
    # Add multiple opt-in pools
    limits = []
    for i in range(5):  # More than af_max_pools=3
        limits.append({
            'order_id': f'limit{i}',
            'user_id': 'user1',
            'outcome_i': 1,
            'yes_no': 'YES',
            'type': 'LIMIT',
            'is_buy': True,
            'size': Decimal('10'),
            'limit_price': Decimal('0.55') + Decimal('0.01') * i,
            'af_opt_in': True,
            'ts_ms': 1000 + i,
        })
    # Triggering order
    trigger_order: Order = {
        'order_id': 'trigger',
        'user_id': 'user2',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('100'),
        'max_slippage': Decimal('0.1'),
        'af_opt_in': False,
        'ts_ms': 2000,
    }
    all_orders = limits + [trigger_order]
    fills, new_state, events = apply_orders(initial_state, all_orders, default_params, 2000)
    auto_fill_events = [e for e in events if 'AUTO_FILL' in str(e)]
    assert len(auto_fill_events) <= default_params['af_max_pools']  # Capped