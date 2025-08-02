# Implementation Plan for Gaming Market Demo

## 0) Goal & Scope

**Goal:** Run a live, 20-person market-testing demo over a single shareable link, with:

* Multi-outcome market (3–10 outcomes), each with **YES/NO** tokens, **market/limit** orders, and support for all design features including LOB, cross-matching YES/NO limits, auto-filling on cross-impacts, multi-resolution support, and user-controlled max slippage on market orders.
* **Batch execution** every configurable interval (e.g., 1s) using a **deterministic Python engine** that encapsulates the novel AMM math, including tunable parameters, asymmetry, coupling, and dynamic interpolation.
* **Automatic resolutions** (intermediate and final) with pre-configured outcomes, trading freezes, and price renormalization.
* **Accurate payouts** after final resolution, including distribution of unfilled limit order assets.
* Fast to build, cheap to run, robust for a single demo session (and repeatable).
* UI resembling Polymarket: Clean, intuitive trading panels with outcome selectors, YES/NO toggles, order tickets, order books, recent trades, positions, and countdowns; adapted for binary markets per outcome, cross-impacts, and multi-resolution.

**Out of scope (for the demo):**

* Production-grade auth beyond simple Admin password, KYC, fiat/crypto payments, on-chain settlement.
* MEV mitigation beyond batch execution and FIFO batching.
* Sophisticated visualizations beyond basic order book aggregation, recent trades, and a final metrics graph (use Matplotlib for the graph).
* External speculation info integration.

---

## 1) High-Level Architecture

```
[ User Browsers ]
       |
   (HTTPS)
       |
[ Streamlit App ]  <-- Single public URL for participants; separate Admin URL
   |        |
   |        | (Python import)
   |     [ Engine Package ]  <-- Deterministic math (pure functions + unit tests)
   |
   |------> [ Supabase Postgres ]  <-- Durable state (users, orders, trades, ticks, events, configs)
   |------> [ Supabase Realtime ]  <-- Live updates to clients
   |
   |------> [ Batch Runner ]  <-- Configurable interval: read new orders, run engine, write fills, publish updates
   |
   |------> [ Timer Service ]  <-- Background task for real-time countdowns, automatic resolutions, and freezes
```

* **Front end:** Streamlit. Separate Admin dashboard URL (with password prompt); shareable participant URL. Simple join flow, Polymarket-like trading UI, scoreboard, admin controls.
* **State:** Supabase Postgres for persistence; Supabase Realtime for pushing events/UI refresh.
* **Engine:** Pure-Python package with a single entry point. Black-box the novel math (quadratics, asymmetries, diversions, auto-fills, etc.) behind a stable interface. 100% unit-tested.
* **Concurrency model:** **Batch per tick**. New orders buffered in DB, processed atomically once per tick.
* **Timer:** Background task (e.g., threading in Streamlit) for monitoring real-time countdowns, triggering automatic intermediate/final resolutions, and enforcing trading freezes.

---

## 2) Roles & User Flows

### Roles

* **Admin**: Accesses dashboard via URL with simple password, configures session, starts demo, monitors participants.
* **Trader/Participant**: Joins via shareable URL, sets display name, trades during active periods.

### Flows

0. **Admin Access**: Visit Admin URL, enter password, proceed to dashboard.
1. **Configure Session** (Admin) → Set outcomes (number, names), total duration (seconds), final winning outcome, intermediate resolutions (number, timings as offsets from start, freeze durations, eliminated outcomes per round), starting/ending tunable params (ζ, μ, ν, κ) with interpolation mode (reset/continue across rounds), starting simulated USDC balance, batch interval, toggles for cross-matching/auto-filling/multi-resolution, all other params (Z, γ, q0, f, p_max, p_min, η, tick_size, f_match, σ, af_cap_frac, af_max_pools, af_max_surplus, vc_enabled), Flat per-transaction gas fee (in USDC): A fixed amount deducted from user balance for every order submission (market or limit), regardless of success/failure/rejection. Defaults to 0 for free testing, but admin can set to simulate costs.
2. **Generate Shareable URL** → System provides URL for participants.
3. **Join** (Trader) → Visit URL, enter display name → Get assigned `user_id`, funded with starting balance.
4. **Lobby** (Admin/Traders) → Admin sees joined users/count; traders see waiting message. Admin triggers start.
5. **Trade** → Once started, traders see Polymarket-like UI: Outcome tabs, YES/NO selectors, order ticket (market/limit, size, limit price if applicable, max slippage for market orders), order book (aggregated bids/asks), recent trades, positions, balances, countdowns to next freeze/end.
6. **Automatic Events** → At configured times: Freeze trading, eliminate outcomes, renormalize prices, resume after freeze (if not final).
7. **Resolve** → Automatic at end: Payouts, distribute unfilled limits, show rankings by final USDC, % gain/loss, trades count; graph (volume, MM risk, MM profit over time); Admin CSV exports (trade history, config, metrics).

