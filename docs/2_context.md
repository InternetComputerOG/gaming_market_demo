# 2_context.md

## config.py_context.md
## Overview
Handles loading environment variables from .env, initializing Supabase client, and providing default EngineParams for session configuration. Short utility file for centralizing config access, used across DB, services, and runners per implementation plan.

## Key Exports/Interfaces
- `load_env() -> dict[str, str]`: Loads and validates required env vars (ADMIN_PASSWORD, SUPABASE_URL, SUPABASE_SERVICE_KEY, DATABASE_URL); raises ValueError if missing.
- `get_supabase_client() -> Client`: Creates and returns Supabase client using loaded env vars.
- `class EngineParams(TypedDict)`: Defines session params per TDD (e.g., n_outcomes: int, z: float, gamma: float, q0: float, f: float, p_max: float, p_min: float, eta: float, tick_size: float, f_match: float, sigma: float, af_cap_frac: float, af_max_pools: int, af_max_surplus: float, cm_enabled: bool, af_enabled: bool, mr_enabled: bool, vc_enabled: bool, mu_start/end: float, nu_start/end: float, kappa_start/end: float, zeta_start/end: float, interpolation_mode: str, res_schedule: list[int]) plus demo fields (total_duration: int, final_winner: int, res_offsets: list[int], freeze_durs: list[int], elim_outcomes: list[list[int]], starting_balance: float, gas_fee: float, batch_interval_ms: int).
- `get_default_engine_params() -> EngineParams`: Returns default TypedDict with values per TDD defaults (e.g., n_outcomes=3, z=10000.0, gamma=0.0001) and demo settings (e.g., gas_fee=0.0, batch_interval_ms=1000).

