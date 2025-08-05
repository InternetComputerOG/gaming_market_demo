# order-processing-audit-checklist.md

## Overview
This audit checklist is designed to guide an AI Coding Assistant through a systematic review and resolution of issues in the Gaming Market Demo's order processing flow. It is based on a comprehensive analysis of the "Gaming Market TDD.md" (core design principles, including distinct q_yes/q_no updates for AMM/LOB vs. cross-matches, solvency invariants like q < L_i, true limit price enforcement with separate fees, and auto-filling/seigniorage mechanics) and "Implementation Plan for Gaming Market Demo.md" (batch-based execution, engine interfaces like apply_orders, gas deductions on submission regardless of success, max slippage rejection, and position updates from fills). 

The checklist draws from inconsistencies noted in the provided _context.md files, prioritizing legitimacy (e.g., confirmed mismatches with TDD) and severity (e.g., solvency risks as High). Each item includes:
- **Description**: The issue and its impact.
- **Relevant Context**: Key excerpts from TDD/Implan/_context.md files.
- **Steps to Audit/Fix**: Granular actions, including code locations, tests to add, and validation criteria.
- **Priority Rationale**: Why High/Medium/Low.

Items are grouped by severity: **High** (solvency/functional breaks), **Medium** (inaccuracies affecting UX/estimates), **Low** (optimizations/precisions). Focus on High first to ensure core integrity.

## High Severity Items
These could break solvency invariants (e.g., q_yes + q_no < L_i per binary), lead to incorrect payouts, or cause cascading errors in batch processing. Prioritize: Audit engine_orders.py, positions.py, and batch_runner.py integrations.

1. [ ] **q_yes/q_no Update Mismatch Across Fills**: Positions.py always adds fill size to both q_yes and q_no, but TDD requires this only for cross-matches (both updated), while AMM/LOB/auto-fills update only one (YES or NO). This over-inflates q, potentially violating solvency (payouts > L_i) and causing invariant failures in validations.
  - **Relevant Context**: TDD Derivations: Cross-matching updates both q_yes/no += Δ; AMM buy YES updates only q_yes += Δ. positions.py_context.md: "Always adds size to both q_yes and q_no (Lines 115-118) regardless of yes_no or fill_type". engine_orders.py_context.md: "AMM updates only one q (Lines 237-251)". autofill.py_context.md: "Updates one q (Lines 373-377)". lob_matching.py_context.md: "Cross updates both (Lines 209-210); market no updates". batch_runner.py_context.md: "Assumes fills add to both via positions.py".
  - **Steps to Audit/Fix**:
    1. In positions.py, add logic to check fill_type (e.g., if 'CROSS_MATCH', add to both; else add to q_{yes_no}). Use ticks.py classification ('CROSS_MATCH' if price_yes/no present).
    2. Modify engine_orders.py and lob_matching.py to include 'fill_type' in Fill dict (e.g., 'CROSS_MATCH', 'LOB_MATCH', 'AMM', 'AUTO_FILL').
    3. Update autofill.py to set 'fill_type'='AUTO_FILL' in events (treat as AMM: update one q).
    4. Add unit test in engine/tests/test_orders.py: Simulate AMM buy YES (assert only q_yes +=size), cross-match (both +=size); validate solvency post-update (q_yes + q_no < L_i).
    5. In batch_runner.py, after apply_orders, log/validate state solvency before save.
    6. Rerun full batch trace: Submit AMM/LOB/cross orders; check DB positions/state q match TDD.
  - **Priority Rationale**: High – Direct solvency risk; could lead to over-payouts or validation raises halting batches.

2. [ ] **Missing q Updates in LOB Market Matches**: lob_matching.py's match_market_order doesn't update q_yes/no (expects higher-level), but engine_orders.py may not handle it, leading to under-updates and solvency breaks (payouts uncovered).
  - **Relevant Context**: TDD: Market orders vs LOB should update the traded q (e.g., buy YES: q_yes +=size). lob_matching.py_context.md: "No q updates in match_market_order (unlike cross)". engine_orders.py_context.md: "MARKET: match_lob then AMM; AMM updates one q, but LOB not explicit". positions.py_context.md: "Updates from fill, but assumes both q – mismatch if engine doesn't update state q for LOB".
  - **Steps to Audit/Fix**:
    1. In engine_orders.py, after match_market_order (Lines 151-300), add q updates based on is_yes/is_buy (e.g., if buy YES: binary['q_yes'] += size).
    2. Confirm cross_match_binary already updates both (lob_matching.py Lines 209-210).
    3. Add validation in apply_orders end: Call validate_solvency_invariant on new_state.
    4. Test in engine/tests/test_lob_matching.py: Simulate market buy vs LOB; assert q updated correctly, no solvency violation.
    5. Trace batch_runner.py: Process MARKET order with LOB fill; check state q in DB post-save.
  - **Priority Rationale**: High – Undercounting q could allow over-trading, breaking no-rejection/asymptotic guarantees and solvency.