---

## 3) Functional Requirements

### Market & Tokens

* **Multi-outcome market**: Exactly one winner; N=3–10 outcomes.
* For each outcome **i**, two tokens: **YES_i** (pays $1 if i wins), **NO_i** (pays $1 if i loses).
* **Price domain:** $0–$1; **tick_size** configurable.
* **Initial setup:** Per design (Z subsidy, q0 virtuals, p=0.5).
* **Features:** All per design: AMM with asymmetry/coupling/tunables, LOB with batched matching, cross-matching (toggleable), auto-filling (toggleable), multi-resolution (toggleable), dynamic param interpolation (linear over time/rounds).
* **User controls:** Max slippage on market orders (to cap asymptotic penalties). Users can configure this value per session or per order. If execution would exceed the configured max slippage (after accounting for auto-fills and seigniorage), the order is reverted/rejected in the engine (status=REJECTED), but the flat gas fee is still deducted from balance.

### Orders

* **Types:** MARKET (with max slippage), LIMIT.
* **Fields:** outcome_i, yes_no, size (tokens), limit_price (for LIMIT), af_opt_in (for auto-fill if enabled).
* **Validation:** Price in [0,1], size >0, sufficient balance (conservative estimate), trading not frozen.
* **Slippage Estimation:** For market orders, client-side validation and UI previews must estimate slippage conservatively (e.g., based on current_p + potential impact from κ and penalties). The implementation must account for auto-filling effects (if enabled) by simulating potential seigniorage reductions in penalties, to avoid over-estimating slippage for large orders. This ensures accurate max slippage checks without rejecting viable trades.
* **Cancellation:** Withdraw unfilled limit orders (pro-rata from pool).

### Matching & Execution (per batch/tick)

* Batch collects **new** orders since last tick.
* **Engine call:** `apply_orders(state, new_orders, params, current_time) -> (fills, new_state, events)`
  * `state` includes per-binary pools (V_i, L_i, q_yes_i, q_no_i, virtual_yes_i, subsidy_i, seigniorage_i), LOB pools per tick/yes_no, active flags.
  * `params` includes all symbols from design, toggles, dynamic interpolation based on current_time.
  * **Active Outcomes Handling:** Computations such as f_i = 1 - (N_active - 1) * ζ must use the current number of active outcomes (N_active, derived from active flags in state). Diversions are applied only across remaining active binaries (j != i and active_j == true), updating N_active dynamically in multi-resolution scenarios.
  * Handles market orders: Cross LOB first (if matches), then AMM with slippage check.
  * Limits: Add to tick pools; match in batch (pro-rata, FIFO in batch).
  * Cross-matching: If enabled, match YES buys with NO sells at complementary prices.
  * Auto-filling: If enabled, trigger on cross-impacts, capture seigniorage.
* **Filling rules:**
  * Market: Fill vs LOB then AMM; reject if slippage > max.
  * Limit: Fill if crosses clearing; remain in pool otherwise.
  * Partial fills allowed.
* **Fee model:** f on trades, f_match on matches; seigniorage allocation per σ.
* **Diversion & Impacts:** Per design quadratics, diversions, own/cross impacts, penalties. Leverage numpy for reliable processing of numerical computations to ensure precision and efficiency.
* **Dynamic Params:** Interpolate ζ, μ, ν, κ linearly from start to end values based on time (reset/continue per round if multi-res).

### Balances & Risk

