#!/usr/bin/env python3

from decimal import Decimal
from app.engine.state import init_state, get_binary, get_p_yes, get_p_no, update_subsidies
from app.engine.autofill import auto_fill
from app.engine.tests.test_autofill import default_params, initial_state, add_sample_pools

def debug_diversion():
    # Get test fixtures
    params = {
        'n_outcomes': 3,
        'z': Decimal('10000.0'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('10000.0') / Decimal('3') / Decimal('2'),  # (Z/N)/2 per TDD
        'f': Decimal('0.01'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'tick_size': Decimal('0.01'),
        'f_match': Decimal('0.005'),
        'sigma': Decimal('0.5'),
        'af_cap_frac': Decimal('0.1'),
        'af_max_pools': 3,
        'af_max_surplus': Decimal('0.05'),
        'cm_enabled': True,
        'af_enabled': True,
        'mr_enabled': False,
        'vc_enabled': True,
        'mu_start': Decimal('1.0'),
        'mu_end': Decimal('1.0'),
        'nu_start': Decimal('1.0'),
        'nu_end': Decimal('1.0'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.001'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.1'),
        'interpolation_mode': 'continue',
        'res_schedule': [],
        'total_duration': 3600,
    }
    
    state = init_state(params)
    binary = get_binary(state, 1)
    
    print("=== BEFORE DIVERSION ===")
    print(f"V: {binary['V']}")
    print(f"L: {binary['L']}")
    print(f"q_yes: {binary['q_yes']}")
    print(f"q_no: {binary['q_no']}")
    print(f"virtual_yes: {binary['virtual_yes']}")
    print(f"p_yes: {get_p_yes(binary)}")
    print(f"p_no: {get_p_no(binary)}")
    
    # Add pool at tick 0.60
    add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})
    pool_tick = Decimal('0.60')
    print(f"Pool tick: {pool_tick}")
    
    # Apply diversion manually to see effect
    diversion = Decimal('100')
    print(f"\n=== APPLYING DIVERSION {diversion} ===")
    
    binary['V'] = float(Decimal(str(binary['V'])) + diversion)
    update_subsidies(state, params)
    
    print(f"V: {binary['V']}")
    print(f"L: {binary['L']}")
    print(f"subsidy: {binary['subsidy']}")
    print(f"p_yes: {get_p_yes(binary)}")
    print(f"p_no: {get_p_no(binary)}")
    
    # Check if pool should be filled
    current_p = get_p_yes(binary)
    is_increase = diversion > Decimal('0')
    
    print(f"\n=== AUTO-FILL CHECK ===")
    print(f"is_increase: {is_increase}")
    print(f"current_p: {current_p}")
    print(f"pool_tick: {pool_tick}")
    print(f"Condition (is_increase and pool_tick <= current_p): {is_increase and pool_tick <= current_p}")
    print(f"Should skip pool: {is_increase and pool_tick <= current_p}")
    
    if is_increase and pool_tick > current_p:
        print("Pool should be auto-filled!")
    else:
        print("Pool should be skipped")

if __name__ == "__main__":
    debug_diversion()
