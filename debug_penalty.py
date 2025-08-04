#!/usr/bin/env python3

from decimal import Decimal
import sys
sys.path.append('/home/aiv55/workspaces/vibeCoding/gaming-market-demo')

from app.engine.state import init_state
from app.engine.amm_math import buy_cost_yes, get_new_p_yes_after_buy
from app.engine.impact_functions import compute_f_i, compute_dynamic_params

# Create test parameters matching the test
params = {
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
    'sigma': Decimal('0.1'),
    'af_cap_frac': Decimal('0.1'),
    'af_max_pools': 3,
    'af_max_surplus': Decimal('0.05'),
    'mr_enabled': False,
    'res_schedule': [1000, 2000, 3000],
    'vc_enabled': False,
    'total_duration': 10000,
    'res_offsets': [1000, 1000, 1000],
    'freeze_durs': [100, 100, 100],
}

# Initialize state with single binary
state = init_state(params)
# Deactivate binaries 1 and 2 to test with single binary
state['binaries'][1]['active'] = False
state['binaries'][2]['active'] = False
binary = state['binaries'][0]

# Calculate initial price
from app.engine.amm_math import get_effective_p_yes
initial_p_yes = get_effective_p_yes(binary)

print(f"Initial state:")
print(f"  V: {binary['V']}")
print(f"  L: {binary['L']}")
print(f"  q_yes: {binary['q_yes']}")
print(f"  q_no: {binary['q_no']}")
print(f"  virtual_yes: {binary['virtual_yes']}")
print(f"  Initial p_yes: {initial_p_yes}")

# Compute dynamic params
dyn_params = compute_dynamic_params(params, 1000)
zeta = dyn_params['zeta']
f_i = compute_f_i(params, zeta, state)
params_dyn = {**params, **dyn_params}

# Debug f_i calculation
n_active = sum(1 for binary in state['binaries'] if binary['active'])
print(f"\nDynamic params:")
print(f"  zeta: {zeta}")
print(f"  n_active: {n_active}")
print(f"  f_i calculation: 1 - ({n_active} - 1) * {zeta} = {Decimal(1) - Decimal(n_active - 1) * zeta}")
print(f"  f_i: {f_i}")

# Test different order sizes to find when penalty triggers
test_sizes = [Decimal('1000'), Decimal('10000'), Decimal('50000'), Decimal('100000'), Decimal('500000')]

for delta in test_sizes:
    print(f"\nBuying {delta} YES tokens:")
    
    # Calculate cost
    X = buy_cost_yes(binary, delta, params_dyn, f_i)
    print(f"  Cost X: {X}")
    
    # Debug the price calculation components
    q_yes_eff = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])
    L = Decimal(binary['L'])
    new_q_yes = q_yes_eff + delta
    new_L = L + f_i * X
    
    print(f"  Initial: q_yes_eff={q_yes_eff}, L={L}")
    print(f"  After trade: new_q_yes={new_q_yes}, new_L={new_L}")
    print(f"  f_i * X = {f_i * X}")
    print(f"  Liquidity increase ratio: {new_L / L}")
    print(f"  Token increase ratio: {new_q_yes / q_yes_eff}")
    
    p_before_penalty = new_q_yes / new_L
    print(f"  Price before penalty check: {p_before_penalty}")
    print(f"  Price change: {p_before_penalty / initial_p_yes}x")
    print(f"  Penalty triggered: {p_before_penalty > params_dyn['p_max']}")
    
    if p_before_penalty > params_dyn['p_max']:
        penalty_ratio = (p_before_penalty / params_dyn['p_max']) ** params_dyn['eta']
        print(f"  Penalty ratio: {penalty_ratio}")
        X_penalized = X * penalty_ratio
        print(f"  Penalized cost: {X_penalized}")
        
        # Final price after penalty
        p_after_penalty = (q_yes_eff + delta) / (L + f_i * X_penalized)
        print(f"  Final price after penalty: {p_after_penalty}")
    
    # Detailed tracing of V and L updates
    delta_v = f_i * X  # Own impact: V += f_i * X
    new_V = binary['V'] + float(delta_v)
    
    # Calculate new subsidy: max(0, Z/N - γ * V)
    z_per_n = params['z'] / params['n_outcomes']
    new_subsidy = max(0, z_per_n - params['gamma'] * new_V)
    
    # Calculate new L: L = V + subsidy
    new_L = new_V + new_subsidy
    new_q_yes = binary['q_yes'] + delta
    
    print(f"  After trade: new_V={new_V:.4f}, new_subsidy={new_subsidy:.4f}, new_L={new_L:.4f}, new_q_yes={new_q_yes}")
    print(f"  delta_V = f_i * X = {f_i} * {X:.4f} = {delta_v:.7f}")
    print(f"  V increase ratio: {new_V / binary['V']:.6f}")
    print(f"  L increase ratio: {new_L / binary['L']:.6f}")
    print(f"  Token increase ratio: {new_q_yes / binary['q_yes']:.6f}")
    
    # Calculate price before penalty
    price_before_penalty = (new_q_yes + binary['virtual_yes']) / new_L
    print(f"  Price before penalty check: {price_before_penalty:.30f}")
    print(f"  Price change: {price_before_penalty / initial_p_yes:.30f}x")
    
    # Check if penalty triggers
    penalty_triggered = price_before_penalty > Decimal('0.99')
    print(f"  Penalty triggered: {penalty_triggered}")
    
    if penalty_triggered:
        penalty_factor = (price_before_penalty / Decimal('0.99')) ** Decimal('2.0')
        final_cost = X * penalty_factor
        final_delta_v = f_i * final_cost
        final_V = binary['V'] + float(final_delta_v)
        final_subsidy = max(0, z_per_n - params['gamma'] * final_V)
        final_L = final_V + final_subsidy
        final_price = (new_q_yes + binary['virtual_yes']) / final_L
        print(f"  Penalty factor: {penalty_factor:.6f}")
        print(f"  Final cost after penalty: {final_cost:.4f}")
        print(f"  Final V after penalty: {final_V:.4f}")
        print(f"  Final L after penalty: {final_L:.4f}")
        print(f"  Final price after penalty: {final_price:.30f}")
    else:
        final_price = price_before_penalty
        print(f"  Actual final price: {final_price:.30f}")
    
    # Calculate the actual final price using the function
    final_price = get_new_p_yes_after_buy(binary, delta, X, f_i)
    print(f"  Actual final price: {final_price}")