* **Simulated USDC balance.**
* **Cost/Proceeds:** Per AMM formulas or tick prices.
* **Gas Fees:** Deduct the configured flat gas fee from user balance on every order submission, even if rejected (e.g., due to max slippage exceedance, insufficient funds, or frozen trading). Track gas deductions in user metrics.
* **Positions:** Tracked per user, yes_no_i (tokens held).
* **Margin/Risk:** Block insufficient funds on entry (estimate at p_max for buys); engine enforces on fill.
* **MM Risk/Profit:** Tracked (subsidy phase-out, fees, seigniorage); bounded by Z.

### Automatic Resolutions & Payouts

* **Timer monitors:** At timings, pause trading, eliminate pre-config (pay NO, free liquidity, redistribute, renormalize virtual_yes), resume after freeze.
* **Final:** At end, pay based on winner (YES_w=1, NO_w=0; others opposite), distribute unfilled limits pro-rata, lock market.
* **Payout Clarification:** All payouts (intermediate and final) are calculated based solely on user-held tokens, aggregated from the `positions` table (sum of `tokens` per user per `outcome_i` and `yes_no`). This excludes the initial virtual q0 component of q_yes_i/q_no_i, which is not held by users and does not contribute to actual liabilities or payouts. The engine's `trigger_resolution` function must sum user positions to determine redeemable amounts, ensuring solvency proofs hold as per the design (actual q_yes_i/q_no_i used only for pricing, not payouts).
* **Final balances:** Starting + proceeds - costs + payouts + rebates - fees + unfilled returns.
* All open orders canceled on final.

### Realtime Updates

* After tick/resolution: Publish `TickEvent` (summary stats, prices, volumes), deltas (fills, positions, top of book per outcome/yes_no, leaderboard).

### Observability & Export

* **Events table** for audit.
* **CSV export:** Trades, config, metrics (rankings, % gain/loss, trades/user, MM profit/risk).
* **Graph:** Matplotlib plot (volume, MM risk (sum subsidy_i), MM profit (fees + seigniorage + remainings) over time). Use numpy for efficient data processing if needed.
* **Gas Metrics:** Track and export per-user gas costs (sum of deductions), total gas costs across all users, and include in final rankings/CSV (e.g., net_pnl adjusted for gas, % gain/loss incorporating gas).

---

## 4) Engine Interface (deterministic core)

Pure-Python package: `market_engine/`

**Public API**

```python
from typing import List, Tuple, Dict, Any

class EngineState(TypedDict):
    # Opaque; JSON-serialized
    binaries: List[Dict]  # Per i: V, L, q_yes, q_no, virtual_yes, subsidy, seigniorage, active, lob_pools (dict tick: {yes_buy: volume/shares, ...})
    ...

class EngineParams(TypedDict):
    n_outcomes: int
    outcome_names: List[str]
    z: float
    gamma: float
    q0: float
    mu_start: float  # And end, similarly for nu, kappa, zeta
    interpolation_mode: str  # 'reset' or 'continue'
    # All other params: f, p_max, etc.; toggles: cm_enabled, af_enabled, mr_enabled
    ...

class Order(TypedDict):
    order_id: str
    user_id: str
    outcome_i: int
    yes_no: str  # 'YES' or 'NO'
    type: str  # 'MARKET' or 'LIMIT'
    size: float
    limit_price: float | None
    max_slippage: float | None  # For MARKET
    af_opt_in: bool
    ts_ms: int

class Fill(TypedDict):
    trade_id: str
    buy_user_id: str
    sell_user_id: str
    outcome_i: int
    yes_no: str
    price: float
    size: float
    fee: float
    tick_id: int
    ts_ms: int

def apply_orders(
    state: EngineState,
    orders: List[Order],
    params: EngineParams,
    current_time: int  # For interpolation, resolutions
) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]:
    """Deterministic; computes dynamic params, handles matching/AMM/auto-fills."""
    ...

def trigger_resolution(
    state: EngineState,
    params: EngineParams,
    is_final: bool,
    elim_outcomes: List[int] | int  # List for intermediate, int for final winner
) -> Tuple[Dict[str, float], EngineState, List[Dict]]:  # Payouts per user, new_state, events
    ...
```

