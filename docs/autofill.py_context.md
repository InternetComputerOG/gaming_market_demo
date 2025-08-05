# autofill.py_context.md

## Overview
Engine module for auto-filling limit orders against the AMM on cross-impacts in the Gaming Market Demo, implementing opportunistic fills with seigniorage capture, binary searches for max profitable delta, pool/share updates, rebates, and validations per TDD derivations (Auto-Filling section). Handles triggers post-order execution and per-binary fills with caps/surpluses; called by engine_orders.py for events post-AMM (Lines 1-30: Imports/TypedDicts; 31-80: trigger_auto_fills; 81-150: binary_search_max_delta; 151-200: update_pool_and_get_deltas; 201-220: apply_rebates; 221-end: auto_fill).

## Key Exports/Interfaces
- **AutoFillEvent** (TypedDict, Line 22): {'type': str ('auto_fill_buy'/'auto_fill_sell'), 'binary_id': int, 'is_yes': bool, 'tick': int, 'delta': Decimal, 'surplus': Decimal, 'user_position_deltas': Dict[str, Decimal], 'user_balance_deltas': Dict[str, Decimal]}; event format for fills.
- **trigger_auto_fills(state: EngineState, i: int, X: Decimal, is_buy: bool, params: EngineParams, current_time: int) -> List[AutoFillEvent]** (Lines 25-80): Triggers fills on cross-impacts if af_enabled; computes simplified diversions (X * zeta / (n_active-1), negated if !is_buy) per other active binary, calls auto_fill; returns aggregated events.
- **binary_search_max_delta(pool_tick: Decimal, is_buy: bool, is_yes: bool, binary: BinaryState, params: EngineParams, f_i: Decimal, max_high: Decimal) -> Decimal** (Lines 82-150): Binary search (20 iterations) for max delta where post-trade p <=/>= pool_tick (buy/sell) and surplus >=0; uses amm_math costs/received; handles edges (max_high<=0 ->0); returns best_delta.
- **update_pool_and_get_deltas(pool: Dict[str, Any], delta: Decimal, charge: Decimal, is_buy: bool) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]** (Lines 152-200): Updates pool shares/volume pro-rata (buy: reduce USDC shares/volume by charge; sell: reduce token shares/volume by delta); computes position/balance deltas (+/- tokens/USDC); cleans zero shares; returns deltas.
- **apply_rebates(surplus: Decimal, sigma: Decimal, original_volume: Decimal, shares: Dict[str, Decimal], balance_deltas: Dict[str, Decimal]) -> None** (Lines 202-220): Adds pro-rata rebates ((1-sigma)*surplus) to balance_deltas if >0; modifies in-place.
- **auto_fill(state: EngineState, j: int, diversion: Decimal, params: EngineParams) -> Tuple[Decimal, List[AutoFillEvent]]** (Lines 222-end): Applies diversion to V_j, updates subsidies; for increase/decrease (buy/sell direction), iterates YES/NO pools (highest/lowest ticks first), binary searches delta (with max_high from pool_volume or search), computes X/charge/surplus, caps delta/surplus, updates pool/binary (q +/-/V + system_surplus), validates/rolls back, applies rebates, creates events; caps total_surplus; returns total_surplus, events.

## Dependencies/Imports
- Imports: decimal.Decimal, typing (Dict/Any/List/Tuple) (Lines 1-4).
- From .: amm_math (buy_cost_yes/no, get_effective_p_yes/no, get_new_p_yes/no_after_buy/sell, sell_received_yes/no), state (BinaryState/EngineState/get_p_yes/no/update_subsidies), params (EngineParams), impact_functions (get_new_prices_after_impact) (Lines 6-13).
- From app.utils: safe_divide/validate_size/price_value/usdc_amount/validate_binary_state/validate_solvency_invariant (Lines 5-6).
- Interactions: Called by engine_orders.py (trigger_auto_fills post-AMM); uses amm_math for costs/prices; updates state binaries in-place (V/q/subsidies/lob_pools); events processed by batch_runner.py for DB/positions; ties to lob_matching.py for pool semantics (USDC/token volumes).

## Usage Notes
- Implements TDD Auto-Filling/Seigniorage (§Derivations) with binary search for max delta (profitable + price_ok), pro-rata updates/rebates, validation rollbacks; use Decimal for precision (no numpy, pure Python—potential stability issues in searches/quadratics); f_j =1-(len(active)-1)*zeta_start (Line 235); direction='buy' if diversion>0 (increase V, drop prices—fill buy pools); pools sorted reverse for buys (high tick first); caps: delta<=af_cap_frac*abs(diversion)/pool_tick, pools<=af_max_pools, surplus<=af_max_surplus*abs(diversion)/zeta_start; events for positions.py updates (both q_yes/no? but code updates one token_field); debug prints throughout for tracing.

## Edge Cases/Invariants
- Edges: diversion=0/af_disabled/inactive -> (0,[]); delta<=0/surplus<=0 -> skip; max_high<=0 ->0; pools_filled>=af_max_pools -> break; validation fail -> rollback V/q/pool (raises ValueError); original_volume<=0 -> empty deltas; high/low=mid /2 handles zero mid.
- Invariants: Surplus >=0 enforced (profit_ok); p_mid <=/>= pool_tick (price_ok for buy/sell); q < L_i preserved via validations post-mutations; deterministic sorts (reverse for increase); shares/volume >=0 (cleans <=0); total_surplus capped; f_j >0 assumed (zeta<1/(n-1)).

## Inconsistencies/Possible Issues
- No numpy import despite Implan §3 recommendation for binary searches/quadratics stability (pure Decimal loops—potential precision loss in /2 iterations, e.g., Line 95); may cause underflow in mid=(low+high)/2 with small Decimals.
- In trigger_auto_fills, simplified diversion=X*zeta/(n-1) per j (total (n-1)*zeta*X diverted, matches TDD), but negated if !is_buy (sells decrease V, but TDD sells divert -zeta*X); assumes X>0 always—check engine_orders.py if X<0 possible.
- auto_fill updates one q (yes/no, Lines 373-377), but positions.py_context.md update_position_from_fill adds to both q_yes/q_no (Lines 115-118)—mismatch for autofill events (assumes cross-like, but autofill is AMM buy/sell; solvency break if positions assumes both).
- Events 'AUTO_FILL' but ticks.py_context.md/extract_events expects 'CROSS_MATCH' (price_yes/no); may misclassify in summaries if no dual prices—integration gap with engine_orders.py fills.
- In binary_search_max_delta for sells, surplus=X_mid-charge (receive-pay>0), but debug prints/test_deltas only for buys (Lines 290-295)—asymmetric testing; potential uncaught negative surplus.
- Cap total_surplus at af_max_surplus*abs(diversion)/zeta_start (Line 445), but per-pool surplus not recalculated post-cap—may over-cap if multi-pools.
- Diversion added to V as float(Decimal+diversion), but state V float (JSONB)—precision loss; consistent with engine.state but ties to positions.py_context.md note on float loss.
- batch_runner.py_context.md calls apply_orders (with trigger_auto_fills), but no explicit event insertion for autofills—assume in engine_orders events list; check if positions updated correctly from events (ties to positions.py adding both q).
- streamlit_app.py_context.md af_opt_in checkbox, but autofill uses pool['volume']>0 (opt-in via key? code skips if volume<=0, but no af_opt_in check—mismatch if services_orders.py sets but ignored).