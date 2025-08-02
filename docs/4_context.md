# 4_context.md

# realtime.py_context.md

## Overview
Service for Supabase Realtime integration, handling event publishing (e.g., TickEvent summaries, resolution updates) on 'demo' channel for live UI refreshes per impl plan §6-7. Focuses on pushing payloads with state summaries, prices, volumes, and stats.

## Key Exports/Interfaces
- `get_realtime_client() -> Client`: Returns Supabase client for realtime ops.
- `publish_event(channel: str, event_type: str, payload: Dict[str, Any]) -> None`: Broadcasts JSON payload to channel; handles errors with print logging.
- `make_tick_payload(tick_id: int) -> Dict[str, Any]`: Builds tick payload with tick_id, ts_ms, prices (per outcome: p_yes/p_no), volumes, mm_risk/profit, serialized state_summary.
- `publish_tick_update(tick_id: int) -> None`: Publishes 'tick_update' event with make_tick_payload.
- `publish_resolution_update(is_final: bool, elim_outcomes: Any) -> None`: Publishes 'resolution_update' event with is_final and elim_outcomes.

## Dependencies/Imports
- Imports: typing (Dict, Any), json, supabase (Client).
- From app.config: get_supabase_client (for client init).
- From app.db.queries: fetch_engine_state (EngineState), get_current_tick (dict with ts_ms).
- From app.utils: serialize_state (for state_summary JSON).
- Interactions: Called by runner/batch_runner.py (post-tick), timer_service.py (resolutions); UIs subscribe to 'demo' for updates; payloads JSON-compatible for DB/Supabase.

## Usage Notes
- Use 'demo' channel for all broadcasts; serialize floats for Decimal compatibility. Payloads include state summaries for deltas (fills/positions via queries in UIs). Tie to impl plan realtime: <500ms updates via WebSockets.

## Edge Cases/Invariants
- Handles empty state/tick: Default 0.0 prices/volumes. Deterministic: No random; json.dumps implicit sort. Errors logged but non-blocking. Assumes valid tick_id; prices safe_divide by L>0. For tests: Validate payloads match state (e.g., p_yes = q_yes / L).

# services_orders.py_context.md

## Overview
Service for handling order submission, validation, cancellation, and DB operations in the Gaming Market Demo. Implements order lifecycle per impl plan (gas deduction on submit, batch buffering in DB, conservative estimates for slippage/confirmation UX), tying to TDD order types/validations.

