import time
import threading
from decimal import Decimal
from typing import List, Dict, Any

from app.config import get_supabase_client
from app.utils import get_current_ms, safe_divide
from app.db.queries import (
    fetch_engine_state,
    save_engine_state,
    insert_trades_batch,
    update_order_status,
    fetch_open_orders,
    insert_events,
    get_current_tick,
    load_config,
    insert_tick as db_insert_tick,
    update_metrics,
)
from app.engine.orders import apply_orders, Fill, Order
from app.engine.state import EngineState
from app.engine.params import EngineParams
from app.services.ticks import compute_summary, create_tick
from app.services.realtime import publish_tick_update
from app.services.positions import update_position_from_fill

# Assume no atomic_transaction context manager; use sequential calls for demo
# If errors, manual rollback not implemented (demo-scale)

def get_status_and_config() -> Dict[str, Any]:
    config = load_config()
    return config

def run_tick():
    client = get_supabase_client()
    config = get_status_and_config()
    if config['status'] not in ['RUNNING'] or config.get('frozen', False):
        return

    start_ts_ms = config.get('start_ts', 0)  # Assume ms
    current_ms = get_current_ms()
    current_time_sec = safe_divide(Decimal(current_ms - start_ts_ms), Decimal(1000))  # seconds for interpolation

    # Fetch next tick_id (max +1)
    current_tick_data = get_current_tick()
    tick_id = (current_tick_data.get('tick_id', 0) if current_tick_data else 0) + 1

    # Fetch all open orders, sorted by ts_ms
    new_orders: List[Order] = fetch_open_orders(None)  # Assume global fetch, sorted

    state: EngineState = fetch_engine_state()
    params: EngineParams = config['params']  # TypedDict

    fills: List[Fill]
    new_state: EngineState
    events: List[Dict[str, Any]]
    fills, new_state, events = apply_orders(state, new_orders, params, int(current_time_sec))

    # Process DB updates
    insert_trades_batch(fills)

    # Update orders from events (e.g., ACCEPTED/REJECTED/FILLED)
    for event in events:
        if event['type'] in ['ORDER_ACCEPTED', 'ORDER_FILLED', 'ORDER_PARTIAL', 'ORDER_REJECTED']:
            order_id = event['order_id']
            status = event['status']  # e.g., 'FILLED'
            filled_qty = event.get('filled_qty')
            update_order_status(order_id, status, filled_qty)

    # Update positions and balances from fills using the centralized service function
    # This ensures both user positions AND engine state are updated consistently per TDD Phase 3.2
    for fill in fills:
        try:
            # Use the properly implemented service function that handles:
            # - Both buyer and seller position updates
            # - Engine state token quantity updates (q_yes, q_no)
            # - Proper fee handling per TDD specifications
            # - Balance consistency and validation
            update_position_from_fill(fill, new_state)
        except Exception as e:
            print(f"Error updating position from fill {fill['trade_id']}: {e}")
            # Continue processing other fills rather than failing the entire batch

    # lob_pools updated in state, saved below

    save_engine_state(new_state)

    # Compute summary and create tick
    summary = compute_summary(new_state, fills)
    create_tick(new_state, fills, tick_id)  # Inserts tick and updates metrics

    insert_events(events)

    publish_tick_update(tick_id)

def start_batch_runner():
    config = get_status_and_config()
    interval_ms = config['params'].get('batch_interval_ms', 1000)

    def runner_loop():
        while True:
            run_tick()
            time.sleep(interval_ms / 1000.0)

    thread = threading.Thread(target=runner_loop, daemon=True)
    thread.start()