**Design notes**

* **Determinism:** Sort by ts_ms, order_id.
* **Unit tests:** Cover quadratics, penalties, cross-impacts, auto-fills, renormalizations, edges (p_max/min, zero subsidy). Use numpy for numerical stability in quadratic solves, interpolations, and auto-fill computations (e.g., discriminant calculations, binary searches if implemented).
* **Pluggability:** Engine handles AMM solves, LOB matching, diversions internally.

---

## 5) Data Model (Postgres/Supabase)

Use snake_case. Add created_at/updated_at. Single instance (no room_id).

### `config`

* `config_id` (uuid, pk)
* `params` (jsonb)  # All EngineParams, timings, outcomes, etc.
* `status` (enum: DRAFT|RUNNING|PAUSED|RESOLVED|FROZEN)
* `start_ts` (timestamptz)
* `current_tick` (int)

### `users`

* `user_id` (uuid, pk)
* `display_name` (text)
* `is_admin` (bool, default false)  # But only one effective Admin
* `balance` (numeric(18,6))
* `net_pnl` (numeric(18,6), default 0)
* `trade_count` (int, default 0)

### `positions`

* `position_id` (uuid, pk)
* `user_id` (fk)
* `outcome_i` (int)
* `yes_no` (enum: YES|NO)
* `tokens` (numeric(18,6), default 0)

### `orders`

* `order_id` (uuid, pk)
* `user_id` (fk)
* `outcome_i` (int)
* `yes_no` (enum: YES|NO)
* `type` (enum: MARKET|LIMIT)
* `size` (numeric(18,6))
* `limit_price` (numeric(6,4), nullable)
* `max_slippage` (numeric(6,4), nullable)
* `af_opt_in` (bool)
* `status` (enum: OPEN|FILLED|PARTIAL|CANCELED|REJECTED)
* `remaining` (numeric(18,6))
* `tick_accepted` (int, nullable)
* `ts_ms` (bigint)

**Indexes:** (status), (tick_accepted), (user_id).

### `lob_pools`

* `pool_id` (uuid, pk)
* `outcome_i` (int)
* `yes_no` (enum: YES|NO)
* `is_buy` (bool)
* `tick` (int)  # tick_size * 100 for int
* `volume` (numeric(18,6))  # USDC or tokens
* `shares` (jsonb)  # {user_id: share}

### `trades`

* `trade_id` (uuid, pk)
* `outcome_i` (int)
* `yes_no` (enum: YES|NO)
* `buy_user_id` (fk)
* `sell_user_id` (fk)
* `price` (numeric(6,4))
* `size` (numeric(18,6))
* `fee` (numeric(18,6))
* `tick_id` (int)
* `ts_ms` (bigint)

### `ticks`

* `tick_id` (int, pk)
* `ts_ms` (bigint)
* `summary` (jsonb)  # Prices, volumes, MM risk/profit

### `events`

* `event_id` (uuid, pk)
* `type` (text)  # ORDER_ACCEPTED, TICK, RESOLUTION, etc.
* `payload` (jsonb)
* `ts_ms` (bigint)

### `metrics`

* `metric_id` (uuid, pk)
* `tick_id` (int, nullable)
* `volume` (numeric(18,6))
* `mm_risk` (numeric(18,6))
* `mm_profit` (numeric(18,6))

**Realtime channels:** `realtime:demo` for all.

---

## 6) Batch Runner (authoritative loop)

**Trigger:** Background task; runs every batch_interval_ms if status=RUNNING and not FROZEN.

**Pseudocode:**

```python
def run_tick():
    with pg_transaction():
        tick_id = next_tick_id()
        new_orders = db.fetch_open_orders(eligible_at=tick_id)
        state = db.fetch_engine_state()
        current_time = time.time() - config.start_ts.timestamp()

        fills, new_state, events = engine.apply_orders(state, new_orders, config.params, current_time)

        db.insert_trades(fills)
        db.update_orders_from_fills(fills)
        db.update_positions_and_balances(fills)
        db.update_lob_pools_from_fills()  # If matched
        db.save_engine_state(new_state)
        db.insert_tick(tick_id, summary_from(new_state))
        db.insert_events(events)
        db.update_metrics(tick_id, volume=..., mm_risk=sum(subsidy_i), mm_profit=fees+seigniorage+...)

    realtime.publish('demo', make_tick_payload(tick_id))
```

