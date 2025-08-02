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