# test_demo.py_context.md

## Overview
Selenium-based end-to-end test script for the Gaming Market Demo UI, implementing automated admin actions (reset/start demo), user joins on multiple ports, and a sequence of market/limit orders/cancels across two testers (Tester1/2) to verify flows like cross-matching/auto-filling per Implan §7 and TDD UX (e.g., order tickets, portfolio updates). Handles environment detection (WSL/headless) with Chrome options, polls for updates instead of fixed sleeps, and logs detailed steps/errors for debugging; assumes apps running on localhost:8501/8502/8503 and default config (n_outcomes>=3, cm/af enabled).

## Selectors
The script interacts with the Streamlit-generated DOM (as described in streamlit_app.py_context.md) using Selenium By.CSS_SELECTOR, By.XPATH, and text matching for robustness, as Streamlit elements lack custom IDs but use data-testid (e.g., stTextInput, stButton). Key selection strategies:

- **Admin Login/Buttons (Lines 90-150)**: Password input via `[data-testid='stTextInput'] input`; buttons by `[data-testid='stButton'] button` then case-insensitive text match (e.g., "Reset Demo", "Confirm Reset", "Start Demo"). Relies on presence_of_all_elements_located and loop for text; potential issue: If multiple stButton on page, may mis-select if text not unique (e.g., other "Confirm" buttons).
- **Join Interface (Lines 160-250 in join_as_user)**: Display name via `[data-testid='stTextInput'] input`; Join button by `[data-testid='stButton'] button` with case-insensitive "Join". Checks page_source (lowercase) for "Waiting Room"/"Enter display name"/"Balance" to verify state; logs page preview on errors. Waits for `[data-testid="stMetricValue"]` post-join.
- **Balance Metric (Lines 260-280 in get_balance, also used in polling)**: Primary CSS `[data-testid="stMetricValue"]` (direct child value); assumes first is balance (scope by parent if multiple). Matches streamlit_app.py_context.md DOM, robust to layout changes.
- **Outcome Tabs (Lines 290-320 in get_yes_price/place_market_order)**: Scoped with `[key="outcome-tabs"] button:nth-child({outcome+1})`; fallback `[key="outcome-tabs"] div[role="tab"]:nth-child({outcome+1})`. Matches DOM with key; nth-child assumes fixed order, robust for n_outcomes<=10.
- **YES/NO and Buy/Sell Radios (Lines 350-400)**: Scoped by key (e.g., `[key="yes-no-radio-{outcome}"] label`) then case-insensitive text match (e.g., "YES", "Buy"); loops over labels to click matching. Robust to multiple radios via key scoping.
- **Order Type Select (Lines 410-420)**: `[data-testid="stSelectbox"][key="order-type-select-{outcome}"] select` then Select.by_visible_text("MARKET"/"LIMIT"). Uses outcome-scoped key, matching DOM; robust.
- **Size/Limit Inputs (Lines 430-450)**: Number inputs via `[data-testid="stNumberInput"][key="size-input-{outcome}"] input` or key="limit_price_{outcome}"; clear/send_keys. Scoped by outcome key.
- **Submit Button (Lines 460-470)**: `[data-testid="stButton"][key="submit-order-button-{outcome}"] button`; clickable wait. Scoped.
- **Polling for Updates (Lines 480-500)**: Refreshes page, checks get_balance change OR page_source for "order filled" (lowercase); timeout 15s, interval 2s; assumes update signals fill—may false-negative if net-zero but mitigated by text check.
- **Portfolio/Cancel (Lines 550-650 in cancel_order)**: Portfolio tab by `button[role='tab']` case-insensitive "portfolio"; open orders by nth-child(2); expander by `details summary` text "Order #"/yes_no (parse ID for key="cancel-order-button-{order_id}-0"); cancel/confirm by case-insensitive text. Attempts key use; issue: If ID parse fails or multiple, may select wrong (first matching).
- Conflicts with streamlit_app.py_context.md: Selectors now align better (keys/data-testid used); text/XPATH case-insensitive; portfolio tabs by text/role robust. For metrics/radios, key scoping reduces cross-tab bleed. Waits/EC replace sleeps for loads. Overall, selectors more robust but still text-dependent for cancel/portfolio tabs.