## Dependencies/Imports
- Imports: os (path handling), dotenv (load_dotenv), typing_extensions (TypedDict), supabase (create_client, Client).
- Interactions: Provides env dict and Supabase client to db/queries.py for connections; EngineParams used in engine/params.py for interpolation, services/* for validation, runner/* for intervals; JSONB-compatible for DB storage in config table.

## Usage Notes
- Central config loader; fetch/override params from DB config table (jsonb) in production flows. Supports dynamic params per TDD addendum (start/end values, interpolation_mode 'reset'/'continue'). Use for admin config form in streamlit_admin.py. JSON-serializable for state persistence.

## Edge Cases/Invariants
- Env vars must exist or raise error; defaults ensure safe ranges (e.g., zeta_start <=1/(n_outcomes-1)). Assumes single session (no room_id); params immutable post-load for determinism. For tests: Validate TypedDict keys match TDD table; check defaults align with design (e.g., mu_start=1.0 for asymmetry).

## utils.py_context.md
## Overview
Provides general utility functions for timestamp handling, decimal precision arithmetic, input validation, state serialization, and mathematical helpers like quadratic solves, supporting deterministic computations across engine and services per implementation plan.

## Key Exports/Interfaces
- `USDC_DECIMALS: int = 6`: Constant for USDC decimal places.
- `PRICE_DECIMALS: int = 4`: Constant for price decimal places.
- `get_current_ms() -> int`: Returns current timestamp in milliseconds.
- `to_ms(ts: float) -> int`: Converts float timestamp to milliseconds.
- `from_ms(ms: int) -> float`: Converts milliseconds to float timestamp.
- `usdc_amount(amount: float | str | Decimal) -> Decimal`: Quantizes amount to USDC precision.
- `price_value(p: float | str | Decimal) -> Decimal`: Quantizes price to PRICE_DECIMALS.
- `validate_price(p: Decimal) -> None`: Raises ValueError if p not in [0,1].
- `validate_size(s: Decimal) -> None`: Raises ValueError if s <=0.
- `validate_balance_buy(balance: Decimal, size: Decimal, est_price: Decimal, gas_fee: Decimal) -> None`: Raises ValueError if balance < size * est_price + gas_fee.
- `validate_balance_sell(tokens: Decimal, size: Decimal) -> None`: Raises ValueError if tokens < size.
- `serialize_state(state: Dict[str, Any]) -> str`: JSON-serializes state, handling Decimal and numpy floats.
- `deserialize_state(json_str: str) -> Dict[str, Any]`: Deserializes JSON to dict.
- `decimal_sqrt(d: Decimal) -> Decimal`: Computes square root using mpmath; raises on negative.
- `solve_quadratic(a: Decimal, b: Decimal, c: Decimal) -> Decimal`: Solves quadratic equation (positive root); raises on negative discriminant. Implements TDD quadratic for AMM costs.
- `safe_divide(num: Decimal, den: Decimal) -> Decimal`: Divides with zero-check; raises ValueError on den=0.

## Dependencies/Imports
- Imports: json, time, decimal (getcontext), typing (Dict, Any), mpmath (mp), numpy (np).
- Interactions: Used by engine/* (e.g., quadratics in amm_math.py, sqrt in solves), services/* (validations in orders.py), db/queries.py (timestamps), runner/* (ms intervals); provides precision helpers for all Decimal ops.

## Usage Notes
- Use Decimal for all financial calcs to maintain 6-decimal USDC precision (adjusted from TDD's 18 for demo simplicity); serialize_state ensures JSONB compatibility for DB state. Employ solve_quadratic in AMM/impact functions per TDD Derivations. Validations enforce TDD invariants like positive sizes, prices in [0,1]. Timestamps in ms for batch intervals and events.

## Edge Cases/Invariants
- Assumes Decimal inputs for precision; raises on invalid (e.g., negative sqrt/discriminant, zero divide) to prevent invalid states. Deterministic: No random elements; quadratics assume positive discriminant per TDD proofs. Invariants: Quantized values prevent overflow; validations ensure sufficient funds conservatively (est_price includes slippage). For tests: Cover edges like zero size, p=0/1, negative disc, exact quantize.

## schema.sql_context.md
## Overview
Defines the Postgres schema for the Gaming Market Demo DB, including tables for config, users, positions, orders, lob_pools, trades, ticks, events, and metrics per implementation plan section 5. Provides DDL for tables, enums (e.g., status, types), indexes, and constraints like FKs, CHECKs for positives/ranges.

## Key Exports/Interfaces
- Enums: config_status_enum ('DRAFT'|'RUNNING'|'PAUSED'|'RESOLVED'|'FROZEN'), yes_no_enum ('YES'|'NO'), order_type_enum ('MARKET'|'LIMIT'), order_status_enum ('OPEN'|'FILLED'|'PARTIAL'|'CANCELED'|'REJECTED').
- Tables (key fields):
  - config: config_id (UUID PK), params (JSONB), status (enum), start_ts (TIMESTAMPTZ), current_tick (INT), created_at/updated_at (TIMESTAMPTZ DEFAULT now()).
  - users: user_id (UUID PK), display_name (TEXT), is_admin (BOOL DEFAULT FALSE), balance/net_pnl (NUMERIC(18,6) DEFAULT 0), trade_count (INT DEFAULT 0).
  - positions: position_id (UUID PK), user_id (FK), outcome_i (INT), yes_no (enum), tokens (NUMERIC(18,6) DEFAULT 0 CHECK >=0).
  - orders: order_id (UUID PK), user_id (FK), outcome_i (INT), yes_no (enum), type (enum), size (NUMERIC(18,6) CHECK >0), limit_price/max_slippage (NUMERIC(6,4) CHECK [0,1] or NULL), af_opt_in (BOOL), status (enum DEFAULT 'OPEN'), remaining (NUMERIC(18,6) CHECK >=0), tick_accepted (INT), ts_ms (BIGINT).
  - lob_pools: pool_id (UUID PK), outcome_i (INT), yes_no (enum), is_buy (BOOL), tick (INT), volume (NUMERIC(18,6) DEFAULT 0 CHECK >=0), shares (JSONB DEFAULT '{}').
  - trades: trade_id (UUID PK), outcome_i (INT), yes_no (enum), buy_user_id/sell_user_id (FK), price (NUMERIC(6,4) CHECK [0,1]), size (NUMERIC(18,6) CHECK >0), fee (NUMERIC(18,6) CHECK >=0), tick_id (INT), ts_ms (BIGINT).
  - ticks: tick_id (INT PK), ts_ms (BIGINT), summary (JSONB).
  - events: event_id (UUID PK), type (TEXT), payload (JSONB), ts_ms (BIGINT).
  - metrics: metric_id (UUID PK), tick_id (INT FK), volume/mm_risk/mm_profit (NUMERIC(18,6) CHECK >=0).
- Indexes: On orders (status, tick_accepted, user_id).

## Dependencies/Imports
- No imports (pure SQL DDL); executed via migrations (e.g., 001_initial.sql applies this).
- Interactions: Basis for db/queries.py (query wrappers); services/* use for inserts/updates; engine/state.py serializes to JSONB in config/positions.

## Usage Notes
- Use Supabase/Postgres; JSONB for flexible params (EngineParams), summary (prices/volumes), payload (events), shares (user:share dict).
- Numeric precision: (18,6) for tokens/balances, (6,4) for prices/slippage.
- Timestamps: created_at/updated_at DEFAULT now(); ts_ms as BIGINT for ms precision.
- Single session (no room_id); RLS off for demo.

## Edge Cases/Invariants
- Constraints enforce solvency (tokens >=0, size >0, prices [0,1]); FKs cascade deletes.
- Invariants: Positions/tokens non-negative; orders remaining >=0; metrics positive.
- Assumes idempotent (DROP IF EXISTS); aligns with TDD solvency (q < L_i via engine, not DB).
- For tests: Validate schema matches data model; check constraints prevent invalid inserts (e.g., negative size).

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

# 001_initial.sql_context.md

## Overview
Initial SQL migration script for Supabase (PostgreSQL) database setup in Gaming Market Demo. Creates core tables, triggers, indexes, and extensions for users, markets, orders, positions, resolutions, and ticks; supports AMM state in JSONB per TDD state management and implementation plan's persistence layer.

## Key Exports/Interfaces
- **Extensions/Functions**:
  - CREATE EXTENSION "uuid-ossp": For UUID generation.
  - FUNCTION update_timestamp(): RETURNS TRIGGER; Updates `updated_at` on row changes.

- **Tables** (with columns, types, constraints):
  | Table       | Columns                                                                 | Constraints/Defaults |
  |-------------|-------------------------------------------------------------------------|----------------------|
  | users      | id (UUID PK, default uuid_generate_v4()), username (TEXT UNIQUE NOT NULL), balance (NUMERIC(18,9) NOT NULL DEFAULT 1000.0), created_at (TIMESTAMPTZ NOT NULL DEFAULT NOW()), updated_at (TIMESTAMPTZ NOT NULL DEFAULT NOW()) | Trigger: update_users_timestamp BEFORE UPDATE. |
  | markets    | id (UUID PK, default uuid_generate_v4()), title (TEXT NOT NULL), description (TEXT), resolution_time (TIMESTAMPTZ), state (JSONB NOT NULL DEFAULT '{}'), created_at/updated_at (as above) | Trigger: update_markets_timestamp; State JSONB for AMM params {'alpha_yes': float, 'alpha_no': float, 'liquidity': float} per TDD derivations. |
  | orders     | id (UUID PK, default), user_id (UUID NOT NULL FK users ON DELETE CASCADE), market_id (UUID NOT NULL FK markets ON DELETE CASCADE), is_yes (BOOLEAN NOT NULL), amount (NUMERIC(18,9) NOT NULL), limit_price (NUMERIC(18,9)), status (TEXT NOT NULL DEFAULT 'open'), created_at/updated_at | Trigger: update_orders_timestamp. |
  | positions  | user_id (UUID NOT NULL FK users), market_id (UUID NOT NULL FK markets), shares_yes/shares_no (NUMERIC(18,9) NOT NULL DEFAULT 0), created_at/updated_at | PK (user_id, market_id); Trigger: update_positions_timestamp; ON DELETE CASCADE. |
  | resolutions| market_id (UUID PK FK markets ON DELETE CASCADE), outcome (TEXT NOT NULL), resolved_at (TIMESTAMPTZ NOT NULL DEFAULT NOW()) | - |
  | ticks      | id (UUID PK, default), timestamp (TIMESTAMPTZ NOT NULL DEFAULT NOW()), processed_orders (JSONB NOT NULL DEFAULT '[]') | Supports batch ticking per plan. |

- **Indexes**:
  - idx_orders_market_status ON orders (market_id, status)
  - idx_markets_resolution_time ON markets (resolution_time)
  - idx_positions_user_market ON positions (user_id, market_id)

## Dependencies/Imports
- Relies on PostgreSQL/Supabase environment; no external imports.
- Interacts with future files: db/queries.py for CRUD ops; engine/core.py for state serialization/deserialization to/from JSONB; assumes supabase-py client for execution.

## Usage Notes
- Use NUMERIC(18,9) for precision in balances/shares/AMM values to avoid float issues (aligns with TDD numpy usage).
- JSONB for markets.state and ticks.processed_orders enables flexible serialization of TypedDicts (MarketState, etc.) per plan.
- Script is idempotent (IF NOT EXISTS); run via Supabase dashboard/CLI for initial setup; no data seeding.
- Implements TDD solvency/invariants via DB constraints; supports cross-matching/auto-filling in future ticking logic.

## Edge Cases/Invariants
- Assumes clean DB; defaults ensure solvency (balance >=0, shares >=0).
- Invariants: Market state maintains k=alpha_yes+alpha_no constant, p in [0,1]; orders sorted deterministically for ticking.
- Edge: NULL limit_price for market orders; status transitions ('open' to 'filled/cancelled') in engine.
- Testable: Schema validation, trigger firing, FK integrity for demo-scale (20 users, batch ticks).

# 002_add_gas_metrics.sql_context.md

## Overview
SQL migration script to evolve the Supabase (Postgres) schema by adding gas metric columns to the `resolutions` table for tracking simulation costs in prediction market resolutions, as per TDD's resolution flow with gas deductions and Implementation Plan's DB evolution via migrations for demo-scale batch processing.

## Key Exports/Interfaces
- ALTER TABLE statements:
  - Adds `gas_used BIGINT DEFAULT 0`: Tracks units of gas consumed in resolution simulations (e.g., solvency checks, multi-resolution).
  - Adds `gas_price NUMERIC(18, 9) DEFAULT 0`: Simulated price per gas unit for dynamic parameters.
  - Adds `total_gas_cost NUMERIC(18, 9) DEFAULT 0`: Computed cost (gas_used * gas_price) for auto-resolution tracking.
- Transaction-wrapped (BEGIN; COMMIT;) for atomicity.
- Idempotent with `IF NOT EXISTS` to avoid errors on re-run.

## Dependencies/Imports
- Depends on `001_initial.sql`: Assumes `resolutions` table exists with JSONB state.
- Integrates with `schema.sql` for overall schema consistency.
- Used via Supabase CLI or direct execution; future queries in `db/queries.py` will reference these columns for gas metrics in engine ticks/resolutions.

## Usage Notes
- Backward-compatible: Adds non-nullable columns with defaults, no data loss.
- Tie to TDD Section Gas Metrics: Enables tracking for quadratic AMM solvency post-resolution and batch ticks.
- Implementation Plan: Supports JSONB state storage with added metrics for 20-user demo determinism; use in resolution functions to update these via DB queries.
- For tests: Verify column addition via schema introspection; test defaults on insert, updates in resolution flows.

## Edge Cases/Invariants
- Assumes no existing columns of same name; defaults ensure zero-cost for pre-migration data.
- Invariants: Numeric precision for gas_price/total_gas_cost handles fractional simulations; maintain determinism in demo runs by consistent gas calculations.
- Edge: Handle large BIGINT for high-gas resolutions; no constraints beyond defaults for flexibility in multi-resolution features.