# streamlit_app.py_context.md

## Overview
Streamlit script implementing the participant UI for the Gaming Market Demo, handling join flow (display name to user_id assignment with starting balance), waiting room in DRAFT status (with joined players list and auto-refresh), frozen/resolved displays, trading interface with outcome tabs (order tickets, order books, recent trades), portfolio management (positions, open orders with cancellation, summary), and realtime refreshes via polling (rerun on tick change or 1s interval). Implements Polymarket-like UX per Implan §7, with transaction confirmation expanders showing estimates/fees/returns/risks; integrates services for orders/positions and DB queries for displays; stops on invalid states. (Lines 1-20: Imports/setup; 21-60: Join/session init; 61-150: Status handling; 151-200: Time/balance/leaderboard; 201-500: Outcome tabs with tickets/books/trades; 501-800: Portfolio tabs; 801-end: Refresh button.)

## Key Exports/Interfaces
- No exports (executable script); runs as Streamlit app via `streamlit run streamlit_app.py`.
- Internal Functions/Components:
  - Join Form (Lines 21-30): `st.text_input("Enter display name")`, `st.button("Join")` → Calls `insert_user(user_id=uuid4(), display_name, balance=config['starting_balance'])`; sets session_state['user_id/display_name/last_tick/last_check'].
  - Waiting Room (Lines 61-120): In DRAFT, shows users count/list (from `client.table('users').select('*')`), auto-checks status every 3s with rerun limit (100), manual refresh button.
  - Frozen/Resolved Handling (Lines 121-150): Warnings/tables for pauses/resolutions; rankings sorted by net_pnl with % gain; graph via `generate_graph()` → `st.pyplot(fig)`.
  - Trading Tabs (Lines 201-500): `outcome_tabs = st.tabs([f"Outcome {i+1}" for i in range(n_outcomes)])`; per tab:
    - Order Ticket: Radios for yes_no/direction, selectbox for order_type, number_inputs for size/limit_price/max_slippage; checkbox for af_opt_in if enabled; expander with summary/fee/returns/risk analysis (e.g., potential profit/return multiple, risk warnings); `st.button("Submit Order")` → `submit_order(user_id, order_data=dict(outcome_i, yes_no, type, is_buy, size, limit_price=None/market, max_slippage=None/limit, af_opt_in, ts_ms=get_current_ms())`.
    - Order Book: Tabs for YES/NO; dataframes for bids/asks (aggregated from `fetch_pools(outcome_i)` with user shares/indicators); metrics for current prices/spread.
    - Recent Trades: `st.table` from `client.table('trades').select('*').eq('outcome_i', outcome_i).order('ts_ms', desc=True).limit(10)`.
- Portfolio Tabs (Lines 501-800): Positions (dataframe with returns analysis), Open Orders (expanders with details/cancel buttons confirming via session_state pending), Summary (holdings/pending/commitment metrics).
- Refresh: `st.button("Refresh")` → `st.rerun()`.

## Dependencies/Imports
- Imports: `streamlit as st`, `time`, `uuid.uuid4`, `typing: Dict/Any/List/Optional`, `decimal.Decimal`, `datetime.datetime` (Lines 1-6).
- From app: `config.get_supabase_client`, `utils: get_current_ms/usdc_amount/price_value/validate_size/validate_price/validate_limit_price_bounds`, `db.queries: load_config/insert_user/fetch_user_balance/fetch_positions/fetch_user_orders/get_current_tick/fetch_pools/fetch_engine_state`, `services.orders: submit_order/cancel_order/get_user_orders/estimate_slippage`, `services.positions: fetch_user_positions`, `engine.state: get_binary/get_p_yes/get_p_no` (Lines 7-15).
- Interactions: Fetches config/status (load_config), user data/queries; submits via services.orders; estimates slippage with simulation; mutates session_state for UI persistence; reruns for realtime (poll last_tick > current_tick['tick_id'] every 1s).

## Usage Notes
- Implements Implan §7 participant flows: Join funds starting_balance; DRAFT lobby with users grid; FROZEN warning with refresh; RESOLVED rankings/graph; RUNNING tabs with tickets (validations per TDD, disable on reject/insufficient); books aggregate pools (pro-rata user shares, indicators); portfolio with cancel confirmations (session_state pending to avoid accidental); time_to_end metric from elapsed_ms.
- Realtime via polling (1s check/rerun on tick change, <500ms effective); JSON-compatible for DB; Decimal for precision (usdc_amount 6 decimals, price_value 4); confirmation abstracts penalties/auto-fills into slippage/returns (e.g., effective_price = est_cost / size); risk infos based on effective_cost_per_token thresholds (>0.8 high, >0.6 moderate).
- Tie to TDD: Uses engine state for prices (get_p_yes/no); handles multi-res via n_outcomes/active implicit in config; gas_fee in confirmation but deducted in services.orders.

## Edge Cases/Invariants
- Edges: No user_id → join stop; DRAFT/FROZEN/RESOLVED → stop/disable submits; zero size/price → errors; limit_price None for MARKET; est would_reject disables button; cancel pending confirmations (yes/no buttons); no pools/positions → empty displays; high risk warnings (>0.8/0.6 thresholds); ISO timestamp parsing with decimal fix (Lines 151-180).
- Invariants: Deterministic rerun (sorted users? assume DB); balance >=0 enforced via services; q_eff < L_i via engine (not here); poll counter <100 prevents loops; true limit enforcement info in UI; effective prices/fees separate/transparent per TDD UX.

## Inconsistencies/Possible Issues
- Line 300-350: Est slippage uses estimate_slippage but assumes market; for LIMIT, trading_fee_est = f_match * size * limit_price /2 (but f_match for cross, f for AMM—clarify if LIMIT can hit AMM? Per TDD, LIMIT adds to pool, no immediate AMM).
- Line 400-450: Order book uses fetch_pools but aggregates manually (Decimal sums); user_positions_in_pools redundant with data['user_share'].
- Line 550-600: Positions potential_payout = tokens *1.0 but uses estimated_cost_basis ~ tokens * current_price (fallback 0.5)—inaccurate if trade history unavailable; consider DB trade avg for basis.
- Line 700-750: Cancel uses session_state pending per order (unique keys); but rerun on confirm may cause flicker—consider st.form for modals.
- No WebSocket; polling may lag >500ms on high load—extend with streamlit-webrtc if needed per Implan.