**Timer Service:** Separate loop checks for resolution timings: If time for intermediate/final, set status=FROZEN, call engine.trigger_resolution, update state/payouts/balances, set RESOLVED if final or resume RUNNING after freeze.

**Idempotency:** Tick monotonic; transaction ensures atomicity.

---

## 7) Streamlit UI (single-file MVP → refactor later)

**Panels**

1. **Admin Dashboard** (password-protected URL)

   * Config form: All params as inputs/dropdowns.
   * Joined users list/count.
   * Start button; freeze/resume if needed (but automatic).
   * CSV export buttons.
   * Graph viewer post-resolution.

2. **Participant URL**

   * Join: Display name input.
   * Lobby: Waiting message.
   * Trading: Polymarket-style: Outcome tabs, YES/NO buttons, order ticket (dropdowns/sliders for size/price/slippage), aggregated order book (bids/asks table), recent trades list, positions table, balance, countdowns (to next freeze/end). **Transaction Confirmation UX:** Before submission, display a confirmation pop-up with details including: order type/size/price (if limit), estimated slippage (abstracting penalties and auto-fill/penalty reductions into overall slippage for simplicity), fees, flat gas cost (deducted regardless of success), and total estimated cost. The "Submit Transaction" button is disabled if the user lacks sufficient balance/assets (conservative estimate including gas) or if estimated slippage exceeds their configured max slippage, with clear error messages (e.g., "Insufficient balance: Need X more USDC" or "Estimated slippage 5% > Max 3%"). Auto-fill rebates (e.g., (1-σ) surplus pro-rata) and penalty reductions are abstracted away; users see only the net cheaper cost/slippage on confirmation. Fees are shown separately for transparency.
   * Cancel orders button (list open limits).

**Realtime UX**

* Subscribe to `realtime:demo`.
* On tick: Refresh trades, positions, books, leaderboard. For smoother realtime updates across users, integrate streamlit-webrtc or similar extensions if standard reruns/polling cause latency/flicker; subscribe to Supabase Realtime channels and use WebSocket handling for low-latency pushes.
* On resolution: Show updates, final screen with rankings (% gain/loss = (final-start)/start, trades count), graph.

**Validation & UX details**

* Disable trades during freeze/resolved.
* Toasts for orders/fills/resolutions.

---

## 8) Acceptance Criteria & Test Cases

**Functional**

* 20 users join/trade for duration with batches; automatic freezes/resolutions work.
* All features (AMM, LOB, cross-match, auto-fill, multi-res) testable via toggles.
* Limits cancelable; unfilled returned at end.
* Balances/positions reconcile; MM risk <=Z.
* UI matches Polymarket aesthetics (tabs, tickets, books).

**Engine**

* Tests: Solves, impacts, auto-fills, renormalizations, interpolations, toggles.

**Data**

* Constraints enforced.
* CSV opens correctly.

**Performance**

* Tick <200ms with 200 orders.
* Updates <500ms.

**Failure modes**

* Transaction rollback on crash; resume on next tick.

---

## 9) Configuration & Env

* `ADMIN_PASSWORD` (env)
* `BATCH_INTERVAL_MS` (from config)
* `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL`

---

## 10) Security & Auth (demo-level)

* **Admin:** Simple password check in Streamlit session state.
* **Participants:** No auth; display name only, user_id in cookie.
* RLS off for demo.

---

## 11) Repository Structure

