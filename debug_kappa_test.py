#!/usr/bin/env python3

"""Debug script to test AMM behavior with different kappa values"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from app.engine.state import init_state
from app.engine.amm_math import buy_cost_yes, get_effective_p_yes
from app.engine.impact_functions import apply_own_impact, compute_f_i
from app.config import get_default_engine_params

def test_kappa_values():
    """Test AMM behavior with different kappa values"""
    
    kappa_values = [0.001, 0.0001, 0.00001, 0.000001]
    delta = Decimal('10000')  # Large order
    
    print("=== TESTING DIFFERENT KAPPA VALUES ===")
    print(f"Order size: {delta} tokens")
    print()
    
    for kappa in kappa_values:
        print(f"--- KAPPA = {kappa} ---")
        
        # Create params with modified kappa
        params = get_default_engine_params()
        params['n_outcomes'] = 1  # Single binary for simplicity
        params['kappa_start'] = kappa
        
        # Initialize state
        state = init_state(params)
        binary = state['binaries'][0]
        
        # Calculate f_i
        f_i = compute_f_i(params, Decimal(str(params['zeta_start'])), state)
        
        # Get initial price
        initial_price = get_effective_p_yes(binary)
        print(f"  Initial price: {initial_price:.6f}")
        
        # Calculate cost
        cost_x = buy_cost_yes(binary, delta, params, f_i)
        print(f"  Cost X: {cost_x:.2f}")
        
        # Apply impact and update tokens
        apply_own_impact(state, 0, cost_x, True, True, f_i, params)
        binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + delta)
        
        # Get final price
        final_price = get_effective_p_yes(binary)
        price_ratio = final_price / initial_price
        
        print(f"  Final price: {final_price:.6f}")
        print(f"  Price ratio: {price_ratio:.6f}")
        print(f"  L ratio: {Decimal(str(binary['L'])) / Decimal('3333.33'):.2f}")
        
        if final_price > initial_price:
            print("  ✅ Price INCREASED")
        else:
            print("  ❌ Price DECREASED")
        print()

if __name__ == "__main__":
    test_kappa_values()
