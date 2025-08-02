# 1_context.md

# .env Context

## Overview
Static configuration file containing environment variables for the Gaming Market Demo, including admin authentication and Supabase database connections. Loaded by config.py to initialize app settings, enabling secure and configurable access to Supabase Postgres and Realtime features as per Implementation Plan section 9.

## Key Exports/Interfaces
- No code exports; key-value pairs:
  - ADMIN_PASSWORD: String for admin dashboard access (placeholder: your_admin_password_here).
  - SUPABASE_URL: URL for Supabase project (e.g., https://your_project_id.supabase.co).
  - SUPABASE_SERVICE_KEY: Service key for Supabase authentication.
  - DATABASE_URL: Postgres connection string (e.g., postgresql://postgres:your_password@db.your_project_id.supabase.co:5432/postgres).
- Format: Simple .env file with # comments for explanations.

## Dependencies/Imports
- No imports; referenced in config.py via dotenv.load_dotenv() or similar to set os.environ.
- Interacts with: config.py (loads vars), db/queries.py (uses DATABASE_URL for connections), services/realtime.py (uses SUPABASE_URL and SERVICE_KEY for Realtime channels).

## Usage Notes
- Use placeholders for sensitive values; no hard-coded secrets in code.
- Essential for demo setup: ADMIN_PASSWORD for Streamlit admin protection; Supabase vars for DB persistence and realtime updates (e.g., 'demo' channel).
- Tie to Implan: Supports section 9 env vars; ensure vars are set before running streamlit_app.py or runners.

## Edge Cases/Invariants
- Missing vars cause connection failures; assume demo-level security (no production encryption).
- Invariants: URLs must be valid Supabase endpoints; password non-empty string.
- For tests: Mock env vars in unit tests if needed, but no direct tests for this file.

# .gitignore Context

## Overview
Standard .gitignore file for Python projects, excluding build artifacts, caches, environment files, logs, and IDE-specific files to maintain clean version control. Ensures sensitive data like .env and temporary outputs (e.g., plots, exports) are not committed, aligning with demo-scale robustness per Implementation Plan section 10.

## Key Exports/Interfaces
- No code exports; static text file with ignore patterns grouped by categories (e.g., # Python, # Environment).
- Patterns include: *.pyc, __pycache__/, .env, .idea/, *.log, .pytest_cache/, *.png (for Matplotlib), htmlcov/.

## Dependencies/Imports
- No imports or dependencies; standalone file.
- Interacts with: All project files by defining what Git ignores during commits.

## Usage Notes
- Copy standard Python template and customize for demo specifics (e.g., ignore Streamlit caches, Matplotlib outputs, test coverage).
- Essential for security (excludes .env with Supabase keys) and cleanliness; apply at repo root.

## Edge Cases/Invariants
- Invariants: Always include .env and __pycache__/ to prevent leaks/cruft.
- Edge cases: Handle OS-specific files (e.g., .DS_Store); no impact on code execution or tests.

## app__init__.py_context.md

__init__.py: Makes /app a package for relative imports in the Gaming Market Demo.

# app_services__init__.py Context

## Overview
Package initializer for /app/services, exporting key service functions from submodules (e.g., orders.py, positions.py) for easy imports in UI (streamlit_app.py), runners (batch_runner.py), and scripts. Minimal file with no logic, focusing on relative imports per Implementation Plan section 11.

## Key Exports/Interfaces
- Exports: 
  - from .orders import submit_order, validate_order, cancel_order  # Order submission/validation/cancellation.
  - from .positions import update_positions, update_balances, process_payouts  # Position/balance updates, payouts handling.
  - from .ticks import process_tick_summary, update_metrics  # Tick summaries and metrics computation.
  - from .resolutions import trigger_resolution_service  # Resolution triggering and renormalization.
  - from .realtime import publish_event, subscribe_to_channel  # Realtime event publishing/subscriptions via Supabase.

## Dependencies/Imports
- No direct imports; relies on submodules for functionality.
- Interacts with: db/queries.py (via services for DB ops), engine/* (via services for deterministic calls), config.py (env vars), utils.py (validation helpers).

## Usage Notes
- Use for relative imports in higher-level modules (e.g., import services.orders.submit_order).
- Supports demo integration: Services handle validation (e.g., slippage/gas checks), engine calls (apply_orders), DB updates (JSONB state), realtime pushes per Implan section 3/6.
- Essential for batch_runner/timer_service: Call exported functions for tick/resolution processing.

## Edge Cases/Invariants
- Invariants: Exports must match submodule definitions; no runtime logic, so no edges.
- Assumptions: Submodules generated sequentially; deterministic via engine underneath.
- For tests: No direct tests; indirectly via engine/tests (e.g., mock services for integration).

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

# app_engine__init__.py_context.md

## Overview
Package initializer for /app/engine, exporting core deterministic APIs and types for the Gaming Market engine per Implementation Plan section 4. Acts as a facade for submodules implementing AMM math, state management, and features like cross-matching, auto-filling, and multi-resolution.

## Key Exports/Interfaces
- EngineState(TypedDict): Opaque dict for market state; keys: binaries (List[Dict[str, Any]] with V, L, q_yes, q_no, virtual_yes, subsidy, seigniorage, active, lob_pools (Dict[int, Dict[str, Any]] for yes_buy/yes_sell/no_buy/no_sell volumes/shares)).
- EngineParams(TypedDict): Config dict; keys: n_outcomes (int), outcome_names (List[str]), z/float, gamma/float, q0/float, mu_start/end/float, nu_start/end/float, kappa_start/end/float, zeta_start/end/float, interpolation_mode/str ('reset'/'continue'), f/float, p_max/float, p_min/float, eta/float, tick_size/float, cm_enabled/bool, f_match/float, af_enabled/bool, sigma/float, af_cap_frac/float, af_max_pools/int, af_max_surplus/float, mr_enabled/bool, res_schedule/List[int], vc_enabled/bool.
- Order(TypedDict): Order details; keys: order_id/str, user_id/str, outcome_i/int, yes_no/str, type/str, size/float, limit_price/float|None, max_slippage/float|None, af_opt_in/bool, ts_ms/int.
- Fill(TypedDict): Trade fill; keys: trade_id/str, buy_user_id/str, sell_user_id/str, outcome_i/int, yes_no/str, price/float, size/float, fee/float, tick_id/int, ts_ms/int.
- apply_orders(state: EngineState, orders: List[Order], params: EngineParams, current_time: int) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]: Processes batched orders deterministically (sorted by ts_ms/order_id), handles LOB/cross-matching/AMM/auto-fills with toggles, dynamic params interpolation, returns fills/new_state/events; per TDD derivations (quadratics, penalties, diversions).
- trigger_resolution(state: EngineState, params: EngineParams, is_final: bool, elim_outcomes: List[int]|int) -> Tuple[Dict[str, float], EngineState, List[Dict]]: Triggers resolution (intermediate/final), computes payouts from actual q_yes/q_no (excluding virtuals/q0), renormalizes virtual_yes, returns payouts/new_state/events; per TDD multi-resolution.

## Dependencies/Imports
- From typing: List, Tuple, Dict, Any, TypedDict.
- From .orders: apply_orders.
- From .resolutions: trigger_resolution.
- Interacts with: db/queries.py (JSONB state fetch/save), services/* (calls APIs), runner/batch_runner.py (invokes apply_orders in ticks), utils.py (validation/fixed-point), numpy (in submodules for quadratics/searches/interpolations).

## Usage Notes
- Pure Python, deterministic (sort orders, no randomness); use for batch ticks in runner.
- JSON-serialize state for DB; implement submodules per TDD (e.g., amm_math for solves, autofill for binary searches).
- Handle toggles (cm/af/mr_enabled) and dynamic params (linear interpolation via current_time, reset per round if 'reset').
- Essential for tests: Cover quadratics, impacts, auto-fills, renormalizations, interpolations, edges (p_max/min, zero subsidy, negative virtual cap).

## Edge Cases/Invariants
- Invariants: q_yes_eff + q_no < 2*L_i per binary (solvency), p < p_max; total risk <=z; deterministic with sorted orders; f_i >0 (zeta <1/(N_active-1)).
- Assumptions: Valid params in ranges, active outcomes in computations; no rejections (asymptotic penalties); multi-res preserves pre_sum_yes via virtuals (cap >=0 if vc_enabled).
- Edges: Empty orders (no-op), oversized trades (infinite cost/zero receive), frozen status via runner, N=3-10.

## app_engine_tests__init__.py_context.md

__init__.py for /app/engine/tests: Enables pytest discovery and relative imports for engine unit tests.

## app_runner__init__.py_context.md

This file has these contents:
```python
from .batch_runner import run_tick
from .timer_service import start_timer_service, check_resolution_times
```

## app_scripts__init__.py_context.md

Initialization for the scripts package.

This module exports utilities from the scripts submodules for easy import:

```python
from .export_csv import *
from .generate_graph import *
from .seed_config import *
```