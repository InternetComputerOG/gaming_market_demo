import pytest
from decimal import Decimal
from typing import List, Dict, Any, Union
from unittest.mock import patch

from app.engine.resolutions import trigger_resolution
from app.engine.state import EngineState, BinaryState, init_state, get_binary, get_p_yes, get_p_no, update_subsidies
from app.engine.params import EngineParams
from app.utils import usdc_amount, price_value, safe_divide
from app.engine.amm_math import get_effective_p_yes, get_effective_p_no

@pytest.fixture
def default_params() -> EngineParams:
    return {
        'n_outcomes': 3,
        'z': Decimal('3000'),
        'gamma': Decimal('0.0001'),
        'q0': Decimal('500'),
        'mu_start': Decimal('1'),
        'mu_end': Decimal('1'),
        'nu_start': Decimal('1'),
        'nu_end': Decimal('1'),
        'kappa_start': Decimal('0.001'),
        'kappa_end': Decimal('0.001'),
        'zeta_start': Decimal('0.1'),
        'zeta_end': Decimal('0.1'),
        'f': Decimal('0.01'),
        'p_max': Decimal('0.99'),
        'p_min': Decimal('0.01'),
        'eta': Decimal('2'),
        'tick_size': Decimal('0.01'),
        'cm_enabled': True,
        'f_match': Decimal('0.005'),
        'af_enabled': True,
        'sigma': Decimal('0.5'),
        'af_cap_frac': Decimal('0.1'),
        'af_max_pools': 3,
        'af_max_surplus': Decimal('0.05'),
        'mr_enabled': True,
        'res_schedule': [1, 1],  # Eliminate 1 per round, total 2 for N=3
        'vc_enabled': True,
        'interpolation_mode': 'continue',
    }

@pytest.fixture
def initial_state(default_params: EngineParams) -> EngineState:
    return init_state(default_params)

@pytest.fixture
def mock_positions() -> List[Dict[str, Any]]:
    return [
        {'user_id': 'user1', 'outcome_i': 0, 'yes_no': 'YES', 'tokens': Decimal('100')},
        {'user_id': 'user1', 'outcome_i': 0, 'yes_no': 'NO', 'tokens': Decimal('200')},
        {'user_id': 'user2', 'outcome_i': 1, 'yes_no': 'YES', 'tokens': Decimal('150')},
        {'user_id': 'user2', 'outcome_i': 1, 'yes_no': 'NO', 'tokens': Decimal('50')},
        {'user_id': 'user3', 'outcome_i': 2, 'yes_no': 'YES', 'tokens': Decimal('300')},
        {'user_id': 'user3', 'outcome_i': 2, 'yes_no': 'NO', 'tokens': Decimal('100')},
    ]

def assert_solvency(state: EngineState):
    for binary in state['binaries']:
        if binary['active']:
            assert binary['q_yes'] + binary['q_no'] < Decimal('2') * binary['L'], "Solvency violated"

def calculate_pre_sum_yes(state: EngineState) -> Decimal:
    return sum(get_p_yes(binary) for binary in state['binaries'] if binary['active'])

@pytest.mark.parametrize("mr_enabled", [True, False])
@pytest.mark.parametrize("vc_enabled", [True, False])
def test_intermediate_resolution(default_params: EngineParams, initial_state: EngineState, mock_positions: List[Dict[str, Any]], mr_enabled: bool, vc_enabled: bool):
    default_params['mr_enabled'] = mr_enabled
    default_params['vc_enabled'] = vc_enabled
    state = init_state(default_params)
    
    # Simulate some trades to unbalance
    for binary in state['binaries']:
        binary['q_yes'] = Decimal('600')
        binary['q_no'] = Decimal('400')
        binary['V'] = Decimal('500')
        update_subsidies(state, default_params)
    
    pre_sum_yes = calculate_pre_sum_yes(state)
    
    with patch('app.engine.resolutions.fetch_positions', return_value=[p for p in mock_positions if p['outcome_i'] == 0]):
        elim_outcomes = [0] if isinstance(default_params['res_schedule'], list) and len(default_params['res_schedule']) > 0 else 0
        payouts, new_state, events = trigger_resolution(state, default_params, is_final=False, elim_outcomes=elim_outcomes)
    
    assert not new_state['binaries'][0]['active']
    assert new_state['binaries'][1]['active']
    assert new_state['binaries'][2]['active']
    
    # Check payouts for NO on eliminated
    assert payouts.get('user1', Decimal('0')) == Decimal('200')  # NO tokens for outcome 0
    
    # Freed liquidity redistributed
    binary0 = new_state['binaries'][0]
    freed = binary0['L'] - Decimal('400')  # q_no
    added_per_remaining = freed / Decimal('2')
    assert new_state['binaries'][1]['V'] == Decimal('500') + added_per_remaining
    assert new_state['binaries'][2]['V'] == Decimal('500') + added_per_remaining
    
    update_subsidies(new_state, default_params)
    
    # Renormalization
    post_sum_yes = calculate_pre_sum_yes(new_state)
    if vc_enabled:
        for i in [1, 2]:
            binary = new_state['binaries'][i]
            target_p = safe_divide(get_p_yes(binary), post_sum_yes) * pre_sum_yes
            virtual_yes = target_p * binary['L'] - binary['q_yes']
            assert binary['virtual_yes'] == max(virtual_yes, Decimal('0'))
    else:
        # Without cap, but in code it might still compute without cap
        pass
    
    new_sum_yes = sum(get_effective_p_yes(binary) for binary in new_state['binaries'] if binary['active'])
    if vc_enabled and any(b['virtual_yes'] == 0 for b in new_state['binaries'] if b['active']):
        assert new_sum_yes <= pre_sum_yes
    else:
        assert new_sum_yes == pytest.approx(pre_sum_yes, abs=Decimal('1e-6'))
    
    assert_solvency(new_state)
    assert any(e['type'] == 'ELIMINATION' for e in events)