3. [ ] **Fill Classification and Dual Prices Missing for Cross-Matches**: Engine fills lack 'fill_type'/price_yes/no, causing misclassification in ticks.py (e.g., all as 'LOB_MATCH' or 'AMM'), inaccurate summaries/events, and potential positions mismatches.
  - **Relevant Context**: TDD Cross-Matching: Fills have price_yes/no for true enforcement. ticks.py_context.md: "Classifies 'CROSS_MATCH' if price_yes/no present". engine_orders.py_context.md: "Fills have single price; no 'price_yes/no' in cross (handled in lob_matching, not returned)". lob_matching.py_context.md: "cross_match_binary returns fills with price_yes/no".
  - **Steps to Audit/Fix**:
    1. In engine_orders.py, when collecting cross_fills from cross_match_binary (Lines 101-150), ensure price_yes/no propagated to Fill dict.
    2. Add 'fill_type' to all fills in apply_orders (e.g., set 'CROSS_MATCH' for cross, 'LOB_MATCH' for market_lob, 'AMM' for AMM).
    3. Update ticks.py normalize_fills to use 'fill_type' if present, fallback to price_yes/no or AMM_USER_ID.
    4. In extract_cross_match_events, use actual params['f_match'] instead of hardcoded 0.02.
    5. Test: Submit cross order; assert fill has price_yes/no and 'CROSS_MATCH'; check summary/events in ticks.py.
    6. Validate in batch_runner.py: After insert_trades, check trades table has expected fields.
  - **Priority Rationale**: High – Breaks event extraction/summaries; could cascade to UI (streamlit_app.py recent trades) and metrics.

4. [ ] **Auto-Fill Events and q Updates Mismatch**: Autofill updates one q but events may be misclassified; positions assumes both, and ticks expects 'CROSS_MATCH'.
  - **Relevant Context**: TDD Auto-Filling: AMM-like, update one q; seigniorage to V. autofill.py_context.md: "Events 'auto_fill_buy/sell'; updates one q". ticks.py_context.md: "Expects 'CROSS_MATCH' for dual prices". positions.py_context.md: "Adds both q".
  - **Steps to Audit/Fix**:
    1. In autofill.py, set 'fill_type'='AUTO_FILL' in AutoFillEvent (extend to Fill-like).
    2. In engine_orders.py, when aggregating auto-fill events post-AMM (Lines 151-300), include as fills with single price, 'AUTO_FILL'.
    3. Update positions.py to handle 'AUTO_FILL' as single q update.
    4. In ticks.py, add 'AUTO_FILL' classification (single price, like AMM).
    5. Test: Trigger cross-impact auto-fill; assert one q updated, event classified correctly, no solvency break.
    6. Check batch_runner.py: Events inserted properly.
  - **Priority Rationale**: High – Similar to q mismatch; affects seigniorage tracking and solvency.

## Medium Severity Items
These affect UX (e.g., over-rejections, inaccurate estimates) or minor inconsistencies (e.g., hardcodes), but not core solvency. Audit after High; focus on services_orders.py and streamlit_app.py.

5. [ ] **Conservative Fee/Slippage Estimates Over-Rejecting Orders**: services_orders.py uses f_match/2 for LIMIT est (may over-reject if unmatched) and AMM*1.1 for MARKET; streamlit_app.py mirrors for UI.
  - **Relevant Context**: TDD: Fees only on fills (f_match on cross, f on AMM); LIMIT no immediate fee. services_orders.py_context.md: "LIMIT est_fee = f_match * size * limit_price /2". streamlit_app.py_context.md: "Est trading_fee = f_match * size * limit_price /2".
  - **Steps to Audit/Fix**:
    1. In services_orders.py submit_order, for LIMIT: Use 0 fee est (or max f_match if assuming match).
    2. For MARKET: Rely on estimate_slippage sim for accurate (incl LOB/auto-fills).
    3. Update streamlit_app.py confirmation: Use estimate_slippage breakdown for fees/effective_price.
    4. Test: Submit LIMIT with balance = size*limit_price + gas; assert accepts if unmatched.
    5. UI: Add note "Fees only if matched" in expander.
  - **Priority Rationale**: Medium – UX frustration (false rejects), but no solvency impact; conservative safe.

6. [ ] **Hardcoded Values Inconsistent with Params**: ticks.py hardcodes f_match=0.02; autofill.py assumes zeta<1/(n-1) but no check.
  - **Relevant Context**: TDD: Params configurable (f_match 0-0.02). ticks.py_context.md: "Hardcoded f_match=0.02 (Line 275)". autofill.py_context.md: "f_j >0 assumed".
  - **Steps to Audit/Fix**:
    1. In ticks.py extract_events, fetch f_match from params (pass state/params to create_tick).
    2. In autofill.py trigger_auto_fills, add check: if zeta >=1/(n_active-1), skip or raise.
    3. Update batch_runner.py: Pass params to create_tick.
    4. Test: Set f_match=0.005; assert events use correct.
    5. Add engine validation in params.py for zeta range.
  - **Priority Rationale**: Medium – Wrong metrics/events if params change; easy fix, no immediate break.

