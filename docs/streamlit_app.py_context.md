# streamlit_app.py_context.md

## Overview
Streamlit script for the participant UI in the Gaming Market Demo, managing join flows, status-based displays (lobby/frozen/resolved), trading interfaces with outcome tabs (order tickets/books/trades), portfolio views, and realtime refreshes via polling (rerun on tick changes/1s intervals). Implements Implan §7 participant flows with Polymarket-like UX, transaction confirmations (estimates/fees/returns/risks), and validations per TDD (e.g., slippage est via services, true limit enforcement notes). Updated with improved selectors (e.g., keys on tabs/expanders for robustness), pre-submit warnings in confirmation expander (e.g., insufficient balance including gas), and gas spent metric placeholder in portfolio summary.

**Notes for Updating test_demo.py**: Incorporate new keys for selectors (e.g., "outcome-tabs" for tabs, "order-expander-{order_id}" for cancel expanders) to scope CSS/XPATH (e.g., `[key="outcome-tabs"] button:nth-child({outcome+1})` for tabs, reducing offsets; `[key="order-expander-{order_id}"]` for expanders, but since test lacks order_id in sequence, add logic to fetch latest order_id via page_source or assume single). Use child data-testid for metrics (e.g., `[data-testid="stMetricValue"]`) to fix sibling mismatches. Extend waits/polling to 3-5s for lazy loads; add checks for new warnings (e.g., "Insufficient balance" in page_source to verify pre-submit errors). Test confirmation expander content (e.g., extract est_cost/gas_fee via XPATH) for accurate polling (include gas in balance change assumptions). These changes enhance robustness without breaking existing text/XPATH fallbacks.

## Generated DOM
Streamlit generates dynamic HTML; below is a mocked structure based on the code (using Selenium-compatible selectors like data-testid, classes from Streamlit v1.37+). Root is <div id="root">; elements have classes like "stTextInput", "stButton". Use Selenium By.CSS_SELECTOR or By.XPATH for robustness, e.g., driver.find_element(By.CSS_SELECTOR, '[data-testid="stMetricValue"]') for balance/price values (now more reliable as children). Added keys (e.g., key="outcome-tabs") enable scoping like [key="outcome-tabs"].

