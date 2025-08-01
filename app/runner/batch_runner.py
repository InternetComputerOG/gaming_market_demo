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

    # Update positions and balances from fills
    user_deltas: Dict[str, Dict[str, Decimal]] = {}  # user_id: {'balance_delta': Decimal, 'positions': {outcome_i_yes_no: delta}}
    for fill in fills:
        buy_user = fill['buy_user_id']
        sell_user = fill['sell_user_id']
        outcome_i = fill['outcome_i']
        yes_no = fill['yes_no']
        size = fill['size']
        price = fill['price']
        fee = fill['fee']

        # Buy side
        if buy_user not in user_deltas:
            user_deltas[buy_user] = {'balance_delta': Decimal(0), 'positions': {}}
        user_deltas[buy_user]['balance_delta'] -= size * price + fee / Decimal(2)  # Assume fee split
        pos_key = f"{outcome_i}_{yes_no}"
        if pos_key not in user_deltas[buy_user]['positions']:
            user_deltas[buy_user]['positions'][pos_key] = Decimal(0)
        user_deltas[buy_user]['positions'][pos_key] += size

        # Sell side
        if sell_user not in user_deltas:
            user_deltas[sell_user] = {'balance_delta': Decimal(0), 'positions': {}}
        user_deltas[sell_user]['balance_delta'] += size * price - fee / Decimal(2)
        if pos_key not in user_deltas[sell_user]['positions']:
            user_deltas[sell_user]['positions'][pos_key] = Decimal(0)
        user_deltas[sell_user]['positions'][pos_key] -= size

    # Apply deltas to DB (update_position and update_user_balance)
    for user_id, deltas in user_deltas.items():
        for pos_key, delta in deltas['positions'].items():
            outcome_i, yes_no = pos_key.split('_')
            # Fetch current, update
            current_pos = fetch_positions(user_id=user_id)  # Assume returns list, find matching
            q_yes = Decimal(0)
            q_no = Decimal(0)
            for pos in current_pos:
                if pos['outcome_i'] == int(outcome_i) and pos['yes_no'] == yes_no:
                    if yes_no == 'YES':
                        q_yes = pos['tokens'] + delta
                    else:
                        q_no = pos['tokens'] + delta
            update_position(user_id, int(outcome_i), q_yes, q_no)
        # Update balance
        # Assume update_user_balance(user_id, deltas['balance_delta'])  # Incremental
        # But from queries, update_user_balance not explicit, assume exists or raw update

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