# generate_graph.py_context.md

## Overview
Script to generate Matplotlib graphs for cumulative volume, MM risk (sum subsidy_i), and MM profit (fees + seigniorage) over time, using data from metrics and ticks tables per implementation plan. Runnable standalone for admin exports/UI display.

## Key Exports/Interfaces
- `generate_graph(output_path: str = None) -> None`: Fetches ticks/metrics data, computes relative times and cumulative volume, plots multi-line graph (time vs values), saves to PNG or shows; handles no-data case.

## Dependencies/Imports
- From matplotlib: pyplot as plt; numpy as np; typing: List, Dict, Any.
- From supabase: Client.
- From app.config: get_supabase_client.
- From app.db.queries: load_config.
- From app.utils: from_ms, safe_divide.
- Interactions: Queries Supabase for ticks (ts_ms, tick_id) and metrics (volume, mm_risk, mm_profit); uses np.cumsum for volume; plt for plotting. Called by streamlit_admin.py for graph viewer/exports.

## Usage Notes
- Use relative time in seconds from min ts_ms; np for efficient cumsum/array handling. Tie to TDD: MM risk = sum subsidy_i, profit = fees + seigniorage + remainings. Deterministic: Sort by tick_id; grid/legend in plot. For tests: Mock DB responses, verify arrays/plots via image diff or data asserts.

## Edge Cases/Invariants
- Edges: No ticks/metrics (print message, return); mismatched tick_ids (filter common). Invariants: Times non-negative, volumes_cum increasing; assume float precision aligns with DB numeric(18,6). Deterministic with sorted fetches.