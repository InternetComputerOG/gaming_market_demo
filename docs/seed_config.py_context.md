# seed_config.py_context.md

## Overview
Script to seed initial EngineParams into DB config table as JSONB, using defaults with optional CLI overrides for session reset/demo setup per impl plan §11 and data model (status='DRAFT', start_ts=None, current_tick=0).

## Key Exports/Interfaces
- `def seed_config(overrides: Dict[str, Any] = None) -> None`: Applies overrides to default params, upserts via update_config; prints success.
- CLI entry: Uses argparse for params like --n_outcomes (int), --z (float), ..., --res_schedule (str JSON list); parses and calls seed_config.

## Dependencies/Imports
- From typing: Dict, Any; json; argparse.
- From app.config: EngineParams, get_default_engine_params.
- From app.db.queries: load_config, update_config.
- Interactions: Loads defaults from config.py; upserts params dict to DB config JSONB; no state/engine calls.

## Usage Notes
- Aligns with TDD defaults (e.g., n_outcomes=3, z=10000.0); handles JSON string args for lists (e.g., res_schedule); warns on invalid keys. Run as python seed_config.py --key value for overrides. JSONB-compatible floats/ints/lists.

## Edge Cases/Invariants
- No existing config: Uses full defaults. Invalid override: Warns but proceeds. JSON parse errors: Argparse fails. Deterministic: Defaults fixed, overrides explicit. Assumes DB access; no validation beyond type hints.