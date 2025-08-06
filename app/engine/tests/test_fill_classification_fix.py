"""
Test for Checklist Item #3: Fill Classification and Dual Prices Missing for Cross-Matches

This test verifies that:
1. Cross-match fills have proper dual prices (price_yes and price_no)
2. All fill types have correct fill_type classification
3. ticks.py properly handles dual prices and uses dynamic f_match
4. Engine fills are properly propagated with all required fields
"""

import pytest
from decimal import Decimal
from typing import Dict, Any, List

from app.engine.orders import apply_orders, Fill, Order, AMM_USER_ID
from app.engine.state import EngineState, init_state
from app.engine.params import EngineParams
from app.services.ticks import normalize_fills_for_summary, extract_cross_match_events, create_tick
from app.utils import get_current_ms


def create_test_params() -> EngineParams:
    """Create test parameters for the engine."""
    return {
        'n_outcomes': 3,
        'outcome_names': ['Outcome A', 'Outcome B', 'Outcome C'],
        'z': 100.0,
        'gamma': 0.5,
        'q0': 10.0,
        'mu_start': 0.1,
        'mu_end': 0.1,
        'nu_start': 0.1,
        'nu_end': 0.1,
        'kappa_start': 0.1,
        'kappa_end': 0.1,
        'zeta_start': 0.05,
        'zeta_end': 0.05,
        'interpolation_mode': 'reset',
        'f': 0.01,
        'f_match': 0.02,  # Test with non-default f_match
        'p_max': 0.99,
        'p_min': 0.01,
        'eta': 0.1,
        'tick_size': 0.01,
        'sigma': 0.5,
        'af_cap_frac': 0.1,
        'af_max_pools': 5,
        'af_max_surplus': 10.0,
        'cm_enabled': True,
        'af_enabled': True,
        'mr_enabled': False,
        'vc_enabled': True,
        'batch_interval_ms': 1000,
        'total_duration': 3600,
        'gas_fee': 0.01,
        'start_ts_ms': get_current_ms()
    }


def create_test_state() -> EngineState:
    """Create test engine state."""
    params = create_test_params()
    return init_state(params)