```html
<html>
  <body>
    <div id="root" class="stApp">
      <!-- Join Form (if no user_id; Lines 21-30) -->
      <div class="row-widget stHorizontal">
        <div data-testid="stTextInput" class="stTextInput">
          <label>Enter display name</label>
          <input type="text" value="" key="display-name-input">
        </div>
        <button data-testid="baseButton-secondary" class="stButton" key="join-button">Join</button>
      </div>

      <!-- Waiting Room (DRAFT status; Lines 61-120) -->
      <h1 data-testid="stMarkdown" class="stMarkdown">🎮 Gaming Market Demo</h1>
      <h2 data-testid="stMarkdown" class="stMarkdown">⏳ Waiting Room</h2>
      <div data-testid="stInfo" class="stAlert">👥 **X players joined** - Waiting for admin to start the demo...</div>
      <div class="row-widget stHorizontal"> <!-- Manual refresh; centered col -->
        <button data-testid="baseButton-primary" class="stButton">🔄 Check Status</button>
      </div>
      <h3 data-testid="stMarkdown" class="stMarkdown">👥 Joined Players</h3>
      <div class="row-widget stHorizontal"> <!-- Grid cols for players -->
        <div class="stMarkdown">• Player1</div>
        <!-- Repeated per player -->
      </div>
      <div data-testid="stMarkdown" class="stMarkdown">---</div>
      <div class="row-widget stHorizontal">
        <div data-testid="stMarkdown" class="stMarkdown">🔄 Auto-checking every 3 seconds... (Check #Y)</div>
        <div data-testid="stMarkdown" class="stMarkdown">🟢 Just checked - Status: DRAFT</div>
      </div>

      <!-- Frozen Warning (FROZEN status; Lines 121-140) -->
      <div data-testid="stWarning" class="stAlert">⏸️ **Trading is currently frozen**</div>
      <div data-testid="stInfo" class="stAlert">The admin has temporarily paused trading. Please wait for trading to resume.</div>
      <button data-testid="baseButton-secondary" class="stButton">🔄 Check Status</button>

      <!-- Resolved Display (RESOLVED status; Lines 141-150) -->
      <div data-testid="stMarkdown" class="stMarkdown">Market resolved</div>
      <div data-testid="stDataFrame" class="stDataFrame"> <!-- Table of rankings -->
        <table><thead><tr><th>Name</th><th>Net PNL</th><th>% Gain</th><th>Trades</th></tr></thead><tbody><!-- Rows --></tbody></table>
      </div>
      <div data-testid="stPyplot" class="stPyplot"> <!-- Graph from generate_graph() --></div>

      <!-- Trading Interface (RUNNING status; Lines 151-200: Metrics) -->
      <div data-testid="stMetric" class="stMetric">
        <div data-testid="stMetricLabel">Time to End</div>
        <div data-testid="stMetricValue">Z seconds</div>
      </div>
      <div data-testid="stMetric" class="stMetric">
        <div data-testid="stMetricLabel">Balance</div>
        <div data-testid="stMetricValue">$W.XX</div>
      </div>
      <!-- Sidebar Leaderboard (Lines 201-210) -->
      <div data-testid="stSidebar" class="stSidebar">
        <h2 data-testid="stMarkdown" class="stMarkdown">Leaderboard</h2>
        <div data-testid="stMarkdown" class="stMarkdown">1. PlayerA: $V.UU</div>
        <!-- Repeated -->
      </div>

      <!-- Outcome Tabs (Lines 211-500); now with key="outcome-tabs" -->
      <div data-testid="stTabs" class="stTabs" key="outcome-tabs">
        <div role="tablist">
          <button role="tab">Outcome 1</button>
          <!-- Per outcome -->
        </div>
        <div role="tabpanel"> <!-- Active tab content -->
          <div class="row-widget stHorizontal"> <!-- Col1: Order Ticket -->
            <h2 data-testid="stMarkdown" class="stMarkdown">Order Ticket</h2>
            <div data-testid="stRadio" class="stRadio" key="yes-no-radio-0">
              <label>Token</label>
              <input type="radio" value="YES" checked>
              <input type="radio" value="NO">
            </div>
            <div data-testid="stRadio" class="stRadio" key="buy-sell-radio-0">
              <label>Direction</label>
              <input type="radio" value="Buy" checked>
              <input type="radio" value="Sell">
            </div>
            <div data-testid="stSelectbox" class="stSelectbox" key="order-type-select-0">
              <label>Type</label>
              <select><option>MARKET</option><option>LIMIT</option></select>
            </div>
            <div data-testid="stNumberInput" class="stNumberInput" key="size-input-0">
              <label>Size</label>
              <input type="number" value="1.0" min="0.01">
            </div>
            <!-- Conditional: Limit Price or Max Slippage -->
            <div data-testid="stNumberInput" class="stNumberInput" key="limit_price_0"> <!-- If LIMIT -->
              <label>Limit Price</label>
              <input type="number" value="0.5" min="0.0" max="1.0" step="0.01">
            </div>
            <div data-testid="stNumberInput" class="stNumberInput" key="max_slippage_0"> <!-- If MARKET -->
              <label>Max Slippage %</label>
              <input type="number" value="5.0" min="0.0">
            </div>
            <div data-testid="stCheckbox" class="stCheckbox" key="af_opt_in_0"> <!-- If af_enabled -->
              <input type="checkbox" checked> Auto-Fill Opt-In
            </div>
            <div data-testid="stExpander" class="stExpander" expanded="true">
              <summary>📋 Transaction Confirmation</summary>
              <!-- Subsections: Summary, Fees, Returns; cols with st.write; now with warnings like insufficient balance -->
              <div class="row-widget stHorizontal">
                <div><p><strong>Token:</strong> YES</p><!-- etc --></div>
                <div><p><strong>Order Type:</strong> MARKET</p><!-- etc --></div>
              </div>
              <!-- Fee Breakdown, Potential Returns, Warnings (e.g., st.warning for balance) -->
            </div>
            <button data-testid="baseButton-secondary" class="stButton" key="submit-order-button-0" disabled="false">Submit Order</button>
          </div>
          <div class="row-widget stHorizontal"> <!-- Col2: Order Book -->
            <h2 data-testid="stMarkdown" class="stMarkdown">📊 Order Book</h2>
            <!-- Metrics: YES/NO Prices -->
            <div class="row-widget stHorizontal">
              <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">YES Market Price</div><div data-testid="stMetricValue">$0.ABCD</div></div>
              <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">NO Market Price</div><div data-testid="stMetricValue">$0.EFGH</div></div>
            </div>
            <p><strong>Spread:</strong> $0.IJKL</p>
            <div data-testid="stTabs" class="stTabs"> <!-- YES/NO Tabs -->
              <div role="tablist"><button role="tab">📈 YES Token</button><button role="tab">📉 NO Token</button></div>
              <div role="tabpanel"> <!-- YES Token -->
                <h3 data-testid="stMarkdown" class="stMarkdown">YES Token Order Book</h3>
                <p><strong>🔴 Asks (Sellers)</strong></p>
                <div data-testid="stDataFrame" class="stDataFrame"><table><!-- Price, Volume, Your Share, User --></table></div>
                <p><strong>📊 Current Market Price: $0.MNOP</strong></p>
                <p><strong>🟢 Bids (Buyers)</strong></p>
                <div data-testid="stDataFrame" class="stDataFrame"><table><!-- Similar --></table></div>
              </div>
            </div>
          </div>
        </div>
        <h2 data-testid="stMarkdown" class="stMarkdown">Recent Trades</h2>
        <div data-testid="stTable" class="stTable"><table><!-- Price, Size, Side --></table></div>
      </div>

      <!-- Portfolio (Lines 501-800) -->
      <h2 data-testid="stMarkdown" class="stMarkdown">💼 Your Portfolio</h2>
      <div data-testid="stTabs" class="stTabs">
        <div role="tablist"><button role="tab">🏆 Filled Positions</button><button role="tab">⏳ Open Limit Orders</button><button role="tab">📊 Portfolio Summary</button></div>
        <div role="tabpanel"> <!-- Filled Positions -->
          <h3 data-testid="stMarkdown" class="stMarkdown">🏆 Your Filled Positions</h3>
          <div data-testid="stDataFrame" class="stDataFrame"><table><!-- Outcome, Token, Tokens, Current Value, Max Payout, Potential Profit, Return Multiple --></table></div>
          <!-- Metrics cols -->
          <div class="row-widget stHorizontal">
            <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Total Positions</div><div data-testid="stMetricValue">R</div></div>
            <!-- Similar for Current Value, Max Potential -->
          </div>
        </div>
        <div role="tabpanel"> <!-- Open Orders -->
          <h3 data-testid="stMarkdown" class="stMarkdown">⏳ Your Open Limit Orders</h3>
          <div data-testid="stExpander" class="stExpander" expanded="true" key="order-expander-ID">
            <summary>📋 Order #S - YES LIMIT</summary>
            <!-- Cols with details, potential returns, cancel button with confirm -->
            <div class="row-widget stHorizontal">
              <div><p><strong>Token:</strong> YES</p><!-- etc --></div>
              <div><p><strong>Limit Price:</strong> $0.TUVW</p><!-- etc --></div>
              <div><!-- Potential returns if LIMIT --></div>
            </div>
            <div data-testid="stMarkdown" class="stMarkdown">---</div>
            <div class="row-widget stHorizontal">
              <div data-testid="stMarkdown" class="stMarkdown">💡 **Tip:** You can cancel this order anytime to free up your funds</div>
              <button data-testid="baseButton-secondary" class="stButton" key="cancel-order-button-ID-X">🗑️ Cancel Order</button>
              <!-- If pending: Warning and Yes/No buttons -->
            </div>
          </div>
          <!-- Repeated per order -->
        </div>
        <div role="tabpanel"> <!-- Summary -->
          <h3 data-testid="stMarkdown" class="stMarkdown">📊 Portfolio Summary</h3>
          <div class="row-widget stHorizontal">
            <div><p><strong>📈 Current Holdings</strong></p><p>• Outcome Y: Z.AA YES tokens</p><!-- etc --></div>
            <div><p><strong>⏳ Pending Orders</strong></p><p>• LIMIT BB.CC YES @ $0.DD</p><!-- etc --></div>
          </div>
          <div data-testid="stMarkdown" class="stMarkdown">---</div>
          <p><strong>🎯 Portfolio Metrics</strong></p>
          <div class="row-widget stHorizontal">
            <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Active Positions</div><div data-testid="stMetricValue">EE</div></div>
            <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Open Orders</div><div data-testid="stMetricValue">FF</div></div>
            <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Capital Committed</div><div data-testid="stMetricValue">$GG.HH</div></div>
            <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Max Potential Payout</div><div data-testid="stMetricValue">$II.JJ</div></div>
          </div>
          <div data-testid="stMetric" class="stMetric"><div data-testid="stMetricLabel">Gas Spent</div><div data-testid="stMetricValue">$0.00</div></div>
        </div>
      </div>

      <!-- Refresh Button (Line 801) -->
      <button data-testid="baseButton-secondary" class="stButton" key="refresh-button">Refresh</button>
    </div>
  </body>
</html>
```