@pytest.mark.parametrize("vc_enabled", [True, False])
def test_final_resolution(default_params: EngineParams, initial_state: EngineState, mock_positions: List[Dict[str, Any]], vc_enabled: bool):
    default_params['vc_enabled'] = vc_enabled
    state = init_state(default_params)
    
    # Simulate
    for binary in state['binaries']:
        binary['q_yes'] = Decimal('700')
        binary['q_no'] = Decimal('300')
        binary['V'] = Decimal('600')
        update_subsidies(state, default_params)
    
    with patch('app.engine.resolutions.fetch_positions', return_value=mock_positions):
        payouts, new_state, events = trigger_resolution(state, default_params, is_final=True, elim_outcomes=1)  # Winner 1
    
    # Payouts: YES for winner 1, NO for others 0 and 2
    assert payouts.get('user1', Decimal('0')) == Decimal('200')  # NO for 0
    assert payouts.get('user2', Decimal('0')) == Decimal('150') + Decimal('50')  # YES for 1 + NO for 1? Wait, NO for 1 gets 0, YES gets 1
    # Correct: For winner 1: YES_1 pays 1, NO_1 pays 0
    # For losers 0,2: YES pays 0, NO pays 1
    assert payouts['user1'] == Decimal('200')  # NO_0
    assert payouts['user2'] == Decimal('150')  # YES_1
    assert payouts['user3'] == Decimal('100')  # NO_2
    
    for binary in new_state['binaries']:
        assert not binary['active']
    
    assert_solvency(new_state)  # Though inactive
    assert any(e['type'] == 'ELIMINATION' for e in events)
    assert any(e['type'] == 'PAYOUT' for e in events)  # Assume events include payouts

def test_virtual_cap_negative(default_params: EngineParams, initial_state: EngineState, mock_positions: List[Dict[str, Any]]):
    default_params['vc_enabled'] = True
    state = init_state(default_params)
    
    # Force scenario where target virtual negative
    state['binaries'][0]['q_yes'] = Decimal('900')
    state['binaries'][1]['q_yes'] = Decimal('100')
    state['binaries'][2]['q_yes'] = Decimal('100')
    for binary in state['binaries']:
        binary['V'] = Decimal('500')
        binary['L'] = binary['V'] + Decimal('1000') / Decimal('3') - default_params['gamma'] * binary['V']
    
    pre_sum_yes = calculate_pre_sum_yes(state)
    
    with patch('app.engine.resolutions.fetch_positions', return_value=[]):
        _, new_state, _ = trigger_resolution(state, default_params, is_final=False, elim_outcomes=[0])
    
    # After elim 0, redistribute, renorm
    # High q_yes in 0 means more freed? But adjust to make one virtual negative
    for binary in new_state['binaries'][1:]:
        assert binary['virtual_yes'] >= Decimal('0')

def test_zero_positions(default_params: EngineParams, initial_state: EngineState):
    with patch('app.engine.resolutions.fetch_positions', return_value=[]):
        payouts, _, _ = trigger_resolution(initial_state, default_params, is_final=True, elim_outcomes=0)
    
    assert not payouts

def test_single_resolution_no_mr(default_params: EngineParams, initial_state: EngineState, mock_positions: List[Dict[str, Any]]):
    default_params['mr_enabled'] = False
    state = init_state(default_params)
    
    with patch('app.engine.resolutions.fetch_positions', return_value=mock_positions):
        payouts, new_state, events = trigger_resolution(state, default_params, is_final=True, elim_outcomes=1)
    
    # Should eliminate all but 1, payouts accordingly
    assert len(payouts) > 0
    assert all(not b['active'] for b in new_state['binaries'])