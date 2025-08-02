# app_db__init__.py_context.md

## Overview
Package initializer for /app/db, exporting key database query functions from queries.py to enable relative imports in services, runners, and UI modules. Supports Supabase Postgres interactions for state persistence, including JSONB for EngineState, per Implan section 5 Data Model.

## Key Exports/Interfaces
- fetch_engine_state() -> EngineState: Retrieves current market state from DB (JSONB in config/ticks).
- save_engine_state(state: EngineState): Saves updated state to DB as JSONB.
- fetch_open_orders(tick_id: int) -> List[Order]: Fetches eligible open orders since last tick.
- insert_trades(fills: List[Fill]): Inserts trade records from engine fills.
- update_orders_from_fills(fills: List[Fill]): Updates order statuses and remaining sizes.
- update_positions_and_balances(fills: List[Fill]): Adjusts user positions and balances, including gas deductions.
- update_lob_pools_from_fills(fills: List[Fill]): Updates LOB pools after matches.
- insert_tick(tick_id: int, summary: Dict): Logs tick summary (prices, volumes) as JSONB.
- insert_events(events: List[Dict]): Records events for audit/realtime.
- update_metrics(tick_id: int, volume: float, mm_risk: float, mm_profit: float): Updates metrics table.
- fetch_config() -> Dict: Retrieves session config (params JSONB).
- update_config_status(status: str): Updates market status (e.g., RUNNING/FROZEN).
- insert_user(display_name: str) -> str: Adds user, assigns user_id and starting balance.
- fetch_users() -> List[Dict]: Lists joined users.
- fetch_positions(user_id: str) -> List[Dict]: Gets user positions per outcome/yes_no.
- fetch_orders_for_user(user_id: str) -> List[Dict]: Retrieves user's open orders.
- fetch_lob_pools(outcome_i: int) -> List[Dict]: Aggregated LOB pools for UI.
- fetch_recent_trades() -> List[Dict]: Recent trades for display.
- fetch_metrics() -> List[Dict]: Metrics for graphs/exports.

## Dependencies/Imports
- From .queries: All listed functions (uses supabase-py or psycopg2 for DB ops, loaded via config.py env vars).
- Interacts with: config.py (DATABASE_URL), engine/state.py (JSONB serialization), services/* (called for DB updates in tick/resolution), runner/batch_runner.py (transactional tick ops).

## Usage Notes
- Use in services for atomic DB ops within transactions; JSONB for opaque state per Implan section 6.
- Supports realtime via events table; ensure deterministic serialization (e.g., sorted keys).
- Tie to TDD: Enforces invariants like q < L_i via engine, but DB queries assume valid data.

## Edge Cases/Invariants
- Invariants: State JSONB maintains solvency (q_yes_eff + q_no < 2*L_i); timestamps monotonic.
- Assumptions: Supabase RLS off for demo; handle no rows (e.g., empty orders); transactions rollback on errors.
- For tests: Mock these functions in engine/tests for integration; edges like zero subsidy, frozen status.