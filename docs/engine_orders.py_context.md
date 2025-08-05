# engine_orders.py_context.md

## Overview
Core engine module for order processing in the Gaming Market Demo, implementing apply_orders to handle batched LIMIT (add to LOB pools) and MARKET orders (match LOB/cross then AMM, with slippage/impacts/auto-fills per TDD derivations), returning fills/state/events while enforcing validations/solvency. Implements Implan §3/§4 engine API with Decimal precision for math, float for state; called by batch_runner.py for ticks (Lines 1-20: Imports/TypedDicts; 21-50: apply_orders start/validate/sort/dyn_params; 51-100: Process LIMIT/add_to_lob; 101-150: Cross-match if enabled; 151-300: Process MARKET/match_lob/AMM/slippage/impacts/auto-fills/validate end).

## Key Exports/Interfaces
- **AMM_USER_ID** (str, Line 21): Constant '00000000-0000-0000-0000-000000000000' for AMM fills in DB.
- **Order** (TypedDict, Lines 23-33): {'order_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'type': str, 'is_buy': bool, 'size': Decimal, 'limit_price': Optional[Decimal], 'max_slippage': Optional[Decimal], 'af_opt_in': bool, 'ts_ms': int}.
- **Fill** (TypedDict, Lines 35-45): {'trade_id': str, 'buy_user_id': str, 'sell_user_id': str, 'outcome_i': int, 'yes_no': str, 'price': Decimal, 'size': Decimal, 'fee': Decimal, 'tick_id': int, 'ts_ms': int}.
- **apply_orders(state: EngineState, orders: List[Order], params: EngineParams, current_time: int) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]** (Lines 47-end): Processes sorted orders: LIMIT to LOB, cross-match binaries, MARKET vs LOB then AMM (with slippage/impacts/subsidies/auto-fills); validates states/solvency; returns fills (AMM/LOB/cross), updated state, events (e.g., ORDER_ACCEPTED/REJECTED/FILLED).

## Dependencies/Imports
- Imports: decimal.Decimal, typing (List/Dict/Any/Tuple), typing_extensions.TypedDict, uuid (Lines 1-5).
- From .: state (EngineState/BinaryState/get_binary/update_subsidies/get_p_yes/no), params (EngineParams), amm_math (buy_cost_yes/sell_received_yes/buy_cost_no/sell_received_no/get_effective_p_yes/no), impact_functions (compute_dynamic_params/compute_f_i/apply_own_impact/apply_cross_impacts/apply_asymptotic_penalty/get_new_prices_after_impact), lob_matching (add_to_lob_pool/cross_match_binary/match_market_order), autofill (trigger_auto_fills) (Lines 7-15).
- From app.utils: usdc_amount/price_value/validate_price/validate_size/safe_divide/validate_engine_state/validate_binary_state/validate_solvency_invariant (Lines 16-17).
- Interactions: Updates state in-place (e.g., q_yes/no, lob_pools); computes dyn_params/impacts per TDD; called by batch_runner.py with DB-fetched orders/state; fills used by positions.py/ticks.py for updates/summaries; services_orders.py simulates via apply_orders on copy.

## Usage Notes
- Uses Decimal for size/price/fee (precision), but state q_yes/no as float (JSONB compat); convert via usdc_amount/price_value.
- Deterministic: Sorts orders by ts_ms; processes LIMIT first (add_to_lob with tick=limit_price/tick_size), then cross-match (if cm_enabled, per binary), then MARKET (match_lob first, AMM remaining with f_i/impacts/subsidies, auto-fills if af_enabled).
- Validations: Engine/binary/solvency at start/end/after updates (raise ValueError); size/price bounds per TDD [p_min,p_max]; slippage check rejects MARKET if > max_slippage.
- Fees: AMM f * size * effective_p (separate from price); LOB/cross f_match * (T+S)/2 (handled in lob_matching).
- AMM fills use AMM_USER_ID; generates uuid trade_id; tick_id=0 placeholder.
- Impacts: Own/cross/penalty after AMM; subsidies post-impacts; auto-fills post-updates (trigger_auto_fills).
- Tie to TDD: Implements AMM quadratics/asymmetry/penalties/cross-impacts/diversions/seigniorage abstraction (via auto-fills); N_active from active binaries; dyn_params for ζ/μ/ν/κ interpolation.

## Edge Cases/Invariants
- Edges: Empty orders → [] fills, unchanged state; inactive binary rejects; zero size rejects; slippage exceed rejects MARKET (event); solvency violation rollbacks AMM update/pops fill.
- Invariants: q_yes/no < L_i preserved via penalties/validates (raise on violation); deterministic FIFO via ts_ms sort; total V increases on buys/decreases on sells; N_active decreases on multi-res (but not handled here, assume state.active set by resolutions.py); events for all rejects/accepted/filled.

## Inconsistencies/Possible Issues
- AMM updates only one q (yes or no) per fill (Lines 237-251), but positions.py_context.md update_position_from_fill adds to both q_yes/q_no (Lines 115-118) assuming cross-matches; mismatch for AMM/LOB fills (TDD: cross adds both, AMM/LOB one—potential q over-inflation/solvency break if positions assumes both).
- Fills lack 'source'/'fill_type' (e.g., 'AMM'/'LOB'/'CROSS'), but ticks.py_context.md normalize_fills classifies via AMM_USER_ID/price_yes (absent here—fills have single price); may misclassify in summaries.
- No 'price_yes'/'price_no' in cross fills (handled in cross_match_binary, not returned here); ticks.py_context.md assumes for 'CROSS_MATCH'—integration gap if cross_fills lack dual prices.
- MARKET slippage computed post-impact (Lines 199-204), but services_orders.py_context.md estimates via sim apply_orders (accounts LOB/AMM/auto-fills); consistent but conservative buffer in submit may over-reject.
- batch_runner.py_context.md derives is_buy in transform (Lines 90-140), but orders.py assumes provided; potential mismatch if derivation errors.
- streamlit_app.py_context.md submits with derived is_buy (yes_no/type), but no explicit slippage est in UI for LIMIT (uses f_match est, but orders.py LIMIT no immediate fee—over-est in confirmation).