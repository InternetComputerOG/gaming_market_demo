#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from decimal import Decimal
from engine.state import init_state
from engine.amm_math import buy_cost_yes, get_effective_p_yes
from engine.impact_functions import compute_f_i

# Test parameters
params = {
    'z': 1000,
    'gamma': 0.3,
    'n_outcomes': 3,
    'q0': 5000 / 3,
    'p_min': 0.01,
    'p_max': 0.99,
    'eta': 2.0,
    'f': 0.01,
    'zeta_start': 0.091,
    'mu_start': 0.1,
    'nu_start': 0.1,
    'kappa_start': 0.001,
    'res_offsets': [0, 600, 1200],
    'freeze_durs': [100, 100, 100],
}

# Initialize state with single binary
state = init_state(params)
# Deactivate binaries 1 and 2 to test with single binary
state['binaries'][1]['active'] = False
state['binaries'][2]['active'] = False
binary = state['binaries'][0]

# Calculate dynamic parameters
zeta = Decimal('0.091')
f_i = compute_f_i(params, zeta, state)

print("=== DEBUGGING V AND L UPDATES ===")
print(f"Initial state:")
print(f"  V: {binary['V']}")
print(f"  subsidy: {binary['subsidy']}")
print(f"  L: {binary['L']}")
print(f"  q_yes: {binary['q_yes']}")
print(f"  q_no: {binary['q_no']}")
print(f"  virtual_yes: {binary['virtual_yes']}")
print(f"  f_i: {f_i}")

initial_price = get_effective_p_yes(binary)
print(f"  Initial price: {initial_price}")

# Test buying 10,000 tokens
amount = Decimal('10000')
print(f"\n=== BUYING {amount} YES TOKENS ===")

# Calculate cost
cost = buy_cost_yes(binary, amount, params, f_i)
print(f"Cost X: {cost}")

# Simulate V update according to TDD: V += f_i * X
delta_v = f_i * cost
new_V = binary['V'] + float(delta_v)
print(f"V update: {binary['V']} + {f_i} * {cost} = {new_V}")

# Calculate new subsidy: max(0, Z/N - γ * V)
z_per_n = params['z'] / params['n_outcomes']
gamma = params['gamma']
new_subsidy = max(0, z_per_n - gamma * new_V)
print(f"Subsidy update: max(0, {z_per_n} - {gamma} * {new_V}) = {new_subsidy}")

# Calculate new L: L = V + subsidy
new_L = new_V + new_subsidy
print(f"L update: {new_V} + {new_subsidy} = {new_L}")

# Update token supply
new_q_yes = binary['q_yes'] + float(amount)
print(f"Token update: {binary['q_yes']} + {amount} = {new_q_yes}")

# Calculate final price
final_price = (new_q_yes + binary['virtual_yes']) / new_L
print(f"Final price: ({new_q_yes} + {binary['virtual_yes']}) / {new_L} = {final_price}")

print(f"\n=== ANALYSIS ===")
if binary['V'] > 0:
    print(f"V increase ratio: {new_V / binary['V']:.6f}")
else:
    print(f"V change: {binary['V']} -> {new_V} (from zero)")
print(f"L increase ratio: {new_L / binary['L']:.6f}")
print(f"Token increase ratio: {new_q_yes / binary['q_yes']:.6f}")
print(f"Price change ratio: {float(final_price) / float(initial_price):.6f}")

if final_price < initial_price:
    print("❌ PROBLEM: Price DECREASED after buying tokens!")
    print("This indicates a fundamental issue with the AMM design.")
else:
    print("✅ Price increased as expected")

print(f"\n=== SUBSIDY ANALYSIS ===")
print(f"Initial subsidy: {binary['subsidy']}")
print(f"New subsidy: {new_subsidy}")
print(f"Subsidy change: {new_subsidy - binary['subsidy']}")

if new_subsidy < binary['subsidy']:
    print("Subsidy decreased because V increased (γ * V term)")
    print("This causes L to grow slower than V, which is correct")
else:
    print("Subsidy stayed the same or increased")
