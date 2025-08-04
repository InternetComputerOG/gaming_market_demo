#!/usr/bin/env python3

"""Debug script to test AMM behavior with a single binary (f_i = 1.0)"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.engine.state import init_state
from app.engine.amm_math import buy_cost_yes, get_effective_p_yes
from app.engine.impact_functions import apply_own_impact
from app.config import get_default_engine_params

def test_single_binary():
    """Test AMM behavior with single binary to isolate f_i effects"""
    
    # Create params for single binary
    params = get_default_engine_params()
    params['n_outcomes'] = 1  # Single binary
    
    print("=== SINGLE BINARY AMM TEST ===")
    print(f"Parameters: n_outcomes={params['n_outcomes']}, q0={params['q0']}, z={params['z']}")
    
    # Initialize state
    state = init_state(params)
    binary = state['binaries'][0]
    
    print(f"\nInitial state:")
    print(f"  V: {binary['V']}")
    print(f"  subsidy: {binary['subsidy']}")
    print(f"  L: {binary['L']}")
    print(f"  q_yes: {binary['q_yes']}")
    print(f"  q_no: {binary['q_no']}")
    print(f"  virtual_yes: {binary['virtual_yes']}")
    
    # Calculate f_i for single binary
    from app.engine.impact_functions import compute_f_i
    f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
    print(f"  f_i: {f_i}")
    
    # Get initial price
    initial_price = get_effective_p_yes(binary)
    print(f"  Initial price: {initial_price}")
    
    # Test buying smaller amount first
    print(f"\n=== BUYING 100 YES TOKENS ===")
    delta = Decimal('100')
    
    # Calculate cost
    cost_x = buy_cost_yes(binary, delta, params, f_i)
    print(f"Cost X: {cost_x}")
    
    # Apply impact
    print(f"V update: {binary['V']} + {f_i} * {cost_x} = {Decimal(str(binary['V'])) + f_i * cost_x}")
    apply_own_impact(state, 0, cost_x, True, True, f_i, params)
    
    # Update token supply (this is normally done in orders.py)
    binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + delta)
    
    # Check final state
    binary = state['binaries'][0]
    print(f"Final state:")
    print(f"  V: {binary['V']}")
    print(f"  subsidy: {binary['subsidy']}")
    print(f"  L: {binary['L']}")
    print(f"  q_yes: {binary['q_yes']}")
    print(f"  q_no: {binary['q_no']}")
    
    # Get final price
    final_price = get_effective_p_yes(binary)
    print(f"  Final price: {final_price}")
    
    # Analysis
    print(f"\n=== ANALYSIS ===")
    v_change = Decimal(str(binary['V'])) - Decimal('0')
    l_ratio = Decimal(str(binary['L'])) / Decimal('3333.33')  # Approximate initial L
    token_ratio = Decimal(str(binary['q_yes'])) / Decimal('1666.67')  # Approximate initial q_yes
    price_ratio = final_price / initial_price
    
    print(f"V change: 0.0 -> {binary['V']} (added {v_change})")
    print(f"L increase ratio: {l_ratio:.6f}")
    print(f"Token increase ratio: {token_ratio:.6f}")
    print(f"Price change ratio: {price_ratio:.6f}")
    
    if final_price > initial_price:
        print("✅ SUCCESS: Price INCREASED after buying tokens!")
    else:
        print("❌ PROBLEM: Price DECREASED after buying tokens!")
    
    return final_price > initial_price

if __name__ == "__main__":
    success = test_single_binary()
    print(f"\nResult: {'PASS' if success else 'FAIL'}")