## Key Exports/Interfaces
- `class Order(TypedDict)`: {'order_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'type': str, 'is_buy': bool, 'size': Decimal, 'limit_price': Optional[Decimal], 'max_slippage': Optional[Decimal], 'af_opt_in': bool, 'ts_ms': int}.
- `submit_order(user_id: str, order_data: Dict[str, Any]) -> str`: Validates order (size, price, balance with est slippage + gas_fee), deducts gas_fee, inserts to DB for batch, publishes event; raises ValueError on invalid/frozen; returns order_id.
- `cancel_order(order_id: str, user_id: str) -> None`: Validates ownership/status, refunds unfilled via engine cancel_from_pool, updates status to CANCELED, publishes event; raises ValueError on invalid.
- `get_user_orders(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]`: Fetches user's orders from DB, filtered by status.
- `estimate_slippage(outcome_i: int, yes_no: str, size: Decimal, is_buy: bool, max_slippage: Optional[Decimal]) -> Dict[str, Any]`: Simulates apply_orders on cloned state for conservative slippage est (abstracts penalties/auto-fills), returns {'estimated_slippage': Decimal, 'would_reject': bool, 'est_cost': Decimal}.

## Dependencies/Imports
- From decimal: Decimal; typing: Dict, Any, List, Optional; typing_extensions: TypedDict.
- From app.config: get_supabase_client, get_current_config (for params/status/gas_fee).
- From app.db.queries: fetch_engine_state, update_user_balance, insert_order, update_order_status, fetch_user_orders, fetch_user_balance, fetch_user_tokens, fetch_order, get_current_params.
- From app.engine.orders: Order (EngineOrder), apply_orders.
- From app.utils: usdc_amount, price_value, validate_size, validate_price, validate_balance_buy, validate_balance_sell, get_current_ms, safe_divide.
- From app.services.realtime: publish_event.
- Interactions: Calls DB for inserts/updates/fetches; uses engine apply_orders for sim in estimate_slippage; publishes to realtime on submit/cancel; assumes batch_runner handles actual processing.

## Usage Notes
- Use Decimal for precision, usdc_amount/price_value for quantization; JSON-compatible dicts for events.
- Gas_fee deducted always (even rejection); slippage est conservative (10% buffer) for UX confirmation, simulates full flow including auto-fills if enabled.
- Deterministic: ts_ms from get_current_ms; status updates for OPEN/FILLED/REJECTED/CANCELED per batch.
- Implements TDD validations (positive size, price [0,1], sufficient balance est including gas); integrates with batch_runner for apply_orders.

## Edge Cases/Invariants
- Edges: Zero size/negative raises; frozen/resolved rejects; insufficient balance/tokens raises (conservative est); slippage > max in sim returns would_reject=True but submit may differ post-batch.
- Invariants: Gas deducted before insert; orders sorted by ts_ms in batch; balance >=0 enforced via validations; solvency via engine invariants (q_eff < L_i); deterministic fetches/sims; rejection updates status but gas lost.

# positions.py_context.md

## Overview
Service module for managing user positions, balance updates, gas deductions, and payouts in the Gaming Market Demo. Handles position tracking per user/binary (actual tokens excluding virtuals), integrates with engine state for updates, and enforces TDD invariants like q < L_i via engine; supports multi-res payouts and gas on submissions per impl plan.

## Key Exports/Interfaces
- `class Position(TypedDict)`: Dict with `position_id: str`, `user_id: str`, `outcome_i: int`, `yes_no: str`, `tokens: Decimal`.
- `fetch_user_positions(user_id: str) -> List[Dict[str, Any]]`: Fetches and quantizes user positions from DB; returns list of dicts with Position fields.
- `update_position_from_fill(fill: Dict[str, Any], state: EngineState) -> None`: Updates state q_yes/q_no and DB position from fill; increments user trade_count; validates size/tokens.
- `apply_payouts(resolution_data: Dict[str, Any], state: EngineState) -> None`: Applies payouts to balances/net_pnl, zeros positions for eliminated outcomes in state/DB; handles final unfilled returns (stubbed); updates mm_profit metric from state seigniorage.
- `deduct_gas(user_id: str, gas_fee: Decimal) -> None`: Deducts quantized gas from balance (raises if insufficient); updates total_gas metric.
- `update_balance(user_id: str, delta: Decimal) -> None`: Adds quantized delta to balance (raises if negative); used for proceeds/payouts.

## Dependencies/Imports
- From typing: List, Dict, Any; typing_extensions: TypedDict; decimal: Decimal.
- From .db.queries: fetch_positions, update_position, update_metrics, get_db.
- From .engine.state: EngineState, BinaryState, get_binary.
- From .utils: usdc_amount, validate_balance_buy/sell, validate_size, safe_divide.
- Interactions: Queries DB for CRUD on positions/users/metrics; mutates EngineState q_yes/q_no/active; calls utils for validation/quantization.

## Usage Notes
- Use Decimal via usdc_amount for 6-decimal precision (TDD USDC); DB numeric(18,6) but demo simplified.
- Atomic via direct DB calls (wrap in transactions externally for multi-op); integrate with orders.py for post-fill updates, resolutions.py for payouts.
- Gas deducted pre-order (even rejects); track in metrics for CSV/rankings per impl plan.
- JSON-compatible: Positions as dicts for serialization.

## Edge Cases/Invariants
- Invariants: Tokens >=0 post-update (raises on negative); q < L_i preserved via engine (not enforced here); actual q for payouts (exclude virtual_yes).
- Edges: Zero positions/tokens ok; insufficient balance/gas raises ValueError; multi-res burns eliminated positions/active=False; final distributes unfilled (implement lob pro-rata).
- Deterministic: No random; uses DB selects (assume sorted by queries); for tests: Cover buy/sell fills (token +/-), payouts (balance+/positions=0), gas deduct (metrics+), edges like zero delta/insufficient.

# services_resolutions.py_context.md

## Overview
Service for triggering resolutions (intermediate/final), handling payouts, state updates, and event publishing in the Gaming Market Demo. Implements automatic resolutions with freezes, eliminations, liquidity redistribution, and renormalization per TDD multi-resolution mechanics and impl plan automatic events.

## Key Exports/Interfaces
- `get_active_outcomes(state: EngineState) -> List[int]`: Returns sorted list of active outcome indices.
- `compute_pre_sum_yes(state: EngineState) -> Decimal`: Computes sum of effective p_yes across active binaries.
- `apply_payouts(payouts: Dict[str, Decimal]) -> None`: Atomically updates user balances in DB from payouts.
- `trigger_resolution_service(is_final: bool, elim_outcomes: Union[List[int], int], current_time: int) -> None`: Orchestrates resolution: loads state/params, calls engine.trigger_resolution, applies payouts, saves state, inserts events, updates metrics/status, publishes realtime.

## Dependencies/Imports
- From typing: List, Dict, Any, Union; typing_extensions: TypedDict; decimal: Decimal; supabase: Client.
- From app.config: get_supabase_client, EngineParams.
- From app.utils: get_current_ms, serialize_state, deserialize_state, usdc_amount, safe_divide.
- From app.db.queries: fetch_engine_state, save_engine_state, load_config, update_config, insert_events, update_metrics, fetch_positions, atomic_transaction.
- From app.engine.resolutions: trigger_resolution.
- From app.engine.state: EngineState.
- From app.services.realtime: publish_resolution_update.
- Interactions: Called by timer_service.py for timed triggers; updates DB config/status, state JSONB; uses engine for core logic.

## Usage Notes
- Use Decimal for precision in sums/p_yes; serialize for JSONB. Supports mr_enabled toggle (list elims intermediate, int final). Status set FROZEN then RESOLVED/RUNNING. Payouts based on actual q (not virtual). Tie to TDD: Renormalization preserves pre_sum_yes via virtual_yes adjustments, cap >=0 if vc_enabled.

## Edge Cases/Invariants
- Invariants: Actual q_yes/no < L_i preserved (engine raises on violation); virtual_yes >=0 capped; pre_sum_yes from active only; deterministic (sort elims).
- Edges: No elims/zero freed ok; negative virtual capped; no active raise; single-res (mr_enabled=False) only final; inactive elim skipped. For tests: Cover payouts reconciliation, renormalization sum preservation, edges like zero positions/subsidy.

# ticks.py_context.md

## Overview
Service for tick processing, computing summaries (prices, volumes, MM risk/profit), inserting ticks to DB, and updating metrics per impl plan §6; integrates with batch_runner for post-engine atomic ops.

## Key Exports/Interfaces
- `class Fill(TypedDict)`: Dict for trade fills with keys: trade_id (str), buy_user_id (str), sell_user_id (str), outcome_i (int), yes_no (str), price (float), size (float), fee (float), tick_id (int), ts_ms (int).
- `def compute_summary(state: EngineState, fills: List[Fill]) -> Dict[str, Any]`: Computes JSON-compatible summary with 'prices' (dict of outcome_i: {'p_yes': float, 'p_no': float, 'active': bool}), 'volume' (sum sizes), 'mm_risk' (sum subsidies), 'mm_profit' (sum seigniorage + fees), 'n_active' (int); sorts binaries by outcome_i for determinism.
- `def create_tick(state: EngineState, fills: List[Fill], tick_id: int) -> None`: Inserts tick to DB with ts_ms and summary; updates metrics with volume, mm_risk, mm_profit.

## Dependencies/Imports
- From typing: List, Dict, Any; typing_extensions: TypedDict.
- From app.utils: get_current_ms.
- From app.db.queries: insert_tick, update_metrics (get_current_tick imported but unused).
- From app.engine.state: EngineState, BinaryState, get_p_yes, get_p_no.
- Interactions: Called by runner/batch_runner.py after apply_orders; uses state for summaries per TDD state fields; DB inserts for persistence.

## Usage Notes
- Summaries JSONB-compatible (floats from Decimals); mm_risk = sum(subsidy_i), mm_profit = sum(seigniorage_i) + sum(fees) per TDD; tie to multi-res via active flags. Deterministic: Sort binaries; use in realtime.py for broadcasts.

## Edge Cases/Invariants
- Empty fills: volume=0; zero subsidies/mm_risk=0; no binaries: empty prices/n_active=0. Invariants: Prices <1 per TDD; summaries positive/non-neg; floats for JSON; assumes valid state (q_eff < L_i enforced elsewhere).

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

# timer_service.py_context.md

## Overview
Background service for monitoring real-time countdowns, triggering automatic intermediate/final resolutions, enforcing trading freezes, and updating status per impl plan §6-7 and TDD multi-resolution mechanics. Runs as a daemon thread, checking timings against config offsets/durations.

## Key Exports/Interfaces
- `start_timer_service() -> None`: Initializes start_ts_ms if unset, updates config status to 'RUNNING', launches monitor_loop thread.
- `monitor_loop() -> None`: Infinite loop: Loads config, computes elapsed_ms, checks for next resolution offset (mr_enabled) or total_duration; freezes status, calls trigger_resolution_service, publishes update, sleeps for freeze_dur, resumes or resolves status.

## Dependencies/Imports
- Imports: threading, time, typing (Dict, Any, Union).
- From app.config: EngineParams, get_supabase_client (unused directly).
- From app.utils: get_current_ms.
- From app.db.queries: load_config, update_config.
- From app.services.resolutions: trigger_resolution_service.
- From app.services.realtime: publish_resolution_update.
- Interactions: Updates config table (status, current_round, start_ts_ms); calls resolutions.py for engine triggers; publishes via realtime.py; assumes batch_runner.py pauses on 'FROZEN' status.

## Usage Notes
- Use ms timestamps for determinism; supports mr_enabled (rounds via res_offsets/elim_outcomes/freeze_durs) or single final (total_duration/final_winner). Sleep(1) for checks; publish for UI countdowns. Tie to TDD: Prepares pre_sum_yes implicitly via state; interpolates params if dynamic (but not handled here). JSON-compatible config updates.

## Edge Cases/Invariants
- Invariants: Status transitions deterministic (RUNNING -> FROZEN -> RUNNING/RESOLVED); current_round increments to len(res_offsets); elapsed_ms >= offset exact. Edges: No mr_enabled (single final); zero freeze_dur (immediate resume); t=0/end handled; no active outcomes raises in resolutions.py. Deterministic: Sort elim_outcomes if list; assumes valid config (e.g., sum(elim) = N-1). For tests: Mock time/config for trigger sims, verify status sequences/publishes.