# streamlit_app.py_context.md

## Overview
This file implements the main Streamlit application for participant users in the Gaming Market Demo, handling user joining, waiting room (DRAFT status), trading interface with outcome tabs, order placement, portfolio management, and recent trades display (lines 1-~800, truncated in document). It aligns with Implementation Plan section 7 for participant URL flows, using Streamlit fragments for realtime updates without manual polling, and integrates with services for orders/positions while supporting multi-resolution and batch execution per TDD goals.

## Exports/Interfaces
- No explicit exports (Streamlit script); main entry is the script body which runs the UI loop based on session state and config status.
- **SYSTEM_USERS**: Set[str] - System usernames to filter from leaderboards (e.g., 'AMM System', 'Limit YES Pool') (line 31).
- **filter_system_users(users: List[Dict]) -> List[Dict]**: Filters out system users from a list of user dicts based on 'display_name' (line 35-37).
- **price_fragment(outcome_i: int) -> Tuple[Optional[float], Optional[float]]**: Fragment to display and return current YES/NO prices with spread; runs every batch_interval_s (lines 71-90). Implements realtime price metrics per TDD tunable prices.
- **portfolio_fragment(user_id: str) -> Dict[str, Any]**: Fragment to fetch and cache user positions/orders; returns {'success': bool, 'positions': List[Dict], 'orders': List[Dict], 'error': Optional[str]} (lines 92-122). Caches for batch_interval_s to reduce DB calls.
- **get_current_prices(outcome_i: int) -> Tuple[float, float]**: Helper to fetch YES/NO prices from engine state (lines 124-130). Returns (p_yes, p_no).
- **waiting_room_status_fragment() -> Dict[str, Any]**: Fragment for DRAFT status checks; returns {'success': bool, 'status': str, 'check_count': int, 'last_check': float, 'error': Optional[str]} (lines 132-162). Runs every 3s, triggers rerun on status change.
- **balance_fragment() -> float**: Fragment to display and return user balance; caches for batch_interval_s (lines 300-325).
- **leaderboard_fragment() -> Dict[str, Any]**: Fragment for top 5 users by portfolio value; returns {'success': bool, 'leaderboard': List[Dict], 'user_count': int, 'error': Optional[str]} (lines 327-374). Runs every 2*batch_interval_s, includes position market values.
- **countdown_fragment() -> Tuple[float, float]**: Fragment for time remaining/progress display; runs every 1s (lines 248-275). Returns (time_to_end_live, progress_live).
- **recent_trades_fragment() -> Dict[str, Any]**: Fragment to fetch/process recent trades; returns {'success': bool, 'trades': List[Dict], 'users_data': Dict[str, str], 'error': Optional[str]} (lines 665-711). Caches for batch_interval_s, processes for UI display.

## Definitions
- **client**: SupabaseClient - Global Supabase client from get_supabase_client() (line 27).
- **get_current_ms() -> int**: Returns current timestamp in ms (imported, line 11).
- **usdc_amount(val: float) -> str**: Formats USDC amount (imported, line 11).
- **price_value(val: float) -> str**: Formats price (imported, line 11).
- **validate_size(size: float) -> bool**: Validates order size (imported, line 11).
- **validate_price(price: float) -> bool**: Validates price (imported, line 11).
- **validate_limit_price_bounds(price: float) -> bool**: Validates limit price bounds (imported, line 11).
- **load_config() -> Dict[str, Any]**: Loads market config (imported, line 12).
- **insert_user(user_id: str, display_name: str, balance: float) -> None**: Inserts new user (imported, line 12).
- **fetch_user_balance(user_id: str) -> Decimal**: Fetches balance (imported, line 12).
- **fetch_positions(user_id: str) -> List[Dict]**: Fetches positions (imported, line 12). Deprecated, use fetch_user_positions.
- **fetch_user_orders(user_id: str) -> List[Dict]**: Fetches orders (imported, line 12). Deprecated, use get_user_orders.
- **get_current_tick() -> int**: Gets current tick (imported, line 12).
- **fetch_pools(outcome_i: int) -> List[Dict]**: Fetches LOB pools (imported, line 12). Not used directly.
- **fetch_engine_state() -> Dict[str, Any]**: Fetches engine state (imported, line 12).
- **submit_order(order: Dict) -> None**: Submits order (imported, line 13).
- **cancel_order(order_id: str, user_id: str) -> None**: Cancels order (imported, line 13).
- **get_user_orders(user_id: str, status: str) -> List[Dict]**: Gets orders by status (imported, line 13).
- **estimate_slippage(outcome_i: int, yes_no: str, size: float, is_buy: bool) -> float**: Estimates slippage (imported, line 13). Per TDD slippage estimation with auto-fill simulation.
- **fetch_user_positions(user_id: str) -> List[Dict]**: Fetches positions (imported, line 14).
- **get_binary(state: Dict, outcome_i: int) -> Dict**: Gets binary state (imported, line 16).
- **get_p_yes(binary: Dict) -> float**: Computes YES price (imported, line 16).
- **get_p_no(binary: Dict) -> float**: Computes NO price (imported, line 16).
- **format_time(seconds: float) -> str**: Formats time as HH:MM:SS or MM:SS (line 262-268).
- **generate_graph() -> matplotlib.Figure**: Generates final metrics graph (imported, line 213).