## Key Exports/Interfaces
- **ENABLED_FEATURES** (dict, Lines 70-75): {'cross_matching': True, 'auto_filling': True}; toggles for test variants.
- **run_admin_test() -> None** (Lines 80-160): Sets up Chrome (headless/WSL options), logs in admin (password "talus123"), resets/starts demo; keeps open. Params: None. Returns: None. Raises: Exception on button not found/errors.
- **join_as_user(driver: WebDriver, wait: WebDriverWait, username: str, port: int=8501) -> None** (Lines 170-260): Navigates to port, enters username, joins; checks for balance/portfolio elements post-join. Params: Selenium driver/wait, username, optional port. Returns: None (False if waiting room). Raises: Exception on elements not found.
- **get_balance(driver: WebDriver, wait: WebDriverWait) -> Optional[float]** (Lines 270-280): Extracts balance via data-testid; strips $/. Params: driver/wait. Returns: Float or None on error.
- **get_yes_price(driver: WebDriver, wait: WebDriverWait, outcome: int) -> Optional[float]** (Lines 290-320): Selects outcome tab (key-scoped nth-child/fallback), extracts YES price via data-testid. Params: driver/wait, outcome (0-index). Returns: Float or None.
- **place_market_order(driver: WebDriver, wait: WebDriverWait, outcome: int, yes_no: str, buy_sell: str, size: float) -> None** (Lines 330-520): Places market order; selects tab/radios/selectbox/input/button; polls balance change or text (15s timeout); basic checks (balance decrease on buy, price increase). Params: driver/wait, outcome, yes_no ('YES'/'NO'), buy_sell ('Buy'/'Sell'), size. Returns: None. Raises: TimeoutError/Exceptions on no change/errors.
- **place_limit_order(driver: WebDriver, wait: WebDriverWait, outcome: int, yes_no: str, buy_sell: str, size: float, price: float, af_opt_in: bool=True) -> None** (Lines 530-620): Similar to market but selects LIMIT, enters price, checks af_opt_in if True; polls balance or text. Params: As market plus price, optional af_opt_in. Returns: None. Raises: As market.
- **cancel_order(driver: WebDriver, wait: WebDriverWait, outcome: int, yes_no: str) -> None** (Lines 630-720): Selects portfolio/open orders tab, finds expander by text (parses ID for key), clicks cancel/confirm; polls balance increase or text. Params: driver/wait, outcome, yes_no. Returns: None. Raises: As market.
- **run_user_tests() -> None** (Lines 730-850): Sets up two drivers (ports 8501/8502), joins Tester1/2, runs sequence of 15 orders/cancels (e.g., market buy/sell, limit buy/sell at prices like 0.60/0.65, cross outcomes). Params: None. Returns: None. Raises/Logs: Errors with browser logs/screenshots.
- **if __name__ == "__main__"** (Lines 860-end): Runs run_admin_test, sleeps 5s, then run_user_tests.

## Dependencies/Imports
- Imports: selenium (webdriver/options/service/By/WebDriverWait/expected_conditions/Select/exceptions), time, os, sys, platform, uuid (Lines 1-10).
- Interactions: Assumes streamlit_app.py/streamlit_admin.py running; uses ChromeDriver (/usr/local/bin/chromedriver binary); environment checks (WSL/DISPLAY) for options; no direct app imports—pure automation.

## Usage Notes
- Runs as `python test_demo.py`; assumes Chrome/ChromeDriver installed (Google Chrome for WSL); skips if WSL without DISPLAY (instructions printed, Lines 30-50). Tests default config (cm/af enabled, n_outcomes>=3); toggle ENABLED_FEATURES for variants. Polls/refresh for async updates (addressing Implan §7 realtime issues); logs verbose steps/page_source/browser logs/screenshots on errors for debugging UI mismatches. Implements Implan §7 flows (join/order/portfolio) and TDD UX (confirmations implicit in actions); sequence tests cross-impacts (e.g., Outcome1/2 orders).

## Edge Cases/Invariants
- Edges: WSL no DISPLAY → sys.exit(0); button not found → raise with screenshot/logs; no balance change post-order → TimeoutError (mitigated by text check); browser crash → log errors/screenshots on quit (Lines 840-850). Assumes TEST_OUTCOMES=3 (Line 20); adjust for config.
- Invariants: Deterministic sequence (fixed orders); balance/price checks post-actions (warnings if unexpected, e.g., no decrease on buy); extended waits (3-5s effective via EC); drivers quit in finally.

## Inconsistencies/Possible Issues
- Balance selector uses [data-testid="stMetricValue"] (assumes first is balance)—may grab wrong if multiple metrics; suggest add label scoping (e.g., '//div[contains(text(), "Balance")]/following::[data-testid="stMetricValue"]') as fallback.
- Tab selectors use key + nth-child, robust but if app adds tabs, offsets; verify order.
- Radio/button text matches case-insensitive; safe for casing but fragile to text changes. Key scoping reduces conflicts.
- Cancel expander attempts ID parse for key, but if fails, falls back to text—may cancel wrong with multiples; app expanders keyed by order_id—improve parse logic.
- Polling assumes balance change or "order filled" signals fill, but if net-zero/gas-only, timeout; text check mitigates.
- Conflicts with streamlit_app.py_context.md: Selectors now align (keys/data-testid, case-insensitive); waits/EC for loads; portfolio tabs by text/role safe. App expander expanded=True for confirmation, but test submits without interacting—assumes no modal block (add check for disabled button if needed). Overall, selectors robust vs data-testid/key.