import logging
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

logger = logging.getLogger(__name__)

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

def apply_payouts(payouts: Dict[str, Decimal], eliminated_outcomes: List[int] = None, is_final: bool = False) -> None:
    """Apply payouts to user balances in DB, using atomic transaction.
    Also zeros positions for eliminated outcomes as required by TDD.
    For final resolutions, distributes unfilled LOB limit orders pro-rata."""
    queries = []
    
    # Apply balance payouts
    for user_id, amount in payouts.items():
        quantized_amount = usdc_amount(amount)
        queries.append(f"UPDATE users SET balance = balance + {quantized_amount} WHERE user_id = '{user_id}'")
    
    # Zero positions for eliminated outcomes (TDD requirement)
    if eliminated_outcomes:
        for outcome_i in eliminated_outcomes:
            # Zero both YES and NO positions for eliminated outcomes
            queries.append(f"UPDATE positions SET tokens = 0 WHERE outcome_i = {outcome_i} AND yes_no = 'YES'")
            queries.append(f"UPDATE positions SET tokens = 0 WHERE outcome_i = {outcome_i} AND yes_no = 'NO'")
    
    # CRITICAL FIX: Pro-rata distribution of unfilled LOB limit orders
    # For intermediate resolutions: return unfilled limits on eliminated outcomes (TDD Section 6)
    # For final resolution: distribute all remaining unfilled limits pro-rata
    if eliminated_outcomes and not is_final:
        # INTERMEDIATE RESOLUTION: Return unfilled limits on eliminated outcomes only
        try:
            state = fetch_engine_state()
            binaries = state.get('binaries', [])
            
            # Process only eliminated outcomes
            for outcome_i in eliminated_outcomes:
                binary = next((b for b in binaries if b['outcome_i'] == outcome_i), None)
                if not binary or 'lob_pools' not in binary:
                    continue
                    
                lob_pools = binary['lob_pools']
                
                # Process YES and NO pools for this eliminated outcome
                for yes_no in ['YES', 'NO']:
                    if yes_no not in lob_pools:
                        continue
                    token_pools = lob_pools[yes_no]
                    if not isinstance(token_pools, dict):
                        continue
                        
                    # Process buy and sell pools separately
                    for is_buy_str in ['buy', 'sell']:
                        if is_buy_str not in token_pools:
                            continue
                        pools = token_pools[is_buy_str]
                        if not isinstance(pools, dict):
                            continue
                            
                        # Process each price tick pool
                        for tick_key, pool in pools.items():
                            if not isinstance(pool, dict) or not pool.get('shares'):
                                continue
                                
                            shares = pool.get('shares', {})
                            total_volume = Decimal(str(pool.get('volume', 0)))
                            
                            if total_volume <= 0 or not shares:
                                continue
                                
                            # Calculate pro-rata returns for each user in the pool
                            total_shares = sum(Decimal(str(share)) for share in shares.values())
                            if total_shares <= 0:
                                continue
                                
                            for user_id, user_shares in shares.items():
                                if user_shares <= 0:
                                    continue
                                    
                                user_shares_decimal = Decimal(str(user_shares))
                                user_return = usdc_amount((user_shares_decimal / total_shares) * total_volume)
                                payouts[user_id] = payouts.get(user_id, Decimal('0')) + user_return
                                
                            logger.info(f"Intermediate resolution: Distributed {total_volume:.4f} from eliminated outcome {outcome_i} {yes_no} {is_buy_str} pool")
                            
        except Exception as e:
            logger.error(f"Error processing intermediate LOB returns: {e}")
            # Continue with other payout processing
    
    elif is_final:
        try:
            state = fetch_engine_state()
            binaries = state.get('binaries', [])
            
            # Process each binary's LOB pools
            for binary in binaries:
                if not isinstance(binary, dict) or 'lob_pools' not in binary:
                    continue
                    
                lob_pools = binary['lob_pools']
                outcome_i = binary.get('outcome_i', 0)
                
                # Process YES and NO pools separately
                for yes_no in ['YES', 'NO']:
                    if yes_no not in lob_pools:
                        continue
                    token_pools = lob_pools[yes_no]
                    if not isinstance(token_pools, dict):
                        continue
                        
                    # Process buy and sell pools separately
                    for is_buy_str in ['buy', 'sell']:
                        if is_buy_str not in token_pools:
                            continue
                        pools = token_pools[is_buy_str]
                        if not isinstance(pools, dict):
                            continue
                            
                        # Process each price tick pool
                        for tick_key, pool in pools.items():
                            if not isinstance(pool, dict) or not pool.get('shares'):
                                continue
                                
                            shares = pool.get('shares', {})
                            total_volume = Decimal(str(pool.get('volume', 0)))
                            
                            if total_volume <= 0 or not shares:
                                continue
                                
                            # Calculate pro-rata returns for each user in the pool
                            total_shares = sum(Decimal(str(share)) for share in shares.values())
                            if total_shares <= 0:
                                continue
                                
                            for user_id, user_shares in shares.items():
                                if user_shares <= 0:
                                    continue
                                    
                                user_shares_decimal = Decimal(str(user_shares))
                                pro_rata_share = user_shares_decimal / total_shares
                                
                                # For buy pools: return USDC volume pro-rata
                                # For sell pools: return token volume pro-rata (converted to USDC at current price)
                                if is_buy_str == 'buy':
                                    # Buy pools contain USDC commitments
                                    return_amount = total_volume * pro_rata_share
                                else:
                                    # Sell pools contain token commitments - convert to USDC
                                    # Use tick price for conversion (tick_key can be int or str)
                                    tick_price = Decimal(str(tick_key)) / Decimal('100')  # Convert cents to dollars
                                    return_amount = total_volume * pro_rata_share * tick_price
                                
                                if return_amount > 0:
                                    quantized_return = usdc_amount(return_amount)
                                    queries.append(f"UPDATE users SET balance = balance + {quantized_return} WHERE user_id = '{user_id}' -- pro-rata LOB return")
                                    
            # Count pro-rata returns applied
            pro_rata_count = len([q for q in queries if 'pro-rata LOB return' in q])
            if pro_rata_count > 0:
                logger.info(f"Applied pro-rata LOB returns for final resolution to {pro_rata_count} users")
                                    
        except Exception as e:
            logger.error(f"Error applying pro-rata LOB returns: {e}")
            # Don't fail the entire resolution - continue with other payouts
    
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
    
    # Edge case validation
    if isinstance(elim_outcomes, list):
        if len(elim_outcomes) == 0:
            raise ValueError("Empty elimination list provided for intermediate resolution")
        # Ensure determinism: sort elim_outcomes
        elim_outcomes.sort()
    elif is_final and not isinstance(elim_outcomes, int):
        raise ValueError("Final resolution requires winner as single integer")
    
    # Set status to FROZEN
    update_config({'status': 'FROZEN'})
    
    # Load state
    state: EngineState = fetch_engine_state()
    
    # Validate state
    active_outcomes = get_active_outcomes(state)
    
    # Validate state has active outcomes
    if len(active_outcomes) == 0:
        raise ValueError("No active outcomes found in state")
    
    # For final resolution, ensure exactly one outcome remains or will remain
    if is_final:
        winner = elim_outcomes
        if winner not in active_outcomes:
            raise ValueError(f"Winner {winner} is not in active outcomes {active_outcomes}")
        remaining_after_elim = [o for o in active_outcomes if o != winner]
        if len(remaining_after_elim) != len(active_outcomes) - 1:
            raise ValueError("Final resolution should eliminate all but one outcome")
    
    # CRITICAL FIX: Enhanced validation for intermediate and final resolutions per TDD Section 6
    if not is_final:
        # For intermediate resolutions, validate elimination list
        if not isinstance(elim_outcomes, list):
            raise ValueError("Intermediate resolution must provide list of outcomes to eliminate")
        if len(elim_outcomes) == 0:
            raise ValueError("Intermediate resolution must eliminate at least one outcome")
        if not all(outcome in active_outcomes for outcome in elim_outcomes):
            invalid_outcomes = [o for o in elim_outcomes if o not in active_outcomes]
            raise ValueError(f"Cannot eliminate inactive outcomes: {invalid_outcomes}")
        remaining_after_elim = [o for o in active_outcomes if o not in elim_outcomes]
        if len(remaining_after_elim) < 1:
            raise ValueError(f"Intermediate resolution cannot eliminate all outcomes. Active: {active_outcomes}, Eliminating: {elim_outcomes}")
    else:
        # For final resolution, validate winner is active
        if not isinstance(elim_outcomes, int):
            raise ValueError("Final resolution must provide single winner outcome")
        winner = elim_outcomes
        if winner not in active_outcomes:
            raise ValueError(f"Final resolution winner {winner} must be an active outcome. Active: {active_outcomes}")
    
    # Call engine trigger_resolution
    payouts, updated_state, events = trigger_resolution(state, params, is_final, elim_outcomes)
    
    # Apply payouts to balances (actual amounts, not virtual) and zero eliminated positions
    eliminated_list = elim_outcomes if isinstance(elim_outcomes, list) else [o for o in get_active_outcomes(state) if o != elim_outcomes] if is_final else []
    apply_payouts(payouts, eliminated_list, is_final)
    
    # Save updated state (with active flags, V/L updates, virtual_yes renormalized)
    save_engine_state(updated_state)
    
    # Insert events (e.g., {'type': 'RESOLUTION', 'payload': {...}})
    ts_ms = get_current_ms()
    for event in events:
        event['ts_ms'] = ts_ms
    insert_events(events)
    
    # Update metrics (complete all schema fields: volume, mm_risk, mm_profit, cross_match_events)
    metrics: Dict[str, Any] = {}
    
    # Calculate mm_risk as sum of remaining subsidies
    total_subsidy = Decimal('0')
    for binary in updated_state['binaries']:
        if binary.get('active', False):  # Only count active binaries
            total_subsidy += Decimal(str(binary['subsidy']))
    metrics['mm_risk'] = float(total_subsidy)
    
    # Calculate mm_profit from seigniorage/fees accumulated in state
    total_seigniorage = sum(float(binary.get('seigniorage', 0)) for binary in updated_state['binaries'])
    metrics['mm_profit'] = total_seigniorage
    
    # Volume: sum of payout amounts (represents resolved trading volume)
    total_volume = sum(float(amount) for amount in payouts.values())
    metrics['volume'] = total_volume
    
    # Cross-match events: count resolution events (placeholder - could be enhanced)
    metrics['cross_match_events'] = len(events)
    
    update_metrics(metrics)
    
    # Set status: RESOLVED if final, else RUNNING after freeze (freeze_durs handled in timer_service)
    new_status = 'RESOLVED' if is_final else 'RUNNING'
    update_config({'status': new_status})
    
    # CRITICAL FIX: Real-time portfolio updates after resolution
    # Per Implementation Plan Section 5.3: "Real-time updates via Supabase Realtime"
    # Trigger portfolio cache invalidation for all users to show updated balances/positions
    try:
        from app.db.queries import publish_event
        
        # Publish portfolio update event to trigger cache invalidation
        # This ensures all user UIs refresh their portfolio data immediately
        portfolio_update_payload = {
            'event_type': 'RESOLUTION_COMPLETE',
            'is_final': is_final,
            'eliminated_outcomes': eliminated_list,
            'timestamp': get_current_ms()
        }
        
        # Use existing publish_event function for real-time updates
        publish_event('demo', 'PORTFOLIO_UPDATE', portfolio_update_payload)
        
        logger.info(f"Published real-time portfolio update for resolution: final={is_final}, eliminated={eliminated_list}")
        
    except Exception as e:
        # Don't fail resolution if portfolio update fails, but log the issue
        logger.warning(f"Failed to publish real-time portfolio update: {e}")
    
    # Publish standard resolution update
    publish_resolution_update(is_final, elim_outcomes)