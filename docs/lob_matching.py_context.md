# lob_matching.py_context.md

## Overview
Core engine module for limit order book (LOB) pool management and matching in the Gaming Market Demo, implementing add/cancel from pools, cross-matching YES/NO limits (peer-to-peer with true limit price enforcement and fees), and market order matching against LOB pools (at limit prices with separate fees). Implements TDD LOB/cross mechanics (Derivations/Proofs) and Implan §3/§4 engine API for batched LOB; called by engine_orders.py for LIMIT adds/cancels and MARKET/ cross fills (Lines 1-30: Imports/constants; 31-100: Pool utils/add_to_lob_pool; 101-150: cancel_from_pool; 151-300: cross_match_binary; 301-end: match_market_order).

## Key Exports/Interfaces
- **LIMIT_YES_POOL_USER_ID/LIMIT_NO_POOL_USER_ID/LIMIT_POOL_USER_ID/MARKET_USER_ID** (str, Lines 15-19): Constants for pool/AMM fill attribution (UUIDs for DB compat).
- **get_pool_key(tick: int, af_opt_in: bool) -> int** (Lines 22-23): Returns tick if af_opt_in else -tick for pool indexing.
- **get_tick_from_key(key: int) -> int** (Line 25): Returns abs(key).
- **is_opt_in_from_key(key: int) -> bool** (Line 28): Returns key >=0.
- **add_to_lob_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, amount: Decimal, af_opt_in: bool, tick_size: Decimal = None) -> None** (Lines 31-100): Adds amount to LOB pool at tick (validates active/binary/tick bounds/size); buy pools store USDC volume (amount*price), sell store token volume; shares track tokens; validates semantics post-add (rollback on fail).
- **cancel_from_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, af_opt_in: bool, tick_size: Decimal = None) -> Decimal** (Lines 102-150): Cancels user's share from pool (reduces volume per semantics: buy share*price, sell share); returns share; cleans empty pools.
- **cross_match_binary(state: EngineState, i: int, params: EngineParams, current_ts: int, tick_id: int) -> List[Dict[str, Any]]** (Lines 152-300): Matches YES buy pools (highest tick first) with NO sell pools (tick_no >= comp_tick_no, ascending); checks T + S >= 1 + f_match*(T+S)/2; fills min(USDC/price_yes, tokens); fees f_match*(T+S)*fill/2 (split); updates V += (T+S)*fill - fee, q_yes/no +=fill; reduces volumes/shares proportionally; validates semantics (rollback on fail); returns fills with price_yes/no.
- **match_market_order(state: EngineState, i: int, is_buy: bool, is_yes: bool, size: Decimal, params: EngineParams, current_ts: int, tick_id: int) -> tuple[List[Dict[str, Any]], Decimal]** (Lines 302-end): Matches market order vs opposing LOB pools (buy: lowest sell ticks ascending; sell: highest buy descending); fills at limit price + separate fee (f*fill*price, split? but code appends fee total); reduces volumes/shares proportionally; cleans empty; returns fills (single price) and remaining unfilled.

## Dependencies/Imports
- Imports: decimal.Decimal, typing (List/Dict/Any), typing_extensions.TypedDict, uuid (Lines 1-4).
- From .: state (EngineState/BinaryState/get_binary/update_subsidies), params (EngineParams), utils (usdc_amount/price_value/validate_price/validate_size/safe_divide/validate_lob_pool_volume_semantics), amm_math (get_effective_p_yes/no) (Lines 6-12).
- Interactions: Updates state binaries in-place (lob_pools, V, q_yes/no, subsidies); called by engine_orders.py for LIMIT (add/cancel), cross (cross_match_binary per binary), MARKET (match_market_order before AMM); fills used by positions.py (update from fill), ticks.py (normalize/classify), batch_runner.py (via apply_orders).

## Usage Notes
- Uses Decimal for precision (volume/shares), float for state q/V (JSONB); tie to TDD: True limit enforcement (users pay/receive exact limits, fees separate); cross solvency via min_sum check; buy pools USDC volume, sell token volume; tick=int(price/tick_size); fallback tick_size=0.01 if None/state lacks; deterministic sorted keys (cross: highest YES buy first, comp NO ascending; market: buy lowest sell ascending, sell highest buy descending); validates active binary; cross fills have price_yes/no, market single price; updates both q_yes/no on cross (per TDD), none on market (handled higher); proportional share reduction preserves semantics.

## Edge Cases/Invariants
- Edges: Empty pools/no matches → [] fills/remaining=size; fill=0 skipped; invalid tick/active → raise ValueError; volume<=0 cleans pool; post-reduction validation fails → full rollback (cross only; market no validation); tick<=0 fallback raise.
- Invariants: Pool volume semantics (buy: volume==sum(shares)*price; sell: volume==sum(shares)); q_yes/no < L_i preserved (cross net collateral >=fill via check); deterministic sort (reverse=True for high first); shares >=0, volume>=0; N_active implicit (all binaries assumed active here).

## Inconsistencies/Possible Issues
- Cross fills update both q_yes/no +=fill (Lines 209-210), consistent with TDD cross but positions.py_context.md adds both regardless (potential over-add for non-cross); engine_orders.py_context.md notes mismatch—ensure engine_orders handles market/LOB adds only one.
- Market fills use fee_rate=params['f'] or 'fee_rate' (Line 376), but TDD f_match for cross/matches—code uses f for LOB/market (consistent? TDD f on trades, f_match on cross); positions.py_context.md splits fee/2 but market appends total fee (Line 366)—split inconsistency.
- No q updates in match_market_order (unlike cross)—must be in engine_orders; if missing, q under-update for LOB/market, breaking solvency (check engine_orders.py_context.md: AMM updates one q, LOB may not).
- Ticks.py_context.md classifies 'CROSS_MATCH' if price_yes/no (present in cross fills), 'LOB_MATCH' else (market fills single price)—matches; but extract_events hardcodes f_match=0.02 vs params['f_match']—use params.
- Services_orders.py_context.md cancel uses cancel_from_pool (consistent); streamlit_app.py_context.md displays books from pools (fetch_pools uses db, but state has lob_pools—sync via batch_runner save).
- Cross cleans pools if volume<=0 but reduces shares proportionally even if >0 (Lines 256-270 duplicate 226-240)—redundant but harmless; potential float precision loss (state float vs Decimal).