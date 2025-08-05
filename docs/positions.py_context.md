# positions.py_context.md

## Overview
Service module for managing user positions, balances, and payouts in the Gaming Market Demo, including updates from engine fills (with fee handling and state adjustments per TDD cross-matching), resolution payouts (zeroing eliminated positions, pro-rata unfilled limits), and gas deductions on submissions. Implements TDD position tracking/payouts (actual q_yes/q_no excluding virtuals) and Implan §3 gas fees/metrics; called post-fills in batch_runner.py (Lines 1-20: Imports/Position TypedDict; 21-40: fetch_user_positions; 41-150: update_position_from_fill; 151-220: apply_payouts; 221-260: deduct_gas; 261-end: update_balance).

## Key Exports/Interfaces
- **Position** (TypedDict, Lines 15-20): {'position_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'tokens': Decimal}.
- **fetch_user_positions(user_id: str) -> List[Dict[str, Any]]** (Lines 22-40): Fetches user positions from DB, formats with usdc_amount; returns list of dicts with position data.
- **update_position_from_fill(fill: Dict[str, Any], state: EngineState) -> None** (Lines 41-150): Updates positions/balances from fill (extracts buy/sell_user_id, outcome_i, yes_no, price, size, fee); validates size/balance/tokens; updates buyer (+size tokens, - (price*size + fee/2)), seller (-size tokens, + (price*size - fee/2)); adds size to both q_yes/q_no in state per TDD cross-matching (Line 175); increments trade_counts; raises ValueError on insufficients/errors.
- **apply_payouts(resolution_data: Dict[str, Any], state: EngineState) -> None** (Lines 151-220): Applies payouts from resolution_data['payouts'] to balances/net_pnl; zeros q_yes/q_no and DB tokens for elim_outcomes; for is_final, pass for pro-rata unfilled limits from lob_pools; updates metrics with mm_profit from seigniorage sum.
- **deduct_gas(user_id: str, gas_fee: Decimal) -> None** (Lines 221-260): Deducts gas_fee from balance (raises if insufficient); updates total_gas in metrics; skips if <=0.
- **update_balance(user_id: str, delta: Decimal) -> None** (Lines 261-end): Adds delta to balance (raises if <0 post-update); uses usdc_amount for precision.

## Dependencies/Imports
- Imports: typing (List/Dict/Any/Optional), typing_extensions (TypedDict), decimal.Decimal (Lines 1-5).
- From app: db.queries (fetch_positions/update_position/update_user_position/fetch_user_position/update_user_balance/fetch_user_balance/update_metrics/get_db), engine.state (EngineState/BinaryState/get_binary), utils (usdc_amount/validate_balance_buy/validate_balance_sell/validate_size/safe_divide) (Lines 6-10).
- Interactions: Queries DB for positions/balances/metrics (e.g., fetch_user_position uses DB select); updates engine state binaries (q_yes/q_no); called by batch_runner.py post-apply_orders for fills; services_resolutions.py for payouts; services_orders.py for gas on submit (deduct_gas integrates with submit_order's always-deduct policy per Implan §3); streamlit_app.py uses fetch_user_positions for portfolio display.

## Usage Notes
- Uses Decimal for precision (e.g., price/size/fee), converts to float for DB updates/JSONB; usdc_amount ensures 6 decimals. Tie to TDD: Positions per (user_id, outcome_i, yes_no); payouts exclude virtual q0/virtual_yes (DB tokens only); updates both q_yes/q_no on fills for cross-matching consistency. Gas deducted regardless of order success; track in metrics.total_gas. For final res, implement unfilled distribution via lob_pools (incomplete: Line 200 pass). Deterministic: Validates positives, raises on errors; trade_count via direct DB updates.

## Edge Cases/Invariants
- Edges: Zero size/gas skipped; negative tokens/balances raise ValueError (e.g., seller_new_tokens <0); empty payouts/elims noop; is_final without lob integration skips distribution.
- Invariants: Post-update balance >=0; tokens >=0 per position; size >0 via validate_size; q_yes/q_no +=size preserves TDD solvency (q < L_i via engine); N_active implicit in state.active (not handled here); assumes fill['fee'] total, split /2.

## Inconsistencies/Possible Issues
- Always adds size to both q_yes and q_no (Lines 115-118) regardless of yes_no or fill_type, but per TDD derivations, AMM/LOB buys add only to q_yes (or q_no), while cross-matches add to both; mismatch if fills include non-cross (check engine_orders.py for fill generation; services_orders.py_context.md notes fills with 'source'='lob'/'amm', but code ignores—potential over-inflation of q_no or q_yes, breaking solvency/invariants).
- fetch_user_position assumes exists (returns 0 if none?), but Decimal(str(...)) may error if None/float; services_orders.py uses for validation, but if new position, needs handling (e.g., default 0).
- In apply_payouts, zeros all positions for elim_outcome (DB update {'tokens':0}), but TDD payouts pay NO for elim (YES=0), assuming burn; code adds payout to balance/net_pnl without burning tokens—ensure burn in services_resolutions.py (per TDD).
- Unfilled limits distribution incomplete (Line 200 pass); integrate with lob_matching.py for pro-rata from state['lob_pools'], update balances (ties to TDD final res).
- Trade_count update fetches via select/execute (Lines 122-140), but potential race if concurrent; use atomic upsert.
- streamlit_app.py_context.md uses fetch_user_positions for portfolio, but returns usdc_amount(tokens) as Decimal—ensure UI handles Decimal/float conversion.
- ticks.py_context.md normalizes fills but no direct position update; assume batch_runner calls this post-fills, but if ticks creates summary pre-update, q_yes/q_no mismatch.