# streamlit_admin.py_context.md

## Overview
Streamlit script for admin dashboard in Gaming Market Demo: Password-protected UI for configuring session params, monitoring users, starting/freezing demo, manual resolutions, CSV exports, and graph viewing per impl plan §7/§13 and TDD params. Implements controls for status transitions and overrides automatic timer/resolutions.

## Key Exports/Interfaces
- No exports (script); main logic in `run_admin_app() -> None`: Handles auth, renders dashboard with form/buttons/tables; calls update_config, start_timer_service, start_batch_runner, trigger_resolution_service.
- Internal: `get_client() -> Client`: Returns Supabase client.
- `download_csv(data: List[Dict[str, Any]], filename: str) -> bytes`: Converts DataFrame to CSV bytes for downloads.

## Dependencies/Imports
- Imports: streamlit (st), typing (Dict, Any, List), supabase (Client), json, os, io, pandas (pd), matplotlib.figure (Figure).
- From app.config: get_supabase_client, EngineParams, get_default_engine_params.
- From app.db.queries: load_config, update_config, fetch_users, get_current_tick.
- From app.utils: get_current_ms.
- From app.services.realtime: publish_resolution_update.
- From app.services.resolutions: trigger_resolution_service.
- From app.scripts.export_csv: fetch_trades, fetch_metrics, export_config_csv, export_rankings_csv.
- From app.scripts.generate_graph: generate_graph.
- From app.runner.batch_runner: start_batch_runner.
- From app.runner.timer_service: start_timer_service.
- Interactions: Updates config table (params JSONB, status, start_ts_ms); fetches users/metrics; triggers resolutions/publishes; exports via scripts; starts background services on "Start Demo".

## Usage Notes
- Password from .env (ADMIN_PASSWORD); session_state for auth. Config form uses st.number_input/checkbox/selectbox/text_input for EngineParams fields/lists/toggles; validates mr_enabled elim sums. Buttons for status changes (DRAFT->RUNNING, RUNNING<->FROZEN); manual resolution if mr_enabled. Downloads via st.download_button; graph post-RESOLVED. Realtime via st.rerun on tick change. Tie to TDD: Params inputs match symbols/ranges; impl plan realtime: Poll tick for refresh (<500ms).

## Edge Cases/Invariants
- Edges: Invalid config (st.error, e.g., elim sum !=n_outcomes-1); no users (empty table); DRAFT disables controls; RESOLVED shows graph/disables buttons. Invariants: Status transitions deterministic (e.g., start sets start_ts_ms); JSON-compatible params; demo-scale (no atomicity beyond DB); auth simple (no sessions). For tests: Mock session/client, cover auth/config save/start/exports flows, validations match TDD ranges.