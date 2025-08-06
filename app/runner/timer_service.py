import threading
import time
from typing import Dict, Any, Union

from app.config import EngineParams, get_supabase_client
from app.utils import get_current_ms
from app.db.queries import load_config, update_config
from app.services.resolutions import trigger_resolution_service
from app.services.realtime import publish_resolution_update

def start_timer_service() -> None:
    """
    Starts the timer service by setting the start timestamp if not set and launching the monitor thread.
    """
    config = load_config()
    # Check if start_ts_ms exists in params (not top-level config)
    params = config.get('params', {})
    if 'start_ts_ms' not in params:
        start_ts_ms = get_current_ms()
        # Store start_ts_ms and current_round in params, not as top-level keys
        config_update = {
            'start_ts_ms': start_ts_ms,  # This will be converted to start_ts column
            'status': 'RUNNING', 
            'params': {'start_ts_ms': start_ts_ms, 'current_round': 0}
        }
        update_config(config_update)

    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()

def monitor_loop() -> None:
    """
    Background loop that monitors timings for resolutions and freezes.
    """
    while True:
        config: Dict[str, Any] = load_config()
        if config['status'] == 'RESOLVED':
            break

        # Get parameters from config['params'] with fallbacks
        params = config.get('params', {})
        
        # Get start_ts_ms from params since it's stored there now
        start_ts_ms: int = params.get('start_ts_ms', 0)
        current_ms = get_current_ms()
        elapsed_ms: int = current_ms - start_ts_ms
        
        # Debug timestamp information
        print(f"Timer debug: current_ms={current_ms}, start_ts_ms={start_ts_ms}, elapsed_ms={elapsed_ms}")
        
        # Safety check: if elapsed time seems unrealistic (more than 24 hours), skip this cycle
        max_reasonable_elapsed_ms = 24 * 60 * 60 * 1000  # 24 hours in ms
        if elapsed_ms > max_reasonable_elapsed_ms or elapsed_ms < 0:
            print(f"Warning: Unrealistic elapsed time {elapsed_ms}ms. Skipping this timer cycle.")
            time.sleep(1)
            continue

        mr_enabled: bool = params.get('mr_enabled', False)
        
        if mr_enabled:
            current_round: int = config.get('current_round', 0)
            res_offsets: list[int] = params.get('res_offsets', [])  # offsets in seconds
            if current_round < len(res_offsets):
                next_offset_ms: int = res_offsets[current_round] * 1000
                if elapsed_ms >= next_offset_ms:
                    # Freeze trading
                    update_config({'status': 'FROZEN'})
                    print(f"Freezing trading for resolution round {current_round} at elapsed {elapsed_ms} ms.")

                    elim_outcomes: Union[list[int], int]
                    elim_outcomes = config['elim_outcomes'][current_round]
                    is_final: bool = (current_round == len(res_offsets) - 1)
                    if is_final:
                        elim_outcomes = config['final_winner']

                    # Trigger resolution
                    trigger_resolution_service(is_final, elim_outcomes, elapsed_ms)
                    publish_resolution_update(is_final, elim_outcomes)

                    # Freeze duration
                    freeze_durs: list[int] = config.get('freeze_durs', [])  # in seconds
                    freeze_dur_s: float = freeze_durs[current_round] if current_round < len(freeze_durs) else 0
                    time.sleep(freeze_dur_s)
                    print(f"Freeze duration {freeze_dur_s} seconds completed for round {current_round}.")

                    if not is_final:
                        # CRITICAL FIX: Resume trading - only update specific params to avoid overwriting existing ones
                        resume_ms = get_current_ms()
                        
                        # First update status
                        update_config({'status': 'RUNNING'})
                        
                        # Then update only the specific parameters we need to change
                        # This preserves all existing parameters (zeta_start, mu_start, etc.)
                        current_config = load_config()
                        existing_params = current_config.get('params', {})
                        updated_params = existing_params.copy()
                        updated_params['current_round'] = current_round + 1
                        updated_params['round_start_ms'] = resume_ms  # Set for parameter interpolation reset mode
                        
                        update_config({'params': updated_params})
                        print(f"Resuming trading after round {current_round} with round_start_ms={resume_ms}.")
                    else:
                        # Final resolution
                        update_config({'status': 'RESOLVED'})
                        print("Market resolved finally.")
        else:
            # Get total_duration from params, not top-level config
            total_duration_s: int = params.get('total_duration', 3600)  # default 1 hour
            total_duration_ms: int = total_duration_s * 1000
            
            print(f"Timer check: elapsed={elapsed_ms}ms, total_duration={total_duration_ms}ms ({total_duration_s}s)")
            
            if elapsed_ms >= total_duration_ms:
                # Freeze trading
                update_config({'status': 'FROZEN'})
                print(f"Freezing trading for final resolution at elapsed {elapsed_ms} ms.")

                # Trigger final resolution
                final_winner: int = params.get('final_winner', 0)
                try:
                    trigger_resolution_service(True, final_winner, elapsed_ms)
                    publish_resolution_update(True, final_winner)
                    
                    # No resume, set resolved
                    update_config({'status': 'RESOLVED'})
                    print("Market resolved successfully.")
                    break  # Exit the loop after successful resolution
                    
                except Exception as e:
                    print(f"Error during resolution: {e}")
                    # Set status to RESOLVED anyway to stop the loop
                    update_config({'status': 'RESOLVED'})
                    print("Market resolution failed, but stopping timer service to prevent infinite loop.")
                    break  # Exit the loop to prevent infinite retries

        # Sleep for 1 second to check frequently but not overload
        time.sleep(1)