#!/usr/bin/env python3
"""
Comprehensive Integration Test for Autofill Type Fixes

This test validates the entire pipeline from batch runner through engine to autofill,
ensuring all Decimal/float type issues are resolved and the system works end-to-end.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.runner.batch_runner import convert_engine_params_to_decimals
from app.engine.orders import apply_orders
from app.engine.autofill import trigger_auto_fills, auto_fill
from app.utils import solve_quadratic
from app.config import get_default_engine_params

def test_batch_runner_parameter_conversion():
    """Test that batch runner correctly converts parameters to Decimal."""
    print("Testing batch runner parameter conversion...")
    
    # Get default float parameters
    float_params = get_default_engine_params()
    
    # Convert to Decimal
    decimal_params = convert_engine_params_to_decimals(float_params)
    
    # Verify critical parameters are converted
    critical_params = ['af_cap_frac', 'sigma', 'tick_size', 'zeta_start', 'mu_start', 'nu_start']
    
    for param in critical_params:
        if param in decimal_params:
            assert isinstance(decimal_params[param], Decimal), f"{param} should be Decimal, got {type(decimal_params[param])}"
            print(f"✅ {param}: {decimal_params[param]} (type: {type(decimal_params[param])})")
    
    print("✅ Batch runner parameter conversion works correctly")
    return True

def test_engine_integration_with_decimal_params():
    """Test that engine functions work correctly with Decimal parameters."""
    print("\nTesting engine integration with Decimal parameters...")
    
    # Create test state with all required fields
    state = {
        'binaries': [
            {
                'outcome_i': 0,
                'L': 1000.0,
                'q_yes': 400.0,
                'q_no': 400.0,
                'virtual_yes': 0.0,
                'V': 0.0,
                'subsidy': 1000.0,
                'seigniorage': 0.0,
                'active': True,
                'lob_pools': {
                    'YES': {'buy': {}, 'sell': {}},
                    'NO': {'buy': {}, 'sell': {}}
                }
            }
        ],
        'pre_sum_yes': 0.8
    }
    
    # Create test order
    orders = [{
        'order_id': 'test-order-1',
        'user_id': 'test-user-1',
        'outcome_i': 0,
        'yes_no': 'YES',
        'type': 'MARKET',
        'is_buy': True,
        'size': Decimal('10'),
        'limit_price': None,
        'max_slippage': None,
        'af_opt_in': True,
        'ts_ms': 1000
    }]
    
    # Get and convert parameters
    params = get_default_engine_params()
    decimal_params = convert_engine_params_to_decimals(params)
    
    try:
        # Test engine integration
        fills, new_state, events = apply_orders(state, orders, decimal_params, 1000)
        print(f"✅ Engine processed order successfully: {len(fills)} fills, {len(events)} events")
        
        # Verify fills have correct types
        for fill in fills:
            assert isinstance(fill['price'], Decimal), f"Fill price should be Decimal, got {type(fill['price'])}"
            assert isinstance(fill['size'], Decimal), f"Fill size should be Decimal, got {type(fill['size'])}"
        
        print("✅ Engine integration with Decimal parameters works correctly")
        return True
        
    except Exception as e:
        print(f"❌ Engine integration failed: {e}")
        return False

def test_autofill_integration_with_decimal_params():
    """Test that autofill works correctly with Decimal parameters and no type errors."""
    print("\nTesting autofill integration with Decimal parameters...")
    
    # Create test state with LOB pools to trigger autofill
    state = {
        'binaries': [
            {
                'outcome_i': 0,
                'L': 1000.0,
                'q_yes': 400.0,
                'q_no': 400.0,
                'virtual_yes': 0.0,
                'V': 0.0,
                'subsidy': 1000.0,
                'seigniorage': 0.0,
                'active': True,
                'lob_pools': {
                    'YES': {'buy': {50: {'volume': 20.0, 'shares': {'user1': 20.0}}}, 'sell': {}},
                    'NO': {'buy': {}, 'sell': {}}
                }
            },
            {
                'outcome_i': 1,
                'L': 1000.0,
                'q_yes': 400.0,
                'q_no': 400.0,
                'virtual_yes': 0.0,
                'V': 0.0,
                'subsidy': 1000.0,
                'seigniorage': 0.0,
                'active': True,
                'lob_pools': {
                    'YES': {'buy': {}, 'sell': {}},
                    'NO': {'buy': {}, 'sell': {}}
                }
            }
        ],
        'pre_sum_yes': 0.8
    }
    
    # Get and convert parameters
    params = get_default_engine_params()
    decimal_params = convert_engine_params_to_decimals(params)
    decimal_params['af_enabled'] = True
    
    try:
        # Test trigger_auto_fills with Decimal X
        X = Decimal('50')  # Large enough to trigger autofill
        events = trigger_auto_fills(state, 0, X, True, decimal_params, 1000)
        print(f"✅ trigger_auto_fills completed: {len(events)} events")
        
        # Test direct auto_fill call
        diversion = Decimal('25')
        surplus, af_events = auto_fill(state, 0, diversion, decimal_params)
        print(f"✅ auto_fill completed: surplus={surplus}, events={len(af_events)}")
        
        # Verify no type errors occurred
        assert isinstance(surplus, Decimal), f"Surplus should be Decimal, got {type(surplus)}"
        
        print("✅ Autofill integration with Decimal parameters works correctly")
        return True
        
    except Exception as e:
        print(f"❌ Autofill integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_solve_quadratic_edge_cases():
    """Test solve_quadratic with various edge cases that could cause string returns."""
    print("\nTesting solve_quadratic edge cases...")
    
    test_cases = [
        # Normal case
        (Decimal('1'), Decimal('-5'), Decimal('6')),
        # Edge case with very small coefficients
        (Decimal('0.001'), Decimal('-1000'), Decimal('1000000')),
        # Case that might trigger numpy fallback
        (Decimal('1e-10'), Decimal('1e10'), Decimal('-1e20')),
        # Negative discriminant case
        (Decimal('1'), Decimal('1'), Decimal('1')),
        # Very large numbers
        (Decimal('1e6'), Decimal('-1e12'), Decimal('1e18'))
    ]
    
    for i, (a, b, c) in enumerate(test_cases):
        try:
            result = solve_quadratic(a, b, c)
            assert isinstance(result, Decimal), f"Test case {i+1}: Expected Decimal, got {type(result)}"
            print(f"✅ Test case {i+1}: {result} (type: {type(result)})")
        except Exception as e:
            print(f"❌ Test case {i+1} failed: {e}")
            return False
    
    print("✅ solve_quadratic handles all edge cases correctly")
    return True

def test_end_to_end_integration():
    """Test complete end-to-end integration from parameter conversion through autofill."""
    print("\nTesting end-to-end integration...")
    
    try:
        # 1. Parameter conversion (batch runner)
        params = get_default_engine_params()
        decimal_params = convert_engine_params_to_decimals(params)
        
        # 2. Engine state setup
        state = {
            'binaries': [
                {
                    'outcome_i': 0,
                    'L': 1000.0,
                    'q_yes': 490.0,  # Close to limit scenario
                    'q_no': 400.0,
                    'virtual_yes': 0.0,
                    'V': 0.0,
                    'subsidy': 1000.0,
                    'seigniorage': 0.0,
                    'active': True,
                    'lob_pools': {
                        'YES': {'buy': {49: {'volume': 10.0, 'shares': {'user1': 10.0}}}, 'sell': {}},
                        'NO': {'buy': {}, 'sell': {}}
                    }
                }
            ],
            'pre_sum_yes': 0.89
        }
        
        # 3. Market order that triggers AMM math
        orders = [{
            'order_id': 'test-order-1',
            'user_id': 'test-user-1',
            'outcome_i': 0,
            'yes_no': 'YES',
            'type': 'MARKET',
            'is_buy': True,
            'size': Decimal('10'),
            'limit_price': None,
            'max_slippage': None,
            'af_opt_in': True,
            'ts_ms': 1000
        }]
        
        # 4. Process through engine (this calls AMM math which uses solve_quadratic)
        fills, new_state, events = apply_orders(state, orders, decimal_params, 1000)
        
        # 5. Verify no type errors and proper Decimal usage
        for fill in fills:
            assert isinstance(fill['price'], Decimal)
            assert isinstance(fill['size'], Decimal)
            assert isinstance(fill['fee'], Decimal)
        
        print(f"✅ End-to-end integration successful: {len(fills)} fills, {len(events)} events")
        print("✅ All type conversions work correctly throughout the pipeline")
        return True
        
    except Exception as e:
        print(f"❌ End-to-end integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run comprehensive integration tests."""
    print("=== Comprehensive Integration Test for Autofill Type Fixes ===\n")
    
    tests = [
        test_batch_runner_parameter_conversion,
        test_solve_quadratic_edge_cases,
        test_engine_integration_with_decimal_params,
        test_autofill_integration_with_decimal_params,
        test_end_to_end_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n=== Integration Test Results: {passed}/{total} passed ===")
    
    if passed == total:
        print("🎉 All integration tests passed! The autofill type fixes are working correctly.")
        print("✅ Batch runner → Engine → AMM Math → Autofill pipeline is fully functional")
        print("✅ No more Decimal/float type errors or string/abs() issues")
    else:
        print("⚠️ Some integration tests failed. Additional fixes may be needed.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
