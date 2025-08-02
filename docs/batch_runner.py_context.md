# batch_runner.py_context.md

## Overview
Module for batch processing ticks in the Gaming Market Demo, running every batch_interval_ms if status=RUNNING and not frozen; fetches orders, calls engine.apply_orders, updates DB (trades/orders/positions/state/tick/events/metrics), publishes realtime updates per impl plan §6.

## Key Exports/Interfaces
- `get_status_and_config() -> Dict[str, Any]`: Fetches config including status, start_ts, params.
- `run_tick() -> None`: Core tick logic; computes current_time, fetches orders/state, calls apply_orders, inserts trades, updates orders/status from events, computes user deltas for positions/balances (updates DB), saves state, creates tick/summary/metrics, inserts events, publishes tick_update.
- `start_batch_runner() -> None`: Starts background threading loop for run_tick at interval_ms; daemon thread.

## Dependencies/Imports
- Imports: time, threading; decimal: Decimal; typing: List, Dict, Any.
- From app.config: get_supabase_client.
- From app.utils: get_current_ms, safe_divide.
- From app.db.queries: fetch_engine_state, save_engine_state, insert_trades_batch, update_order_status, fetch_open_orders, insert_events, get_current_tick, load_config, insert_tick (aliased db_insert_tick), update_metrics; assumes update_position, fetch_positions (for deltas).
- From app.engine.orders: apply_orders, Fill, Order.
- From app.engine.state: EngineState.
- From app.engine.params: EngineParams.
- From app.services.ticks: compute_summary, create_tick.
- From app.services.realtime: publish_tick_update.
- Interactions: Calls engine.apply_orders with current_time (sec from start); DB sequential updates (no atomic_transaction); assumes update_user_balance exists or raw.

## Usage Notes
- Deterministic: Fetches open orders sorted by ts_ms; current_time = (get_current_ms() - start_ts_ms)/1000 for param interpolation.
- Handles gas: Deductions in services/orders (pre-submit), not here; rejects update status=REJECTED.
- JSONB-compatible state via save_engine_state; batch inserts for demo-scale efficiency.
- Implements TDD batch execution (LOB/cross/AMM/auto-fills in apply_orders); N_active from state.active flags.

## Edge Cases/Invariants
- No orders: Empty fills/events, still inserts tick with summary=0s.
- Frozen/resolved: Skips run_tick.
- Edges: Negative time/disc (raise per TDD); zero interval (defaults 1000ms).
- Invariants: q_eff < L_i preserved via engine; deterministic tick_id monotonic; total risk <=Z unchanged; user balances >=0 via validations elsewhere.