def test_cross_match_dual_prices():
    """Test that cross-match fills have proper dual prices and fill_type."""
    state = create_test_state()
    params = create_test_params()
    current_time = 0
    
    # Create LIMIT orders that should cross-match
    orders: List[Order] = [
        # YES buy limit at 0.60
        {
            'order_id': 'order_1',
            'user_id': 'user_1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'LIMIT',
            'is_buy': True,
            'size': Decimal('10'),
            'limit_price': Decimal('0.60'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1000
        },
        # NO sell limit at 0.35 (complement would be 0.65, so should match with 0.60)
        {
            'order_id': 'order_2',
            'user_id': 'user_2',
            'outcome_i': 0,
            'yes_no': 'NO',
            'type': 'LIMIT',
            'is_buy': False,
            'size': Decimal('10'),
            'limit_price': Decimal('0.35'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1001
        }
    ]
    
    # Process orders
    fills, new_state, events = apply_orders(state, orders, params, current_time)
    
    # Find cross-match fills
    cross_match_fills = [f for f in fills if f['fill_type'] == 'CROSS_MATCH']
    
    # Verify cross-match fills have dual prices
    assert len(cross_match_fills) > 0, "Expected at least one cross-match fill"
    
    for fill in cross_match_fills:
        assert fill['fill_type'] == 'CROSS_MATCH', f"Expected CROSS_MATCH, got {fill['fill_type']}"
        assert fill['price_yes'] is not None, "Cross-match fill missing price_yes"
        assert fill['price_no'] is not None, "Cross-match fill missing price_no"
        assert isinstance(fill['price_yes'], Decimal), "price_yes should be Decimal"
        assert isinstance(fill['price_no'], Decimal), "price_no should be Decimal"
        
        # Verify dual prices are reasonable
        assert Decimal('0') < fill['price_yes'] < Decimal('1'), f"Invalid price_yes: {fill['price_yes']}"
        assert Decimal('0') < fill['price_no'] < Decimal('1'), f"Invalid price_no: {fill['price_no']}"


def test_amm_and_lob_fill_types():
    """Test that AMM and LOB fills have correct fill_type and single prices."""
    state = create_test_state()
    params = create_test_params()
    current_time = 0
    
    # Create orders that will generate different fill types
    orders: List[Order] = [
        # LIMIT order to create LOB pool
        {
            'order_id': 'limit_1',
            'user_id': 'user_1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'LIMIT',
            'is_buy': False,  # Sell limit
            'size': Decimal('5'),
            'limit_price': Decimal('0.55'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1000
        },
        # MARKET order that will partially match LOB and then AMM
        {
            'order_id': 'market_1',
            'user_id': 'user_2',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'MARKET',
            'is_buy': True,
            'size': Decimal('10'),  # Larger than LOB, will trigger AMM
            'limit_price': None,
            'max_slippage': Decimal('0.1'),
            'af_opt_in': False,
            'ts_ms': 1001
        }
    ]
    
    # Process orders
    fills, new_state, events = apply_orders(state, orders, params, current_time)
    
    # Check fill types
    lob_fills = [f for f in fills if f['fill_type'] == 'LOB_MATCH']
    amm_fills = [f for f in fills if f['fill_type'] == 'AMM']
    
    # Verify LOB fills
    for fill in lob_fills:
        assert fill['fill_type'] == 'LOB_MATCH', f"Expected LOB_MATCH, got {fill['fill_type']}"
        assert fill['price_yes'] is None, "LOB fill should not have price_yes"
        assert fill['price_no'] is None, "LOB fill should not have price_no"
        assert fill['price'] is not None, "LOB fill should have single price"
    
    # Verify AMM fills
    for fill in amm_fills:
        assert fill['fill_type'] == 'AMM', f"Expected AMM, got {fill['fill_type']}"
        assert fill['price_yes'] is None, "AMM fill should not have price_yes"
        assert fill['price_no'] is None, "AMM fill should not have price_no"
        assert fill['price'] is not None, "AMM fill should have single price"
        # AMM fills should involve AMM_USER_ID
        assert fill['buy_user_id'] == AMM_USER_ID or fill['sell_user_id'] == AMM_USER_ID


def test_ticks_extract_events_uses_dynamic_f_match():
    """Test that extract_cross_match_events uses params['f_match'] instead of hardcoded value."""
    # Create mock fills with cross-match
    fills = [
        {
            'trade_id': 'test_trade_1',
            'buy_user_id': 'user_1',
            'sell_user_id': 'user_2',
            'outcome_i': 0,
            'yes_no': 'YES',
            'price': Decimal('0.60'),
            'size': Decimal('10'),
            'fee': Decimal('0.1'),
            'tick_id': 1,
            'ts_ms': 1000,
            'fill_type': 'CROSS_MATCH',
            'price_yes': Decimal('0.60'),
            'price_no': Decimal('0.35')
        }
    ]
    
    state = create_test_state()
    
    # Test with custom f_match
    custom_f_match = 0.03
    params_custom = {'f_match': custom_f_match}
    
    events = extract_cross_match_events(fills, state, params_custom)
    
    assert len(events) > 0, "Expected cross-match events to be extracted"
    
    # Verify that the custom f_match was used in calculations
    event = events[0]
    expected_min_required = float(Decimal('1') + Decimal(str(custom_f_match)) * (Decimal('0.60') + Decimal('0.35')) / Decimal('2'))
    
    assert abs(event['min_required'] - expected_min_required) < 0.001, \
        f"Expected min_required {expected_min_required}, got {event['min_required']}"


def test_normalize_fills_handles_dual_prices():
    """Test that normalize_fills_for_summary properly handles dual prices."""
    # Create raw fills with different types
    raw_fills = [
        # Cross-match fill with dual prices
        {
            'trade_id': 'cross_1',
            'buy_user_id': 'user_1',
            'sell_user_id': 'user_2',
            'outcome_i': 0,
            'yes_no': 'YES',
            'price': Decimal('0.60'),
            'size': Decimal('10'),
            'fee': Decimal('0.1'),
            'tick_id': 1,
            'ts_ms': 1000,
            'fill_type': 'CROSS_MATCH',
            'price_yes': Decimal('0.60'),
            'price_no': Decimal('0.35')
        },
        # AMM fill with single price
        {
            'trade_id': 'amm_1',
            'buy_user_id': 'user_3',
            'sell_user_id': AMM_USER_ID,
            'outcome_i': 0,
            'yes_no': 'YES',
            'price': Decimal('0.55'),
            'size': Decimal('5'),
            'fee': Decimal('0.05'),
            'tick_id': 1,
            'ts_ms': 1001,
            'fill_type': 'AMM',
            'price_yes': None,
            'price_no': None
        }
    ]
    
    normalized = normalize_fills_for_summary(raw_fills)
    
    # Check cross-match fill
    cross_fill = next(f for f in normalized if f['fill_type'] == 'CROSS_MATCH')
    assert cross_fill['price_yes'] == 0.60, f"Expected price_yes 0.60, got {cross_fill['price_yes']}"
    assert cross_fill['price_no'] == 0.35, f"Expected price_no 0.35, got {cross_fill['price_no']}"
    
    # Check AMM fill
    amm_fill = next(f for f in normalized if f['fill_type'] == 'AMM')
    assert amm_fill['price_yes'] is None, "AMM fill should have price_yes as None"
    assert amm_fill['price_no'] is None, "AMM fill should have price_no as None"


def test_integration_fill_classification():
    """Integration test for complete fill classification and dual price propagation."""
    state = create_test_state()
    params = create_test_params()
    current_time = 0
    
    # Create complex order scenario with multiple fill types
    orders: List[Order] = [
        # LIMIT orders for cross-matching
        {
            'order_id': 'limit_yes',
            'user_id': 'user_1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'LIMIT',
            'is_buy': True,
            'size': Decimal('5'),
            'limit_price': Decimal('0.60'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1000
        },
        {
            'order_id': 'limit_no',
            'user_id': 'user_2',
            'outcome_i': 0,
            'yes_no': 'NO',
            'type': 'LIMIT',
            'is_buy': False,
            'size': Decimal('5'),
            'limit_price': Decimal('0.35'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1001
        },
        # LIMIT order for LOB pool
        {
            'order_id': 'limit_sell',
            'user_id': 'user_3',
            'outcome_i': 1,
            'yes_no': 'YES',
            'type': 'LIMIT',
            'is_buy': False,
            'size': Decimal('3'),
            'limit_price': Decimal('0.50'),
            'max_slippage': None,
            'af_opt_in': False,
            'ts_ms': 1002
        },
        # MARKET order that will hit LOB and AMM
        {
            'order_id': 'market_big',
            'user_id': 'user_4',
            'outcome_i': 1,
            'yes_no': 'YES',
            'type': 'MARKET',
            'is_buy': True,
            'size': Decimal('10'),
            'limit_price': None,
            'max_slippage': Decimal('0.2'),
            'af_opt_in': True,  # Enable auto-fill
            'ts_ms': 1003
        }
    ]
    
    # Process orders
    fills, new_state, events = apply_orders(state, orders, params, current_time)
    
    # Verify all fill types are present and correctly classified
    fill_types = {f['fill_type'] for f in fills}
    
    # Should have cross-match fills
    cross_fills = [f for f in fills if f['fill_type'] == 'CROSS_MATCH']
    assert len(cross_fills) > 0, "Expected cross-match fills"
    
    # Verify dual prices for cross-matches
    for fill in cross_fills:
        assert fill['price_yes'] is not None, "Cross-match missing price_yes"
        assert fill['price_no'] is not None, "Cross-match missing price_no"
    
    # Should have LOB and/or AMM fills
    single_price_fills = [f for f in fills if f['fill_type'] in ['LOB_MATCH', 'AMM', 'AUTO_FILL']]
    for fill in single_price_fills:
        assert fill['price_yes'] is None, f"{fill['fill_type']} should not have price_yes"
        assert fill['price_no'] is None, f"{fill['fill_type']} should not have price_no"
        assert fill['price'] is not None, f"{fill['fill_type']} should have single price"
    
    # Test ticks integration
    normalized_fills = normalize_fills_for_summary(fills)
    cross_events = extract_cross_match_events(normalized_fills, new_state, params)
    
    # Verify events use correct f_match
    if cross_events:
        event = cross_events[0]
        # Should use params['f_match'] = 0.02, not hardcoded 0.02
        expected_f_match = params['f_match']
        # Calculate expected min_required to verify f_match was used
        price_yes = Decimal(str(event['yes_tick'])) * Decimal(str(params['tick_size']))
        price_no = Decimal(str(event['no_tick'])) * Decimal(str(params['tick_size']))
        expected_min_required = float(Decimal('1') + Decimal(str(expected_f_match)) * (price_yes + price_no) / Decimal('2'))
        
        assert abs(event['min_required'] - expected_min_required) < 0.01, \
            f"Event should use params f_match={expected_f_match}"


if __name__ == "__main__":
    # Run tests
    test_cross_match_dual_prices()
    test_amm_and_lob_fill_types()
    test_ticks_extract_events_uses_dynamic_f_match()
    test_normalize_fills_handles_dual_prices()
    test_integration_fill_classification()
    print("All tests for Checklist Item #3 passed!")
