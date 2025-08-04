#!/usr/bin/env python3

"""Find the order size that triggers the penalty mechanism (price > p_max)"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.engine.state import init_state
from app.engine.amm_math import buy_cost_yes, get_effective_p_yes
from app.engine.impact_functions import apply_own_impact, compute_f_i
from app.config import get_default_engine_params

def find_penalty_trigger():
    """Find the order size that makes price > p_max to trigger penalty"""
    
    params = get_default_engine_params()
    p_max = Decimal(str(params['p_max']))
    
    print("=== FINDING PENALTY TRIGGER POINT ===")
    print(f"Target: price > p_max ({p_max})")
    print()
    
    # Binary search for penalty trigger
    low = Decimal('1')
    high = Decimal('5000')  # Start with reasonable upper bound
    
    print("Searching for penalty trigger point...")
    print("Delta\t\tCost\t\tRatio\t\tFinal Price\tTriggers?")
    print("-" * 70)
    
    best_delta = None
    
    for iteration in range(50):
        delta = (low + high) / 2
        
        # Test this delta
        state = init_state(params)
        binary = state['binaries'][0]
        f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
        
        cost_x = buy_cost_yes(binary, delta, params, f_i)
        ratio = cost_x / delta
        
        # Apply trade and check final price
        apply_own_impact(state, 0, cost_x, True, True, f_i, params)
        binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + delta)
        final_price = get_effective_p_yes(binary)
        
        triggers = "YES" if final_price > p_max else "NO"
        print(f"{delta:.0f}\t\t{cost_x:.2f}\t\t{ratio:.4f}\t\t{final_price:.6f}\t{triggers}")
        
        if final_price > p_max:
            # Found a trigger point, try to find the smallest one
            high = delta
            best_delta = delta
        else:
            # Need larger order
            low = delta
        
        # Stop if we're close enough
        if high - low < Decimal('1'):
            break
    
    if best_delta:
        print(f"\n✅ PENALTY TRIGGER FOUND:")
        print(f"   Minimum order size: {best_delta:.0f} tokens")
        
        # Test the exact trigger point
        state = init_state(params)
        binary = state['binaries'][0]
        f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
        cost_x = buy_cost_yes(binary, best_delta, params, f_i)
        
        print(f"   Cost: {cost_x:.2f} USDC")
        print(f"   Ratio: {cost_x/best_delta:.4f} (cost/tokens)")
        
        # Apply trade
        apply_own_impact(state, 0, cost_x, True, True, f_i, params)
        binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + best_delta)
        final_price = get_effective_p_yes(binary)
        
        print(f"   Final price: {final_price:.6f}")
        print(f"   Exceeds p_max: {final_price > p_max}")
        
        # Check if this is still a reasonable trade
        if cost_x / best_delta < Decimal('2.0'):
            print(f"   ✅ Still reasonable trade (ratio < 2.0)")
        else:
            print(f"   ❌ Unreasonable trade (ratio ≥ 2.0)")
            print(f"       User pays ${cost_x/best_delta:.2f} per token worth max $1")
        
        return best_delta
    else:
        print("❌ Could not find penalty trigger in reasonable range")
        return None

def test_realistic_penalty_order():
    """Test a more realistic penalty scenario"""
    
    print(f"\n=== TESTING REALISTIC PENALTY SCENARIO ===")
    
    # Try to find the largest reasonable order that still triggers penalty
    params = get_default_engine_params()
    
    # Test a range of order sizes
    test_sizes = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    
    print("Testing various order sizes:")
    print("Size\t\tCost\t\tRatio\t\tFinal Price\tReasonable?")
    print("-" * 65)
    
    best_reasonable = None
    
    for delta in test_sizes:
        delta = Decimal(str(delta))
        
        state = init_state(params)
        binary = state['binaries'][0]
        f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
        
        cost_x = buy_cost_yes(binary, delta, params, f_i)
        ratio = cost_x / delta
        
        apply_own_impact(state, 0, cost_x, True, True, f_i, params)
        binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + delta)
        final_price = get_effective_p_yes(binary)
        
        reasonable = "YES" if ratio < Decimal('1.5') else "NO"
        
        print(f"{delta:.0f}\t\t{cost_x:.2f}\t\t{ratio:.4f}\t\t{final_price:.6f}\t{reasonable}")
        
        if ratio < Decimal('1.5') and final_price > Decimal('0.8'):  # Reasonable and high impact
            best_reasonable = delta
    
    if best_reasonable:
        print(f"\n✅ BEST REASONABLE HIGH-IMPACT ORDER: {best_reasonable:.0f} tokens")
        return best_reasonable
    else:
        print(f"\n❌ No reasonable order found with high price impact")
        return None

if __name__ == "__main__":
    penalty_delta = find_penalty_trigger()
    reasonable_delta = test_realistic_penalty_order()
    
    if reasonable_delta:
        print(f"\n🎯 RECOMMENDATION:")
        print(f"   Use {reasonable_delta:.0f} tokens for realistic 'large order' test")
        print(f"   This provides high price impact while remaining economically rational")
