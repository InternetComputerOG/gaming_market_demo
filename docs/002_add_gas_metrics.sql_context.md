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