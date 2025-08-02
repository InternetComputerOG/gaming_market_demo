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