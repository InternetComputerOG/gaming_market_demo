#!/usr/bin/env python3

"""Find the break-even point where cost ≈ token amount for realistic large order testing"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.engine.state import init_state
from app.engine.amm_math import buy_cost_yes, get_effective_p_yes
from app.engine.impact_functions import apply_own_impact, compute_f_i
from app.config import get_default_engine_params

def find_breakeven_order():
    """Find the order size where cost ≈ token amount (break-even for rational users)"""
    
    # Use default 3-binary setup like the actual test
    params = get_default_engine_params()
    
    print("=== FINDING BREAK-EVEN ORDER SIZE ===")
    print(f"Market setup: {params['n_outcomes']} binaries, q0={params['q0']:.2f}")
    
    # Initialize state
    state = init_state(params)
    binary = state['binaries'][0]
    
    # Calculate f_i for 3 binaries
    f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
    
    print(f"Initial price: {get_effective_p_yes(binary):.6f}")
    print(f"f_i: {f_i}")
    print()
    
    # Binary search for break-even point
    low = Decimal('1')
    high = Decimal('10000')
    target_ratio = Decimal('1.0')  # cost = tokens
    tolerance = Decimal('0.01')
    
    print("Searching for break-even point (cost ≈ token amount)...")
    print("Delta\t\tCost\t\tRatio\t\tFinal Price")
    print("-" * 60)
    
    best_delta = None
    best_ratio = None
    
    for _ in range(50):  # Max iterations
        delta = (low + high) / 2
        
        # Calculate cost for this delta
        cost_x = buy_cost_yes(binary, delta, params, f_i)
        ratio = cost_x / delta
        
        # Test final price after this trade
        test_state = init_state(params)
        test_binary = test_state['binaries'][0]
        apply_own_impact(test_state, 0, cost_x, True, True, f_i, params)
        test_binary['q_yes'] = float(Decimal(str(test_binary['q_yes'])) + delta)
        final_price = get_effective_p_yes(test_binary)
        
        print(f"{delta:.0f}\t\t{cost_x:.2f}\t\t{ratio:.4f}\t\t{final_price:.6f}")
        
        if abs(ratio - target_ratio) < tolerance:
            best_delta = delta
            best_ratio = ratio
            break
        elif ratio > target_ratio:
            high = delta
        else:
            low = delta
    
    print()
    if best_delta:
        print(f"✅ BREAK-EVEN FOUND:")
        print(f"   Order size: {best_delta:.0f} tokens")
        print(f"   Cost: {buy_cost_yes(binary, best_delta, params, f_i):.2f} USDC")
        print(f"   Ratio: {best_ratio:.4f} (cost/tokens)")
        print()
        
        # Test if this triggers penalty
        cost_x = buy_cost_yes(binary, best_delta, params, f_i)
        test_state = init_state(params)
        test_binary = test_state['binaries'][0]
        apply_own_impact(test_state, 0, cost_x, True, True, f_i, params)
        test_binary['q_yes'] = float(Decimal(str(test_binary['q_yes'])) + best_delta)
        final_price = get_effective_p_yes(test_binary)
        
        print(f"Final price after break-even order: {final_price:.6f}")
        print(f"p_max threshold: {params['p_max']}")
        
        if final_price > Decimal(str(params['p_max'])):
            print("✅ This order size WOULD trigger penalty mechanism!")
        else:
            print("❌ This order size would NOT trigger penalty mechanism")
            print("   Need to find smaller order that increases price to >p_max")
        
        return best_delta
    else:
        print("❌ Could not find break-even point in range")
        return None

def test_penalty_at_breakeven(delta):
    """Test penalty mechanism at the break-even order size"""
    if not delta:
        return
        
    print(f"\n=== TESTING PENALTY AT BREAK-EVEN ({delta:.0f} tokens) ===")
    
    params = get_default_engine_params()
    state = init_state(params)
    binary = state['binaries'][0]
    f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
    
    # Calculate cost and simulate the trade
    cost_x = buy_cost_yes(binary, delta, params, f_i)
    
    print(f"Order: {delta:.0f} tokens for {cost_x:.2f} USDC")
    print(f"Value ratio: {cost_x/delta:.4f} (should be ≈1.0 for rational trade)")
    
    # Apply the trade
    apply_own_impact(state, 0, cost_x, True, True, f_i, params)
    binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + delta)
    
    final_price = get_effective_p_yes(binary)
    print(f"Final price: {final_price:.6f}")
    
    # Check penalty conditions
    if final_price > Decimal(str(params['p_max'])):
        print("✅ Penalty mechanism would trigger!")
        print(f"   Price {final_price:.6f} > p_max {params['p_max']}")
    else:
        print("❌ Penalty mechanism would NOT trigger")
        print(f"   Price {final_price:.6f} ≤ p_max {params['p_max']}")
    
    return final_price

if __name__ == "__main__":
    breakeven_delta = find_breakeven_order()
    test_penalty_at_breakeven(breakeven_delta)
