# 5_context.md

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

# style.css_context.md

## Overview
Static CSS file for customizing Streamlit UI to resemble Polymarket aesthetics: dark theme, green/red accents for YES/NO/Buy/Sell, rounded elements, shadows for depth. Enhances trading panels, tabs, forms, tables, and responsiveness for demo hype.

## Key Exports/Interfaces
- No exports; pure CSS selectors targeting Streamlit classes (e.g., .stTabs, .stButton, .stDataFrame) and custom elements (e.g., .countdown if added).
- Global styles: body (dark bg #1A1A1A, sans-serif), headings (white).
- Component styles:
  - Tabs: Pill-shaped, active green (#00FF00).
  - Buttons: Gray bg, primary green, hover effects.
  - Radio: Green for YES/Buy, red (#FF0000) for NO/Sell.
  - Forms: Dark padded boxes with shadows.
  - Tables: Striped dark, bid green/ask red columns.
  - Sidebar: Darker bg for leaderboard.
  - Messages: Colored for error/success.
  - Media query: Responsive for <768px.

## Dependencies/Imports
- No imports; loaded via st.markdown in streamlit_app.py and streamlit_admin.py (unsafe_allow_html=True).
- Interactions: Applies to UI elements like outcome tabs (st.tabs), order tickets (st.form), books/trades (st.table/st.dataframe), metrics (st.metric).

## Usage Notes
- Reference Polymarket: Clean, intuitive; use for tabs (outcomes), radios (YES/NO, Buy/Sell), forms (tickets with confirmation expanders), tables (books with bid/ask colors, trades/positions).
- Dark mode for hype; green/red for visual excitement per TDD user implications.
- Static file; no dynamic CSS; ensure fast load (<1KB).

## Edge Cases/Invariants
- Cross-browser: Basic styles, no prefixes needed for demo.
- Invariants: Dark theme consistent; colors reinforce YES/NO (green positive, red negative); responsive for mobile demo users.
- Deterministic: No variables; applies uniformly to all Streamlit renders.

# export_csv.py_context.md

## Overview
Script for generating CSV exports of trades, config, metrics, and user rankings (including gas costs, % gain/loss) per impl plan §7/§13, using pandas for data processing and writing.

## Key Exports/Interfaces
- `fetch_trades(client: Client) -> List[Dict[str, Any]]`: Fetches all trades from DB, sorted by ts_ms.
- `fetch_metrics(client: Client) -> List[Dict[str, Any]]`: Fetches all metrics from DB, sorted by tick_id.
- `export_trades_csv(filename: str) -> None`: Exports trades DataFrame to CSV with 6-decimal precision.
- `export_config_csv(filename: str) -> None`: Flattens config params JSONB to DataFrame and exports to CSV.
- `export_metrics_csv(filename: str) -> None`: Exports metrics DataFrame to CSV with 6-decimal precision.
- `export_rankings_csv(filename: str) -> None`: Computes user rankings (final_usdc, pnl, pct_gain_loss using safe_divide, trade_count, gas_costs = gas_fee * trade_count), sorts by pct_gain_loss descending, exports to CSV.

## Dependencies/Imports
- Imports: pandas (pd), typing (List, Dict), decimal (Decimal), supabase (Client).
- From app.config: get_supabase_client.
- From app.utils: safe_divide.
- From app.db.queries: load_config, fetch_users.
- Interactions: Uses Supabase client for table selects (trades/metrics); load_config for params; fetch_users for rankings; called by streamlit_admin.py for export buttons.

## Usage Notes
- Use Decimal for computations (balance, gas_cost, pnl), convert to float for CSV; float_format='%.6f' for USDC precision. Flatten params dict for config export. Rankings incorporate gas deductions in pnl/% gain/loss per TDD/impl fee model.

## Edge Cases/Invariants
- Empty results: Exports empty CSV. Zero starting_balance: safe_divide handles div-by-zero (returns 0). Deterministic: Sorts by ts_ms/tick_id/user pct. Assumes config params exist (starting_balance, gas_fee); post-resolution balances include payouts. Invariants: pnl = balance - starting_balance; gas_cost >=0.

# streamlit_app.py_context.md

## Overview
Streamlit script for participant UI in Gaming Market Demo: Handles join flow (display name → user_id, fund balance), lobby/waiting, trading panels (outcome tabs, YES/NO selectors, order tickets with type/size/price/slippage/af_opt_in, confirmation pop-up with est slippage/cost/gas/fees/validation), displays (books, trades, positions, orders, balance, countdowns), realtime refreshes via tick checks/rerun, final rankings/graph. Implements Polymarket-like UX per impl plan §7, integrates services for orders/positions, disables on frozen/resolved.

## Key Exports/Interfaces
- No exports (script); main logic in if __name__ == "__main__" equivalent (Streamlit runs directly).
- Internal components: Join form (insert_user), config/status fetch (load_config), order ticket (submit_order with data dict: outcome_i, yes_no, type, is_buy, size, limit_price/None, max_slippage/None, af_opt_in, ts_ms → str order_id), cancel (cancel_order(order_id, user_id)), displays via queries (fetch_positions/user_orders/pools/balance/trades/users), est slippage (estimate_slippage → dict: estimated_slippage: Decimal, would_reject: bool, est_cost: Decimal), rankings sort by net_pnl, graph via generate_graph() → fig.
- Session state: user_id (str), display_name (str), last_tick (int), last_check (float).

## Dependencies/Imports
- Imports: streamlit (st), time, uuid (uuid4), typing (Dict/Any/List/Optional), decimal (Decimal).
- From app.config: get_supabase_client.
- From app.utils: get_current_ms, usdc_amount, price_value, validate_size/price.
- From app.db.queries: load_config (→ dict), insert_user (user_id: str, name: str, balance: float), fetch_user_balance (→ Decimal), fetch_positions (→ list[dict]), fetch_user_orders (→ list[dict]), get_current_tick (→ dict), fetch_pools (→ list[dict]).
- From app.services.orders: submit_order (user_id: str, order_data: dict → str), cancel_order (order_id: str, user_id: str), get_user_orders (user_id: str, status: str → list[dict]), estimate_slippage (outcome_i: int, yes_no: str, size: Decimal, is_buy: bool, max_slippage: Optional[Decimal] → dict).
- From app.services.positions: fetch_user_positions (user_id: str → list[dict]).
- From app.scripts.generate_graph: generate_graph (→ fig for st.pyplot).
- Interactions: Calls services for submit/cancel/estimate, queries for data/displays; uses client.table for users/trades; session state for persistence; rerun for realtime (poll on tick_id > last_tick).

## Usage Notes
- JSON-compatible for DB; use Decimal for precision (usdc_amount/price_value). Tie to impl plan realtime: Rerun on 1s poll/tick change for <500ms updates (no full WebSocket, but extendable). Confirmation abstracts penalties/auto-fills into net slippage/cost per TDD UX; disable if reject/insufficient. Deterministic: UUID for user_id, sort leaderboard by net_pnl. Integrate with admin.py for shared config; final graph via matplotlib embed.

## Edge Cases/Invariants
- Edges: No user_id → join form; DRAFT/FROZEN/RESOLVED → stop/disable; zero balance/size → validation errors; invalid inputs → ValueError display; no pools/trades → empty tables; af_opt_in only if af_enabled. Invariants: Balance >=0 (via validations); status checks prevent trades; deterministic fetches (no sort specified, assume DB); poll ensures tick updates; %gain = (final-start)/start, handles zero start. For tests: Mock session/client, cover join/submit/cancel/refresh flows, validations, displays match queries.

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