7. [ ] **Incomplete Unfilled Limits Distribution on Resolution**: positions.py has placeholder for pro-rata returns; not integrated.
  - **Relevant Context**: TDD/Implan: Final res distributes unfilled limits pro-rata. positions.py_context.md: "Unfilled distribution incomplete (Line 200 pass)".
  - **Steps to Audit/Fix**:
    1. In positions.py apply_payouts, if is_final: Fetch state lob_pools, for each pool: Compute pro-rata shares, update balances (e.g., buy pool: return USDC volume * share/total_shares).
    2. Call cancel_from_pool implicitly for all, but refund to balances.
    3. Integrate with resolutions.py trigger_resolution: Collect unfilled before zeroing.
    4. Test: Place LIMIT, resolve; assert balance += unfilled amount.
    5. Update timer_service.py to call on final.
  - **Priority Rationale**: Medium – Missing feature affects final balances; but demo-end only.

8. [ ] **af_opt_in Mismatch**: UI has checkbox, but autofill uses volume>0; no explicit check.
  - **Relevant Context**: TDD: Opt-in per limit order. autofill.py_context.md: "Skips if volume<=0, but no af_opt_in check". streamlit_app.py_context.md: "Checkbox for af_opt_in".
  - **Steps to Audit/Fix**:
    1. In lob_matching.py add_to_lob_pool, store af_opt_in in pool dict (e.g., pools[tick]['af_opt_in_users'] = {user: share if af_opt_in}).
    2. In autofill.py auto_fill, filter pools where any af_opt_in_users >0 (or aggregate opt-in volume).
    3. Update engine_orders.py to pass af_opt_in to add_to_lob.
    4. Test: Submit LIMIT with/without opt-in; trigger auto-fill; assert only opt-in filled.
    5. UI: Reflect in order book (e.g., indicator for opt-in pools).
  - **Priority Rationale**: Medium – Feature incomplete; could auto-fill non-opt-in, violating user choice.

## Low Severity Items
These are optimizations, precision issues, or edges; fix last for polish.

9. [ ] **Decimal to Float Precision Loss**: Multiple files convert Decimal to float for DB/JSONB, risking underflow in small values.
  - **Relevant Context**: Implan: Use Decimal for precision. batch_runner.py_context.md: "Converts Decimals to floats (Lines 170-180)". positions.py_context.md: "Converts to float for DB".
  - **Steps to Audit/Fix**:
    1. In utils.py, add str(Decimal) for DB storage (e.g., safe_decimal_to_str).
    2. Update batch_runner.py/positions.py to use str for size/price/fee in inserts.
    3. In queries.py, parse str back to Decimal on fetch.
    4. Test: Small value (1e-10); assert round-trip equality.
    5. Check all DB interactions (e.g., orders.py stores as float → change to str).
  - **Priority Rationale**: Low – Demo-scale unlikely issue; but good for robustness.

10. [ ] **Inaccurate Pool Volume Estimates in Ticks**: ticks.py uses simplified before/after (size*1.1/0.1); no snapshots.
  - **Relevant Context**: Implan: Accurate summaries. ticks.py_context.md: "Simplified estimates (Lines 280-285)".
  - **Steps to Audit/Fix**:
    1. In batch_runner.py run_tick, snapshot lob_pools pre-apply_orders.
    2. Pass pre/post to create_tick for exact before/after in events.
    3. Update extract_events to use snapshots.
    4. Test: Cross-match; assert events match actual pool changes.
    5. UI: Recent trades in streamlit_app.py uses trades table (accurate).
  - **Priority Rationale**: Low – Metrics only; no functional impact.

11. [ ] **Gas Deducted on Validation Errors**: services_orders.py deducts gas before full validation, potentially frustrating users.
  - **Relevant Context**: Implan: Deduct always. services_orders.py_context.md: "Gas deducted before insertion (Line 122), even if later raise".
  - **Steps to Audit/Fix**:
    1. Move deduct_gas after all validations but before DB insert.
    2. If raise post-deduct, refund (update_balance +gas_fee).
    3. Log reason for reject (events table).
    4. Test: Invalid size; assert no deduct, status=REJECTED not set.
    5. UI: Warn in confirmation "Gas deducted on submit".
  - **Priority Rationale**: Low – UX nit; aligns with "always deduct" but avoids edge frustration.

12. [ ] **Tick Calc Assumes tick_size=0.01**: ticks.py uses int(price*100); but configurable.
  - **Relevant Context**: TDD: tick_size configurable. ticks.py_context.md: "Assumes tick_size=0.01 (Lines 260-265)".
  - **Steps to Audit/Fix**:
    1. Pass params['tick_size'] to create_tick/extract_events.
    2. Compute tick = int(price / tick_size).
    3. Update lob_matching.py get_pool_key to use params.tick_size if None.
    4. Test: Set tick_size=0.005; assert correct tick.
    5. Check engine_orders.py fallback tick_size=0.01.
  - **Priority Rationale**: Low – Default works; easy if changed.