```
# Repository Structure for Gaming Market Demo

# Overall Design Principles:
# - To avoid files being too long for Grok 4 to generate in a single prompt, large files like core.py have been split into smaller, focused modules (e.g., amm_math.py, impact_functions.py). Each file aims to be <1000-1500 lines of code, focusing on 1-2 key responsibilities.
# - To minimize context overload from multiple _context.md files, the structure groups tightly coupled files (e.g., all engine math in subdirs) and defines clear interfaces (e.g., via __init__.py exports). Files are ordered in a generation sequence: start with utils/config, then db, engine basics, services, runners, UIs last.
# - Generation Sequence Recommendation: Generate in this order: config.py/utils.py -> db/schema.sql/queries.py -> engine/state.py/params.py -> engine math files (amm_math.py etc.) -> engine/orders.py/resolutions.py -> services/* -> runner/* -> streamlit_* -> scripts/* -> tests last (as they reference everything).
# - Context Usage: Each file's comment specifies "Needed Context Files" (previous _context.md to reference). Limit to 3-5 per file. Relationships: Lists imports/dependencies. Usage: Brief description for LLM prompting.

# Root-level files
├── .env  # Environment variables (e.g., ADMIN_PASSWORD, SUPABASE_URL, DATABASE_URL). Usage: Static config file, no code; generate as key-value template. Needed Context: None. Relationships: Loaded by config.py.
├── .env.example  # Template for .env with placeholders. Usage: Documentation aid. Needed Context: None. Relationships: Mirrors .env.
├── .gitignore  # Standard Python gitignore (e.g., __pycache__, .env). Usage: Static; copy standard template. Needed Context: None. Relationships: None.
├── README.md  # Project overview, setup instructions, running the apps, and demo usage. Usage: High-level doc; generate last as summary. Needed Context: All _context.md (but summarize). Relationships: References all modules.
├── requirements.txt  # Dependencies (e.g., streamlit, supabase-py, numpy, matplotlib, pytest, typing_extensions). Usage: List deps; generate based on used libs. Needed Context: engine/core files for numpy/etc. Relationships: Required for all Python files.
└── setup.py  # Optional setup for installing /engine as a package (for easier testing/reuse). Usage: Packaging script; simple setup call. Needed Context: engine/__init__.py_context.md. Relationships: Depends on engine package.

# App directory
/app
  ├── __init__.py  # Makes /app a package for relative imports. Usage: Empty or exports; minimal. Needed Context: None. Relationships: Imported by all submodules.
  ├── config.py  # Handles loading configuration, environment variables, and session params. Usage: Loads .env, DB connections; short utility. Needed Context: None (first file). Relationships: Used by db/queries.py, services/*, runner/*.
  ├── utils.py  # General utility functions (e.g., timestamp conversions, fixed-point arithmetic helpers, validation logic). Usage: Common helpers like fixed-point math for USDC (18 decimals). Needed Context: config.py_context.md. Relationships: Imported by engine/*, services/* for math/validation.
  ├── streamlit_app.py  # Main Streamlit script for participant UI (join, lobby, trading panels, realtime updates). Usage: Core participant UI logic; focus on layout/callbacks. Split if needed, but keep <800 lines. Needed Context: services/orders.py_context.md, services/positions.py_context.md, services/realtime.py_context.md, db/queries.py_context.md. Relationships: Calls services for data, uses utils for validation.
  ├── streamlit_admin.py  # Separate Streamlit script for admin dashboard (config form, monitoring, start/pause, exports). Usage: Admin UI; similar to app.py but admin-specific. Needed Context: Same as streamlit_app.py plus scripts/export_csv.py_context.md. Relationships: Similar to streamlit_app.py, plus export triggers.
  ├── /services
  │   ├── __init__.py  # Exports service functions. Usage: Minimal. Needed Context: None. Relationships: For relative imports.
  │   ├── orders.py  # Service for handling order submission, validation, cancellation, and related DB operations. Usage: Order lifecycle; calls engine for simulation if needed. Needed Context: db/queries.py_context.md, engine/orders.py_context.md, utils.py_context.md. Relationships: Interacts with db, engine/orders.
  │   ├── positions.py  # Service for managing user positions, balance updates, and payouts. Usage: Position tracking; gas deductions here. Needed Context: db/queries.py_context.md, engine/state.py_context.md, utils.py_context.md. Relationships: Updates db, uses engine state for calcs.
  │   ├── ticks.py  # Service for tick processing, summary stats, and metrics updates. Usage: Tick summaries; calls engine if needed. Needed Context: db/queries.py_context.md, engine/state.py_context.md, runner/batch_runner.py_context.md. Relationships: Called by batch_runner.
  │   ├── resolutions.py  # Service for triggering resolutions (intermediate/final), renormalization, and event handling. Usage: Resolution orchestration. Needed Context: db/queries.py_context.md, engine/resolutions.py_context.md, utils.py_context.md. Relationships: Calls engine/resolutions, updates db.
  │   └── realtime.py  # Service for Supabase Realtime integration (subscriptions, publishing events, WebSocket handling). Usage: Event pushing; short integration code. Needed Context: db/queries.py_context.md, config.py_context.md. Relationships: Used by UIs and runners for live updates.
  ├── /db
  │   ├── __init__.py  # Exports db functions. Usage: Minimal. Needed Context: None. Relationships: For imports.
  │   ├── schema.sql  # SQL script for creating all database tables, enums, indexes, and constraints. Usage: DDL statements; generate from data model. Needed Context: config.py_context.md (for env vars). Relationships: Executed via migrations.
  │   ├── queries.py  # Python module with SQL query strings and functions for DB interactions (e.g., fetch_state, insert_trades). Usage: Query wrappers; use psycopg2 or supabase-py. Needed Context: schema.sql_context.md, config.py_context.md. Relationships: Used by services/*, runner/*.
  │   └── /migrations
  │       ├── 001_initial.sql  # Initial migration script (applies schema.sql or base setup). Usage: Runs schema. Needed Context: schema.sql_context.md. Relationships: Depends on schema.
  │       └── 002_add_gas_metrics.sql  # Example follow-up migration for adding gas-related columns if needed. Usage: Incremental changes. Needed Context: 001_initial.sql_context.md. Relationships: Sequential to 001.
  ├── /engine  # Pure Python package for deterministic market logic
  │   ├── __init__.py  # Exports main APIs (apply_orders, trigger_resolution). Usage: Central export. Needed Context: state.py_context.md, params.py_context.md. Relationships: Facade for submodules.
  │   ├── state.py  # State management (EngineState TypedDict, serialization/deserialization, updates for V_i, L_i, etc.). Usage: State handling; JSON ops. Needed Context: params.py_context.md, utils.py_context.md. Relationships: Used by all engine files.
  │   ├── params.py  # EngineParams TypedDict and interpolation logic for dynamic params (ζ, μ, ν, κ based on time/rounds). Usage: Param defs and time-based calcs. Needed Context: utils.py_context.md (for time funcs). Relationships: Input to apply_orders/etc.
  │   ├── amm_math.py  # AMM-specific math (quadratics, buy/sell cost functions, slippage penalties). Usage: Core equations; use numpy for solves. Needed Context: state.py_context.md, params.py_context.md, utils.py_context.md. Relationships: Called by orders.py.
  │   ├── impact_functions.py  # Cross-impacts, diversions, own impacts, asymmetry logic. Usage: Impact calcs; split from amm for size. Needed Context: amm_math.py_context.md, state.py_context.md. Relationships: Integrates with amm_math.
  │   ├── autofill.py  # Auto-filling logic on cross-impacts, seigniorage capture, binary searches. Usage: Auto-fill specifics; numpy for searches. Needed Context: impact_functions.py_context.md, params.py_context.md. Relationships: Triggered in orders.py.
  │   ├── lob_matching.py  # LOB handling, batched matching, cross-matching (YES/NO). Usage: Limit order book ops. Needed Context: state.py_context.md, params.py_context.md. Relationships: Part of orders.py flow.
  │   ├── orders.py  # Order processing (apply_orders function, integrating matching, AMM, auto-fills). Usage: Main entry; orchestrates submodules. Needed Context: amm_math.py_context.md, impact_functions.py_context.md, autofill.py_context.md, lob_matching.py_context.md, state.py_context.md. Relationships: Core API; calls submodules.
  │   ├── resolutions.py  # Resolution logic (trigger_resolution function, payouts, renormalization, virtual_yes adjustments). Usage: Resolution handling. Needed Context: state.py_context.md, params.py_context.md, utils.py_context.md. Relationships: Separate API.
  │   └── /tests
  │       ├── __init__.py  # Test setup. Usage: Minimal. Needed Context: None. Relationships: For pytest.
  │       ├── test_state.py  # Unit tests for state updates, serialization, and invariants (solvency checks). Usage: Focused tests. Needed Context: state.py_context.md. Relationships: Tests state.py.
  │       ├── test_params.py  # Unit tests for parameter interpolation and validation within safe ranges. Usage: Param tests. Needed Context: params.py_context.md. Relationships: Tests params.py.
  │       ├── test_amm_math.py  # Unit tests for quadratic solves, buy/sell functions, penalties. Needed Context: amm_math.py_context.md. Relationships: Tests amm_math.py.
  │       ├── test_impact_functions.py  # Tests for impacts, diversions. Needed Context: impact_functions.py_context.md. Relationships: Tests impact_functions.py.
  │       ├── test_autofill.py  # Tests for auto-fills, seigniorage. Needed Context: autofill.py_context.md. Relationships: Tests autofill.py.
  │       ├── test_lob_matching.py  # Tests for LOB and cross-matching. Needed Context: lob_matching.py_context.md. Relationships: Tests lob_matching.py.
  │       ├── test_orders.py  # Integration tests for apply_orders. Needed Context: orders.py_context.md (and submodules). Relationships: Tests orders.py.
  │       └── test_resolutions.py  # Unit tests for resolution flows, renormalization, multi-res scenarios. Needed Context: resolutions.py_context.md. Relationships: Tests resolutions.py.
  ├── /runner
  │   ├── __init__.py  # Exports runners. Usage: Minimal. Needed Context: None. Relationships: For imports.
  │   ├── batch_runner.py  # Main batch processing loop (run_tick function, transaction handling, engine calls). Usage: Tick execution. Needed Context: engine/orders.py_context.md, db/queries.py_context.md, services/ticks.py_context.md. Relationships: Calls engine, services.
  │   └── timer_service.py  # Background timer for resolutions, freezes, countdowns, and status updates. Usage: Time-based triggers. Needed Context: resolutions.py_context.md (service), engine/resolutions.py_context.md, config.py_context.md. Relationships: Calls resolutions service.
  ├── /scripts
  │   ├── __init__.py  # Exports scripts. Usage: Minimal. Needed Context: None. Relationships: For imports.
  │   ├── seed_config.py  # Script to seed initial config into DB (e.g., default params, reset session). Usage: DB seeding. Needed Context: db/queries.py_context.md, config.py_context.md. Relationships: Uses db for inserts.
  │   ├── export_csv.py  # Script to generate CSV exports (trades, config, metrics, rankings including gas costs). Usage: Export logic; pandas for CSV. Needed Context: db/queries.py_context.md, utils.py_context.md. Relationships: Queries db.
  │   └── generate_graph.py  # Script to generate Matplotlib graphs (volume, MM risk/profit over time using numpy for data processing). Usage: Graph gen; matplotlib/numpy. Needed Context: db/queries.py_context.md (for metrics), utils.py_context.md. Relationships: Fetches from db.
  └── /static  # Optional static assets for Streamlit UI customization
      ├── style.css  # Custom CSS for Polymarket-like aesthetics (tabs, tickets, books). Usage: CSS file; static. Needed Context: None. Relationships: Loaded by streamlit_app.py/admin.py.
      └── logo.png  # Placeholder logo or icons for UI elements. Usage: Binary; not generated as code. Needed Context: None. Relationships: Referenced in UIs.
```

---

## 12) Minimal Algorithms (baseline)

**Balance check on order entry**

* BUY: balance >= size * (limit_price or conservative est: current_p + slippage).
* SELL: Have enough tokens.

**Aggregated order book**

* Query lob_pools, aggregate volumes per tick for UI bids (buy pools descending), asks (sell ascending).

**Leaderboard**

* final_usdc = balance + payouts + unfilled_returns; %gain = (final_usdc - start)/start; trades from trade_count.

**Graph**

* From metrics table: Plot lines for volume (cumulative), mm_risk, mm_profit vs tick/time.

---

## 13) Admin Controls & Replay

* **Start/Pause:** Triggers timer/batch; automatic freezes.
* **Resolve:** Automatic; manual override if needed.
* **Reset:** Clear DB, new config.
* **Replay:** Optional—reconstruct from events/trades for scrubber.