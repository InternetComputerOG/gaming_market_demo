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
    if 'start_ts_ms' not in config:
        start_ts_ms = get_current_ms()
        config_update = {'start_ts_ms': start_ts_ms, 'status': 'RUNNING', 'current_round': 0}
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

        start_ts_ms: int = config.get('start_ts_ms', 0)
        elapsed_ms: int = get_current_ms() - start_ts_ms

        mr_enabled: bool = config.get('mr_enabled', False)
        if mr_enabled:
            current_round: int = config.get('current_round', 0)
            res_offsets: list[int] = config.get('res_offsets', [])  # offsets in seconds
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
                        # Resume trading
                        update_config({'status': 'RUNNING', 'current_round': current_round + 1})
                        print(f"Resuming trading after round {current_round}.")
                    else:
                        # Final resolution
                        update_config({'status': 'RESOLVED'})
                        print("Market resolved finally.")
        else:
            total_duration_ms: int = config.get('total_duration', 0) * 1000
            if elapsed_ms >= total_duration_ms:
                # Freeze trading
                update_config({'status': 'FROZEN'})
                print(f"Freezing trading for final resolution at elapsed {elapsed_ms} ms.")

                # Trigger final resolution
                final_winner: int = config.get('final_winner', 0)
                trigger_resolution_service(True, final_winner, elapsed_ms)
                publish_resolution_update(True, final_winner)

                # No resume, set resolved
                update_config({'status': 'RESOLVED'})
                print("Market resolved.")

        # Sleep for 1 second to check frequently but not overload
        time.sleep(1)