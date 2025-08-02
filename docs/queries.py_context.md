# queries.py_context.md

## Overview
Python module for Supabase Postgres DB interactions in Gaming Market Demo. Provides query functions for CRUD on tables (config, users, positions, orders, lob_pools, trades, ticks, events, metrics), state persistence via JSONB, and atomic transactions for tick processing per impl plan §5 and TDD state management.

## Key Exports/Interfaces
- **TypedDicts**:
  - `EngineParams`: Dict with `num_binaries: int`, `fee_rate: float`, etc. (per TDD derivations for AMM params).
  - `EngineState`: Dict with `params: EngineParams`, `binaries: List[Dict[str, Any]]` (e.g., {'v': float, 'l': float, 'q_yes': float}), `total_collateral: float` (per TDD state fields for solvency/invariants).

- **Functions**:
  - `get_db() -> Client`: Returns Supabase client.
  - `load_config() -> Dict[str, Any]`: Fetches config row, deserializes JSONB params.
  - `update_config(params: Dict[str, Any]) -> None`: Updates config params JSONB.
  - `insert_user(user_id: str, username: str, balance: float) -> None`: Inserts new user with numeric(18,6) balance.
  - `fetch_users() -> List[Dict[str, Any]]`: Returns all users.
  - `update_position(user_id: str, binary_id: int, q_yes: float, q_no: float) -> None`: Upserts position quantities.
  - `fetch_positions(user_id: Optional[str] = None) -> List[Dict[str, Any]]`: Fetches positions, filtered by user if provided.
  - `insert_order(order: Dict[str, Any]) -> str`: Inserts order, returns order_id; order dict includes binary_id, status enum, ts_ms for determinism.
  - `fetch_open_orders(binary_id: int) -> List[Dict[str, Any]]`: Fetches open orders for binary, sorted by ts_ms.
  - `update_order_status(order_id: str, status: str, filled_qty: Optional[float] = None) -> None`: Updates order status/filled_qty.
  - `insert_or_update_pool(pool: Dict[str, Any]) -> None`: Upserts LOB pool data.
  - `fetch_pools(binary_id: int) -> List[Dict[str, Any]]`: Fetches pools for binary.
  - `insert_trades_batch(trades: List[Dict[str, Any]]) -> None`: Batch inserts trades for tick efficiency.
  - `insert_tick(tick_data: Dict[str, Any]) -> int`: Inserts tick, returns tick_id; monotonic per impl batch flows.
  - `get_current_tick() -> Dict[str, Any]`: Fetches latest tick.
  - `insert_events(events: List[Dict[str, Any]]) -> None`: Batch inserts events.
  - `update_metrics(metrics: Dict[str, Any]) -> None`: Upserts metrics.
  - `fetch_engine_state() -> EngineState`: Deserializes state JSONB from config.
  - `save_engine_state(state: EngineState) -> None`: Serializes and updates state JSONB.
  - `atomic_transaction(queries: List[str]) -> None`: Executes raw SQL in transaction for atomic tick ops (e.g., update_positions_and_balances).

## Dependencies/Imports
- `from typing import List, Dict, Any, Optional`
- `from typing_extensions import TypedDict`
- `from supabase import Client`
- `from app.config import get_supabase_client`
- Interacts with: schema.sql (table schemas/enums/indexes); used by services/* (e.g., engine.py calls fetch_engine_state), runner/* (tick batch flows); calls Supabase API for select/insert/update/upsert.

## Usage Notes
- JSONB for config.params/state serialization (dict <-> JSONB); ensure TypedDict compatibility.
- Numeric precision: Use numeric(18,6) for balances/qty per impl data model.
- Batch ops for trades/events to support demo-scale (20 users); realtime channels implied but not implemented here.
- Integration: fetch/save_engine_state for EngineState persistence; atomic_transaction wraps multi-ops for determinism/atomicity in tick processing.

## Edge Cases/Invariants
- Handle no rows: Return empty list/dict/default state.
- Determinism: Sort fetches by ts_ms/tick_id; idempotent upserts.
- Invariants: Balance >=0 enforced via DB constraints; state q < L_i via engine logic (not here); solvency preserved in transactions.
- TDD tie-in: Supports AMM quadratics/cross-matching via fetch_open_orders/insert_trades; unit-testable queries (e.g., mock client for isolation).