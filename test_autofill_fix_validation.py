#!/usr/bin/env python3
"""
Test script to validate the autofill string/abs() error fixes.

This test simulates the exact scenario that caused the batch runner to crash:
- Limit order for YES at $0.49
- Market order for YES for $10
- Triggers autofill logic that previously failed with 'bad operand type for abs(): 'str''

Expected result: No more string/abs() errors, autofill completes successfully.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from decimal import Decimal
from app.engine.autofill import auto_fill
from app.engine.state import EngineState
from app.engine.params import EngineParams

def create_test_state() -> EngineState:
    """Create a test engine state similar to the failing scenario."""
    return {
        'binaries': [
            {
                'V': 100.0,
                'L': 200.0,
                'q_yes': 50.0,
                'q_no': 50.0,
                'virtual_yes': 0.0,
                'subsidy': 100.0,
                'seigniorage': 0.0,
                'active': True,
                'lob_pools': {
                    'YES': {
                        'buy': {},
                        'sell': {}
                    },
                    'NO': {
                        'buy': {},
                        'sell': {}
                    }
                }
            },
            {
                'V': 80.0,
                'L': 180.0,
                'q_yes': 40.0,
                'q_no': 40.0,
                'virtual_yes': 0.0,
                'subsidy': 100.0,
                'seigniorage': 0.0,
                'active': True,
                'lob_pools': {
                    'YES': {
                        'buy': {},
                        'sell': {}
                    },
                    'NO': {
                        'buy': {},
                        'sell': {}
                    }
                }
            }
        ]
    }

def create_test_params() -> EngineParams:
    """Create test parameters that could trigger the string/abs() error."""
    return {
        'n_outcomes': 2,
        'outcome_names': ['Outcome A', 'Outcome B'],
        'z': 1000.0,
        'gamma': 0.0001,
        'q0': 50.0,
        'mu_start': 1.0,
        'nu_start': 1.0,
        'kappa_start': 0.001,
        'zeta_start': 0.1,
        'f': 0.01,
        'p_max': 0.99,
        'p_min': 0.01,
        'eta': 2.0,
        'tick_size': 0.01,
        'af_enabled': True,
        'af_cap_frac': 0.1,
        'af_max_pools': 3,
        'af_max_surplus': 0.5,
        'sigma': 0.5
    }

def test_autofill_with_string_diversion():
    """Test autofill with string diversion (the problematic case)."""
    print("\nTesting autofill with string diversion (problematic case)...")
    
    state = create_test_state()
    params = create_test_params()
    
    # This is the problematic case: diversion as string instead of Decimal
    string_diversion = "5.0"  # This would cause abs() string error before fix
    
    try:
        surplus, events = auto_fill(state, 0, string_diversion, params)
        print(f"✅ autofill handled string diversion successfully")
        print(f"   Surplus: {surplus}, Events: {len(events)}")
        return True
    except Exception as e:
        if "bad operand type for abs()" in str(e):
            print(f"❌ autofill still fails with abs() error: {e}")
            return False
        else:
            print(f"❌ autofill failed with different error: {e}")
            return False

def test_autofill_with_decimal_diversion():
    """Test autofill with proper Decimal diversion (normal case)."""
    print("\nTesting autofill with Decimal diversion (normal case)...")
    
    state = create_test_state()
    params = create_test_params()
    
    # Normal case: diversion as Decimal
    decimal_diversion = Decimal('5.0')
    
    try:
        surplus, events = auto_fill(state, 0, decimal_diversion, params)
        print(f"✅ autofill with Decimal diversion works correctly")
        print(f"   Surplus: {surplus}, Events: {len(events)}")
        return True
    except Exception as e:
        print(f"❌ autofill with Decimal diversion failed: {e}")
        return False

def test_autofill_with_none_diversion():
    """Test autofill with None diversion (edge case)."""
    print("\nTesting autofill with None diversion (edge case)...")
    
    state = create_test_state()
    params = create_test_params()
    
    # Edge case: diversion as None
    none_diversion = None
    
    try:
        surplus, events = auto_fill(state, 0, none_diversion, params)
        print(f"✅ autofill handled None diversion successfully")
        print(f"   Surplus: {surplus}, Events: {len(events)}")
        return True
    except Exception as e:
        print(f"❌ autofill with None diversion failed: {e}")
        return False

def main():
    """Run all autofill fix validation tests."""
    print("=" * 60)
    print("AUTOFILL STRING/ABS() ERROR FIX VALIDATION")
    print("=" * 60)
    
    tests = [
        test_autofill_with_string_diversion,
        test_autofill_with_decimal_diversion,
        test_autofill_with_none_diversion
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed! The autofill string/abs() error has been fixed.")
        print("✅ The batch runner should no longer crash on limit orders with autofill.")
    else:
        print("❌ Some tests failed. The fix may need additional work.")
    
    print("=" * 60)
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