## Key Exports/Interfaces
No exports (executable script); internal components:
- Join handling (Lines 21-60): Conditional form; calls insert_user, sets session_state.
- Status displays (Lines 61-150): if/else for DRAFT/FROZEN/RESOLVED with UI elements, auto-rerun logic.
- Metrics/Leaderboard (Lines 151-210): st.metric for time/balance; sidebar writes for top 5 users.
- Outcome tabs (Lines 211-500): Loop over tabs with key="outcome-tabs"; cols for ticket/book; radios/selectbox/inputs/buttons; expander for confirmation with added warnings.
- Portfolio tabs (Lines 501-800): Tabs for positions/orders/summary; dataframes/expanders/metrics with gas spent; cancel with session_state pending/confirm buttons, expanders keyed by order_id.

## Dependencies/Imports
- Imports: streamlit.st, time, uuid.uuid4, typing.Dict/Any/List/Optional, decimal.Decimal, datetime.datetime (Lines 1-6).
- From app: config.get_supabase_client, utils (get_current_ms/usdc_amount/price_value/validate_size/validate_price/validate_limit_price_bounds), db.queries (load_config/insert_user/fetch_user_balance/fetch_positions/fetch_user_orders/get_current_tick/fetch_pools/fetch_engine_state), services.orders (submit_order/cancel_order/get_user_orders/estimate_slippage), services.positions (fetch_user_positions), engine.state (get_binary/get_p_yes/get_p_no) (Lines 7-15).
- Interactions: Calls services for submits/cancels/estimates; queries DB for data; uses engine for prices; reruns for realtime (session_state last_check/tick).

