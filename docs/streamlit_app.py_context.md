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