## Dependencies/Imports
- **streamlit as st**: Core UI library (line 1).
- **time**: For timestamps and sleeps (line 2).
- **json**: For potential JSON handling (line 3).
- **uuid.uuid4**: For user_id generation (line 4).
- **typing: Dict, Any, List, Optional**: Type hints (line 5).
- **decimal.Decimal**: For precise balances (line 6).
- **datetime.datetime**: For timestamp parsing (line 7).
- **app.config.get_supabase_client**: Gets Supabase client (line 9).
- **app.utils: get_current_ms, usdc_amount, price_value, validate_size, validate_price, validate_limit_price_bounds**: Utility functions (line 11).
- **app.db.queries: load_config, insert_user, fetch_user_balance, fetch_positions, fetch_user_orders, get_current_tick, fetch_pools, fetch_engine_state**: DB queries (line 12).
- **app.services.orders: submit_order, cancel_order, get_user_orders, estimate_slippage**: Order services (line 13).
- **app.services.positions.fetch_user_positions**: Position fetching (line 14).
- **app.engine.state: get_binary, get_p_yes, get_p_no**: Engine price getters (line 16).
- **app.scripts.generate_graph**: Graph generation for RESOLVED (line 213).
- Interactions: Calls DB/services for data; uses engine state for prices; fragments query independently for realtime. Integrates with batch_runner/timer_service via config status changes triggering reruns (per Implan section 6-7).

## Usage Notes
- Session state keys: 'user_id', 'display_name', 'last_tick', 'last_check', 'last_price_update', 'last_leaderboard_update', 'realtime_user_count', 'status_check_count', 'last_status_check', 'last_frozen_check', 'last_frozen_check', 'portfolio_cache_{user_id}', 'balance_cache_{user_id}', 'trades_cache' (lines 39-67, 136-140, 97-103, 305-311, 680-686). Clear caches on actions like cancel to force refresh (lines 590-596).
- Fragments: Use @st.fragment with run_every for realtime (e.g., batch_interval_s from config['params']); handle caching to minimize DB hits (per Implan realtime UX).
- Status handling: DRAFT (waiting room, lines 164-226), FROZEN (pause check, lines 228-243), RESOLVED (rankings/graph, lines 245-254), RUNNING (trading UI, lines 256+). Implements auto-events per TDD/Implan.
- Outcome tabs: Dynamic from active_outcomes via engine state (lines 376-399); supports multi-resolution by filtering inactive.
- Order ticket: In each tab, YES/NO toggle, market/limit selector, size/limit_price inputs, slippage estimate, submit with validation/gas deduction simulation (truncated section ~lines 400-500). Per TDD slippage estimation and gas fees.
- Portfolio tabs: Positions (dataframes/metrics, lines ~500-550), Open Orders (expanders with details/cancel, lines ~550-650), Summary (holdings/metrics, lines ~650-750).
- Recent Trades: Table with processed trades (user, price, size with sign, side), filtering system users (lines 713-800). Uses SYSTEM_USER_IDS hardcoded (lines 747-753).
- UI: Polymarket-like with metrics, expanders, confirmations; buttons trigger services/reruns. Reference TDD for UI flows like transaction confirmation UX.

## Edge Cases/Invariants
- No user_id: Stop and prompt join (lines 49-51).
- Status changes: Auto-rerun on fragment detection (e.g., lines 151-155, 239-243).
- No start_ms: Display "Demo not started" (line 221).
- Empty data: Infos like "No positions" (lines 537, 651).
- Cache invalidation: Delete keys on cancel to refresh (line 593).
- Active outcomes: Fallback to all if state fetch fails (lines 378-399); assumes params['n_outcomes'] set.
- Invariants: Prices <1 per TDD; balances positive; deterministic UI via fragments; multi-res active flags from state.

## Inconsistencies/Possible Issues
- Deprecated imports: Uses fetch_positions/fetch_user_orders (line 12) but services use fetch_user_positions/get_user_orders (lines 14,13); potential migration needed.
- Cache keys: 'portfolio_cache_{user_id}' but del 'portfolio_cache' (line 593); may miss if global cache exists.
- User count: Fallback static fetch if realtime=0 (lines 172-182); but realtime_user_count not updated elsewhere, potential staleness.
- Start_ms fallbacks: Multiple sources (params['start_ts_ms'], config['start_ts_ms'], 'start_ts' ISO parse, lines 217-234); error-prone if inconsistent.
- Positions value: Fallback to $0.50 if prices None (lines 347, 721); may inaccurate post-res.
- Trades processing: Assumes buy_user_id/sell_user_id one is system (lines 747-769); fails if user-user trades (though per TDD mostly AMM/LOB).
- Truncated code: Document cuts at portfolio/orders sections; assume full implements order ticket per plan, but verify submit_order calls.
- Gas: Mentions in plan but no deduction in UI; assume in services/orders.py.
- Realtime: Fragments may cause flicker; plan suggests streamlit-webrtc if needed, but not implemented.