## Usage Notes
Implements Implan §7 UI with transaction confirmations (estimates via slippage service, fees separate per TDD UX, returns/risks, pre-submit warnings); af_opt_in checkbox if enabled; true limit enforcement info; polls 1s for tick changes (rerun if > last_tick); Decimal for precision (convert via usdc_amount/price_value); integrates multi-res via n_outcomes in config; gas_fee in confirmation but deducted in services. Gas spent metric assumes DB fetch (placeholder $0.00; update to query if added).

**Notes for test_demo.py**: Leverage new keys (e.g., [key="outcome-tabs"] for tabs to avoid nth-child offsets; [key="order-expander-{order_id}"] for expanders, but derive order_id from sequence or page). Check expander warnings (e.g., "Insufficient balance" text) in polling to verify validations. Use [data-testid="stMetricValue"] directly for balance/price (child of stMetric). Extend sleeps to 3s for loads; add case-insensitive text matches.

## Edge Cases/Invariants
- No user_id → stop after join; DRAFT/FROZEN/RESOLVED → stop/disable submits; zero pools/positions → empty/infos; est reject disables button; cancel pending uses unique keys/session del on confirm; ISO ts parsing fixes decimals (Lines 151-180); poll counter <100 prevents loops; invariants: balance >=0 (via services), deterministic rerun (DB-sorted? assume), q_eff < L_i via engine.
- New: Confirmation warnings prevent submits on low balance (est_cost + gas > balance), but test should mock low balance to verify disable.

## Inconsistencies/Possible Issues
- Est trading_fee for LIMIT uses f_match but TDD f_match only on cross (f on AMM if matched? Lines 300-350)—over-est if unmatched; MARKET est_cost from slippage service but UI assumes /size for effective (potential mismatch if partial fills).
- Positions basis fallback 0.5 if engine fail (Lines 550-600)—inaccurate without history; suggest avg from trades.
- Cancel rerun on confirm may flicker (Lines 700-750); use st.form for better UX.
- Polling may lag >500ms; consider WebSocket ext per Implan.
- Unfilled limits at res not handled (per TDD, but code skips); tie to resolutions.py.
- New: Gas spent placeholder assumes DB column; if not, remove or fetch from trades (sum gas_fee per user). Test polling may need to ignore gas deductions in balance checks (or mock gas=0).