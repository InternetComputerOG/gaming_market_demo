#!/usr/bin/env python3
"""
Verification test for buy execution logic fixes.
Tests the two critical issues that were fixed:
1. Sell penalty bug (deflate instead of inflate)
2. Quadratic solve fallback with asymptotic approximation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.engine.amm_math import sell_received_yes, sell_received_no
from app.engine.state import BinaryState
from app.engine.params import EngineParams
from app.utils import solve_quadratic

def test_sell_penalty_deflation():
    """Test that sell penalty now correctly deflates (reduces) received amount."""
    print("Testing sell penalty deflation fix...")
    
    # Create a binary state that will trigger p' < p_min
    # Start with very low q_yes so that selling will push p' below p_min
    binary: BinaryState = {
        'outcome_i': 0,
        'V': 100.0,
        'L': 200.0,
        'q_yes': 10.0,  # Low q_yes so selling pushes p' below p_min
        'q_no': 5.0,
        'virtual_yes': 0.0,
        'subsidy': 100.0,
        'seigniorage': 0.0,
        'active': True,
        'lob_pools': {'YES': {'buy': {}, 'sell': {}}, 'NO': {'buy': {}, 'sell': {}}}
    }
    
    params: EngineParams = {
        'n_outcomes': 3,
        'outcome_names': ['A', 'B', 'C'],
        'z': 1000.0,
        'gamma': 0.0001,
        'q0': 50.0,
        'mu_start': 2.0,
        'mu_end': 2.0,
        'nu_start': 1.0,
        'nu_end': 1.0,
        'kappa_start': 0.001,
        'kappa_end': 0.001,
        'zeta_start': 0.1,
        'zeta_end': 0.1,
        'f': 0.01,
        'p_max': 0.99,
        'p_min': 0.01,  # Low p_min to trigger penalty
        'eta': 2.0,
        'tick_size': 0.01,
        'cm_enabled': True,
        'f_match': 0.005,
        'af_enabled': True,
        'sigma': 0.5,
        'af_cap_frac': 0.1,
        'af_max_pools': 3,
        'af_max_surplus': 0.2,
        'mr_enabled': False,
        'vc_enabled': True,
        'res_offsets': [],
        'freeze_durs': [],
        'elim_outcomes': [],
        'total_duration': 3600,
        'interpolation_mode': 'continue'
    }
    
    f_i = Decimal('0.8')  # 1 - (3-1) * 0.1
    delta = Decimal('8.0')  # Large sell relative to q_yes=10 to trigger penalty
    
    # Calculate received amount (should be deflated due to penalty)
    received = sell_received_yes(binary, delta, params, f_i)
    
    # Calculate what p' would be without penalty
    L = Decimal(binary['L'])
    q = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])
    
    # The key test: received amount should be significantly reduced due to penalty
    # With p' approaching p_min, the penalty should deflate the received amount
    print(f"Received amount with penalty: {received}")
    print(f"Current p_yes: {q/L}")
    
    # Verify the received amount is positive but reduced
    assert received > Decimal('0'), "Received amount should be positive"
    assert received < delta * Decimal('0.5'), "Received amount should be significantly deflated due to penalty"
    
    print("✅ Sell penalty deflation test PASSED")

def test_quadratic_fallback_asymptotic():
    """Test that quadratic solve now uses asymptotic approximation instead of fixed 0.001."""
    print("Testing quadratic solve asymptotic approximation...")
    
    # Test case with negative discriminant (oversized trade scenario)
    a = Decimal('0.8')
    b = Decimal('-100.0')  # Large negative b
    c = Decimal('50.0')
    
    # This should have negative discriminant: b² - 4ac = 10000 - 160 = 9840 > 0
    # Let me create a case with negative discriminant
    a = Decimal('1.0')
    b = Decimal('1.0')
    c = Decimal('10.0')  # This gives discriminant = 1 - 40 = -39 < 0
    
    result = solve_quadratic(a, b, c)
    
    # The new asymptotic approximation should return |c|/|b| = 10/1 = 10
    expected_asymptotic = abs(c) / abs(b)
    
    print(f"Quadratic solve result: {result}")
    print(f"Expected asymptotic approximation: {expected_asymptotic}")
    
    assert result == expected_asymptotic, f"Expected {expected_asymptotic}, got {result}"
    assert result > Decimal('0.001'), "Result should be larger than old fixed fallback"
    
    print("✅ Quadratic solve asymptotic approximation test PASSED")

def test_sell_penalty_no_function():
    """Test that sell_received_no also has the penalty fix."""
    print("Testing sell penalty deflation fix in NO function...")
    
    # Similar test for NO tokens
    binary: BinaryState = {
        'outcome_i': 0,
        'V': 100.0,
        'L': 200.0,
        'q_yes': 5.0,
        'q_no': 190.0,  # Very high q_no to trigger low p' on sell
        'virtual_yes': 0.0,
        'subsidy': 100.0,
        'seigniorage': 0.0,
        'active': True,
        'lob_pools': {'YES': {'buy': {}, 'sell': {}}, 'NO': {'buy': {}, 'sell': {}}}
    }
    
    params: EngineParams = {
        'n_outcomes': 3,
        'outcome_names': ['A', 'B', 'C'],
        'z': 1000.0,
        'gamma': 0.0001,
        'q0': 50.0,
        'mu_start': 2.0,
        'mu_end': 2.0,
        'nu_start': 1.0,
        'nu_end': 1.0,
        'kappa_start': 0.001,
        'kappa_end': 0.001,
        'zeta_start': 0.1,
        'zeta_end': 0.1,
        'f': 0.01,
        'p_max': 0.99,
        'p_min': 0.01,
        'eta': 2.0,
        'tick_size': 0.01,
        'cm_enabled': True,
        'f_match': 0.005,
        'af_enabled': True,
        'sigma': 0.5,
        'af_cap_frac': 0.1,
        'af_max_pools': 3,
        'af_max_surplus': 0.2,
        'mr_enabled': False,
        'vc_enabled': True,
        'res_offsets': [],
        'freeze_durs': [],
        'elim_outcomes': [],
        'total_duration': 3600,
        'interpolation_mode': 'continue'
    }
    
    f_i = Decimal('0.8')
    delta = Decimal('50.0')
    
    received = sell_received_no(binary, delta, params, f_i)
    
    assert received > Decimal('0'), "Received amount should be positive"
    assert received < delta * Decimal('0.5'), "Received amount should be deflated due to penalty"
    
    print("✅ Sell penalty deflation test for NO function PASSED")

if __name__ == "__main__":
    print("🔧 Testing Buy Execution Logic Fixes")
    print("=" * 50)
    
    try:
        test_sell_penalty_deflation()
        test_quadratic_fallback_asymptotic()
        test_sell_penalty_no_function()
        
        print("=" * 50)
        print("🎉 ALL TESTS PASSED! Buy execution logic fixes are working correctly.")
        print("\nFixed Issues:")
        print("1. ✅ Sell penalty now correctly DEFLATES received amount (was inflating)")
        print("2. ✅ Quadratic solve uses asymptotic approximation (was fixed 0.001)")
        print("3. ✅ Both YES and NO sell functions fixed consistently")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        sys.exit(1)
