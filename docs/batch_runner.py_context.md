# batch_runner.py_context.md

## Overview
Background task module for batch processing in the Gaming Market Demo, executing ticks at configurable intervals to process open orders via the engine, update DB with fills/positions/state, compute summaries/ticks, and publish realtime updates. Implements Implan §6 batch runner with robust threading, error recovery, and health monitoring; called as daemon thread from app startup (Lines 1-50: Imports/globals/logging; 51-250: run_tick; 251-300: Stats/health funcs; 301-end: Start/stop/restart).

## Key Exports/Interfaces
- **_batch_runner_thread** (Optional[threading.Thread], Lines 20-25): Global thread for runner loop.
- **_batch_runner_active** (bool, Lines 20-25): Flag for loop control.
- **_batch_runner_stats** (Dict[str, Any], Lines 25-35): Stats dict with keys: last_tick_time (datetime), total_ticks/total_orders_processed/total_fills_generated (int), last_error (str), error_count/thread_restarts (int).
- **convert_decimals_to_floats(obj: Any) -> Any** (Lines 40-55): Recursively converts Decimals to floats for JSON serialization; returns converted obj.
- **get_status_and_config() -> Dict[str, Any]** (Lines 56-60): Loads config from DB; returns dict with 'status', 'frozen', 'params'.
- **run_tick() -> None** (Lines 61-250): Executes single tick: Checks status, fetches/transforms open orders to Order format (critical: derives is_buy from yes_no/type, Lines 90-140), calls apply_orders (if orders), inserts trades/updates statuses/positions (via update_position_from_fill)/saves state (serializable), computes summary/creates tick/inserts events/publishes update; logs stats/errors.
- **get_batch_runner_stats() -> Dict[str, Any]** (Lines 251-260): Returns copy of stats with added 'is_active' (bool), 'thread_alive' (bool), 'thread_id' (int).
- **stop_batch_runner() -> None** (Lines 261-265): Sets active=False; logs stop.
- **is_batch_runner_healthy() -> bool** (Lines 266-280): Checks active/alive and last_tick <30s; returns bool.
- **restart_batch_runner_if_needed() -> bool** (Lines 281-285): Restarts if unhealthy; returns True if restarted.
- **start_batch_runner() -> None** (Lines 286-end): Stops existing, loads interval_ms, starts daemon thread with runner_loop (while active: run_tick/sleep, error backoff up to 10 consecutive); increments restarts; raises if fails.

## Dependencies/Imports
- Imports: time/threading/decimal.Decimal/getcontext/typing (List/Dict/Any/Optional)/logging/datetime (Lines 1-10).
- From app: config (get_supabase_client), utils (get_current_ms/safe_divide), db.queries (fetch_engine_state/save_engine_state/insert_trades_batch/update_order_status/fetch_open_orders/insert_events/get_current_tick/load_config/insert_tick/update_metrics), engine.orders (apply_orders/Fill/Order), engine.state (EngineState), engine.params (EngineParams), services.ticks (compute_summary/create_tick), services.realtime (publish_tick_update), services.positions (update_position_from_fill) (Lines 11-20).
- Interactions: Fetches config/state/orders via db; transforms to engine Order (per TDD derivations); calls apply_orders for fills/state/events; updates DB via queries/services (e.g., positions from fills per TDD Phase 3.2); creates tick/summary via services.ticks; publishes via realtime. Background thread started from app init; health checked potentially by timer_service.py or admin UI.

## Usage Notes
- Implements Implan §6 pseudocode with transaction-like atomicity (but no explicit tx; assumes Supabase handles); use Decimal internally, convert to float for DB JSONB (precision loss risk); batch_interval_ms from config.params (default 1000ms); orders sorted by ts_ms implicitly via DB; transform fixes is_buy derivation (e.g., for LIMIT BUY YES: is_buy=True); position updates post-fills ensure q_yes/q_no both +=size per cross-matching assumption (tie to TDD solvency); publish even on no-activity ticks; error recovery with exp backoff/max 10 errors; daemon thread for non-blocking; stats for monitoring in admin dashboard via streamlit_admin.py.

## Edge Cases/Invariants
- Edges: No orders → fills=[], state unchanged, tick created; frozen/status not RUNNING → skip; transformation errors → skip order/continue; position update fails → log/continue/error_count++; consecutive errors >=10 → stop thread.
- Invariants: Deterministic with DB-sorted orders; total_ticks/orders/fills monotonic; state saved post-updates preserves TDD q < L_i (via engine); tick_id = max+1; positions/state consistent via update_position_from_fill (adds to both q_yes/q_no); health: last_tick >30s → unhealthy/restart.

## Inconsistencies/Possible Issues
- Always converts Decimals to floats for DB (Lines 170-180), but positions.py_context.md notes precision loss (recommend Decimal str); potential mismatch with services_orders.py_context.md Decimal internals.
- In update_position_from_fill (Lines 195-210), assumes all fills add to both q_yes/q_no (per positions.py_context.md Lines 115-118), but TDD requires only for cross-matches—over-inflation if engine generates AMM/LOB fills without distinction (check engine_orders.py; ticks.py_context.md classifies by 'source' but code ignores).
- create_tick called with raw fills (Line 235), but ticks.py_context.md normalizes/extracts events; if no snapshots, pool volume estimates inaccurate (ticks.py Lines 280-285).
- Publishes tick on every run (even empty), but streamlit_app.py_context.md polls on tick change (last_tick > current)—may cause unnecessary reruns if no activity.
- No explicit DB transaction (relies on Supabase), potential partial updates on errors (e.g., trades inserted but positions fail); add try/except rollback if possible.
- Thread restarts on unhealthy (Line 282), but no auto-start in app; integrate with streamlit_app.py init for resilience.
- Gas not handled here (deducted in services_orders.py on submit); per Implan §3, but metrics.total_gas updated in positions.py—ensure consistency if batch rejects.