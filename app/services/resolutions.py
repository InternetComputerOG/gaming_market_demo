from typing import List, Dict, Any, Union
from typing_extensions import TypedDict
from decimal import Decimal
from supabase import Client

from app.config import get_supabase_client, EngineParams
from app.utils import get_current_ms, serialize_state, deserialize_state, usdc_amount, safe_divide
from app.db.queries import fetch_engine_state, save_engine_state, load_config, update_config, insert_events, update_metrics, fetch_positions, atomic_transaction
from app.engine.resolutions import trigger_resolution
from app.engine.state import EngineState
from app.services.realtime import publish_resolution_update

def get_active_outcomes(state: EngineState) -> List[int]:
    """Helper to get list of active outcome indices from state."""
    return [binary['outcome_i'] for binary in state['binaries'] if binary['active']]

def compute_pre_sum_yes(state: EngineState) -> Decimal:
    """Compute sum of p_yes across active binaries, per TDD renormalization."""
    pre_sum = Decimal('0')
    for binary in state['binaries']:
        if binary['active']:
            q_yes_eff = Decimal(str(binary['q_yes'])) + Decimal(str(binary['virtual_yes']))
            L_i = Decimal(str(binary['L']))
            p_yes = safe_divide(q_yes_eff, L_i)
            pre_sum += p_yes
    return pre_sum

def apply_payouts(payouts: Dict[str, Decimal]) -> None:
    """Apply payouts to user balances in DB, using atomic transaction."""
    queries = []
    for user_id, amount in payouts.items():
        quantized_amount = usdc_amount(amount)
        queries.append(f"UPDATE users SET balance = balance + {quantized_amount} WHERE user_id = '{user_id}'")
        # Zero positions for eliminated outcomes (handled in engine, but confirm)
    if queries:
        atomic_transaction(queries)

def trigger_resolution_service(is_final: bool, elim_outcomes: Union[List[int], int], current_time: int) -> None:
    """Service to trigger resolution: load state/params, call engine, apply updates, publish.
    Handles intermediate (list elims) or final (int winner); updates config status, per impl plan.
    Ties to TDD: pause, eliminate, payout NO for losers (actual q_no only), free/redistribute L_k - q_no_k equally,
    renormalize virtual_yes to preserve pre_sum_yes (target_p = old_p / post_sum * pre_sum,
    virtual = target * L - q_yes, cap >=0 if vc_enabled). Solvency: actual q < L preserved; virtual pricing only."""
    client: Client = get_supabase_client()
    
    # Load config and params with robust initialization
    config: Dict[str, Any] = load_config()
    
    # Ensure params is properly initialized with defaults
    from app.config import get_default_engine_params
    default_params = get_default_engine_params()
    
    # Robust params initialization that handles all edge cases
    if config and 'params' in config and config['params'] and isinstance(config['params'], dict):
        # Merge config params with defaults, ensuring all required keys exist
        config_params = config['params']
        params: EngineParams = default_params.copy()
        
        # Only update params that exist in both default and config
        for key, default_value in default_params.items():
            if key in config_params and config_params[key] is not None:
                try:
                    if isinstance(default_value, (int, float)):
                        params[key] = type(default_value)(config_params[key])
                    else:
                        params[key] = config_params[key]
                except (ValueError, TypeError):
                    # If conversion fails, keep default
                    params[key] = default_value
    else:
        # Config is empty, malformed, or params is missing - use defaults
        params: EngineParams = default_params.copy()
        print(f"Warning: Using default parameters in resolution service. Config params: {config.get('params', 'MISSING')}")
    
    # Debug: Print critical parameters to verify they exist
    critical_params = ['z', 'n_outcomes', 'gamma', 'q0']
    print(f"Resolution service params check:")
    for param in critical_params:
        if param in params:
            print(f"  {param}: {params[param]} (type: {type(params[param])})")
        else:
            print(f"  {param}: MISSING!")
    
    # Ensure critical parameters exist with fallbacks
    if 'z' not in params or params['z'] is None:
        params['z'] = default_params['z']
        print(f"  Fixed missing 'z' parameter with default: {params['z']}")
    
    # Check toggles
    if not params.get('mr_enabled', False) and not is_final:
        raise ValueError("Multi-resolution not enabled for intermediate resolutions")
    
    # Set status to FROZEN
    update_config({'status': 'FROZEN'})
    
    # Load state
    state: EngineState = fetch_engine_state()
    
    # Ensure determinism: sort elim_outcomes if list
    if isinstance(elim_outcomes, list):
        elim_outcomes.sort()
    
    # Call engine trigger_resolution
    payouts, updated_state, events = trigger_resolution(state, params, is_final, elim_outcomes)
    
    # Apply payouts to balances (actual amounts, not virtual)
    apply_payouts(payouts)
    
    # Save updated state (with active flags, V/L updates, virtual_yes renormalized)
    save_engine_state(updated_state)
    
    # Insert events (e.g., {'type': 'RESOLUTION', 'payload': {...}})
    ts_ms = get_current_ms()
    for event in events:
        event['ts_ms'] = ts_ms
    insert_events(events)
    
    # Update metrics (e.g., mm_risk = sum subsidies, mm_profit updated)
    metrics: Dict[str, Any] = {}
    total_subsidy = Decimal('0')
    for binary in updated_state['binaries']:
        total_subsidy += Decimal(str(binary['subsidy']))
    metrics['mm_risk'] = float(total_subsidy)
    # Assume mm_profit from seigniorage/fees accumulated in state; placeholder
    metrics['mm_profit'] = sum(float(binary.get('seigniorage', 0)) for binary in updated_state['binaries'])
    update_metrics(metrics)
    
    # Set status: RESOLVED if final, else RUNNING after freeze (freeze_durs handled in timer_service)
    new_status = 'RESOLVED' if is_final else 'RUNNING'
    update_config({'status': new_status})
    
    # Publish realtime update
    publish_resolution_update(is_final, elim_outcomes)