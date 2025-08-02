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