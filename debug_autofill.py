#!/usr/bin/env python3

from decimal import Decimal
from app.engine.autofill import auto_fill
from app.engine.state import get_binary
from app.engine.amm_math import get_effective_p_yes
from app.utils import price_value

# Create test parameters
default_params = {
    'n_outcomes': 3,
    'z': Decimal('10000.0'),
    'gamma': Decimal('0.0001'),
    'q0': Decimal('5000.0'),
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

# Create initial state
n_outcomes = default_params['n_outcomes']
z_per = default_params['z'] / Decimal(n_outcomes)
q0 = default_params['q0']
binaries = []
for i in range(1, n_outcomes + 1):
    binaries.append({
        'outcome_i': i,
        'V': Decimal('0'),
        'subsidy': z_per,
        'L': z_per,
        'q_yes': q0,
        'q_no': q0,
        'virtual_yes': Decimal('0'),
        'seigniorage': Decimal('0'),
        'active': True,
        'lob_pools': {
            'YES': {
                'buy': {},
                'sell': {},
            },
            'NO': {
                'buy': {},
                'sell': {},
            },
        },
    })
initial_state = {'binaries': binaries, 'pre_sum_yes': Decimal(n_outcomes) * (q0 / z_per)}

def add_sample_pools(binary, is_yes, is_buy, tick, volume, shares):
    side = 'YES' if is_yes else 'NO'
    direction = 'buy' if is_buy else 'sell'
    if tick not in binary['lob_pools'][side][direction]:
        binary['lob_pools'][side][direction][tick] = {'volume': Decimal('0'), 'shares': {}}
    binary['lob_pools'][side][direction][tick]['volume'] += volume
    for user, share in shares.items():
        binary['lob_pools'][side][direction][tick]['shares'][user] = binary['lob_pools'][side][direction][tick]['shares'].get(user, Decimal('0')) + share

# Set up test
binary = get_binary(initial_state, 1)
add_sample_pools(binary, True, True, 60, Decimal('1000'), {'user1': Decimal('1000')})

print('=== Debug Auto-Fill ===')
print(f'Binary index: 1')
print(f'q_yes: {binary["q_yes"]}')
print(f'q_no: {binary["q_no"]}')
print(f'L: {binary["L"]}')
print(f'V: {binary["V"]}')

current_p = get_effective_p_yes(binary)
print(f'Current p_yes: {current_p}')

print(f'Pool at tick 60: {binary["lob_pools"]["YES"]["buy"].get(60, "Not found")}')

pool_tick = price_value(Decimal('60') * default_params['tick_size'])
print(f'Pool tick value: {pool_tick}')
print(f'Current price vs pool tick: {current_p} vs {pool_tick}')
print(f'Is current_p < pool_tick? {current_p < pool_tick}')

diversion = Decimal('100')
print(f'Diversion: {diversion}')

# Call auto_fill
total_surplus, events = auto_fill(initial_state, 1, diversion, default_params)
print(f'Total surplus: {total_surplus}')
print(f'Events: {len(events)}')
for i, event in enumerate(events):
    print(f'Event {i}: {event}')
