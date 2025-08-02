# 3_context.md

# state.py_context.md

## Overview
Manages the deterministic EngineState for the AMM, encapsulating per-binary variables (V, L, q_yes/no, virtual_yes, etc.) and global pre_sum_yes for multi-resolution renormalization. Provides initialization, serialization/deserialization for DB JSONB, and helper functions for access/updates per TDD state management and implementation plan's engine package.

## Key Exports/Interfaces
- `class BinaryState(TypedDict)`: Per-outcome dict with keys: outcome_i (int), V (float), subsidy (float), L (float), q_yes (float), q_no (float), virtual_yes (float), seigniorage (float), active (bool), lob_pools (Dict[str, Dict[str, Dict[int, Dict[str, Any]]]]: 'YES'/'NO' -> 'buy'/'sell' -> tick: {'volume': float, 'shares': Dict[str, float]}).
- `class EngineState(TypedDict)`: Top-level dict with keys: binaries (List[BinaryState]), pre_sum_yes (float).
- `init_state(params: Dict[str, Any]) -> EngineState`: Initializes state from params (n_outcomes, z, gamma, q0); sets initial subsidy_i = z/n_outcomes, L_i = subsidy_i, q_yes/no = q0, virtual_yes=0, active=True, empty lob_pools; pre_sum_yes = n_outcomes * (q0 / subsidy_i).
- `serialize_state(state: EngineState) -> Dict[str, Any]`: Converts state to JSON-compatible dict, stringifying int tick keys in lob_pools.
- `deserialize_state(json_dict: Dict[str, Any]) -> EngineState`: Restores state from JSON dict, int-ifying str tick keys in lob_pools.
- `get_binary(state: EngineState, outcome_i: int) -> BinaryState`: Retrieves BinaryState for given outcome_i; raises ValueError if not found.
- `get_p_yes(binary: BinaryState) -> float`: Computes p_yes = (q_yes + virtual_yes) / L.
- `get_p_no(binary: BinaryState) -> float`: Computes p_no = q_no / L.
- `update_subsidies(state: EngineState, params: Dict[str, Any]) -> None`: Recomputes subsidy_i = max(0, z/n_outcomes - gamma * V_i) and L_i for all binaries.

## Dependencies/Imports
- Imports: typing_extensions (TypedDict), typing (List, Dict, Any).
- Interactions: Params from engine/params.py; state used/updated in engine/orders.py (e.g., V_i += f_i * X), engine/resolutions.py (virtual_yes adjustments); serialized to DB via db/queries.py; no numpy here but assumes float precision for tests.

## Usage Notes
- State JSONB-compatible for Supabase storage; use serialize/deserialize for DB I/O. Tie to TDD invariants (q_yes_eff < L_i); update subsidies after any V changes. Deterministic: No random; init sets p_yes/no=0.5. For tests: Validate init matches TDD defaults, serialization round-trips, p computations align with derivations.

## Edge Cases/Invariants
- Invariants: subsidy >=0, L = V + subsidy >0, q_yes/no >= q0 initially, virtual_yes >=0 (capped in resolutions), active binaries only for computations (N_active from count(active)). Edges: Zero subsidy (trades continue); negative virtual_yes capped (vc_enabled); empty lob_pools; raises on invalid outcome_i. Assumes params valid per TDD ranges; solvency q_yes + q_no < 2*L (enforced in orders). Deterministic with float ops.

# engine_resolutions.py_context.md

## Overview
Module for handling multi-resolution eliminations and final payouts in the engine, including NO payouts on eliminated outcomes, liquidity redistribution, and YES price renormalization via virtual_yes adjustments per TDD multi-resolution mechanics and implementation plan's trigger_resolution API.

## Key Exports/Interfaces
- `trigger_resolution(state: EngineState, params: EngineParams, is_final: bool, elim_outcomes: Union[List[int], int]) -> tuple[Dict[str, Decimal], EngineState, List[Dict[str, Any]]]`: Processes intermediate (list elims) or final (int winner) resolution; computes payouts from positions, subtracts from V_i, redistributes freed (L_i - total_q_no), renormalizes virtual_yes for remaining (target_p = (old_p / post_sum) * pre_sum_yes, cap >=0 if vc_enabled); mutates state (active=False, V/L/active/virtual_yes); returns user payouts, updated state, events list (e.g., {'type': 'ELIMINATION', ...}).

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any, Union; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies, get_p_yes.
- From .params: EngineParams.
- From app.utils: safe_divide, usdc_amount.
- From app.db.queries: fetch_positions.
- Interactions: Mutates state in-place (V/L/active/virtual_yes); fetches positions from DB for actual q_yes/no sums (excludes virtual); called by runner/timer_service.py for automatic resolutions; events for realtime.py pushes.

## Usage Notes
- Use Decimal for all calcs/quantization; state mutations ensure JSON-serializable floats; supports mr_enabled toggle (single-res as final auto-elim); pre_sum_yes from active p_yes sum; redistribute freed / remaining_active; integrates with orders.py invariants (no trades during pause implied).
- For tests: Cover solvency checks (raise if q_no > L), virtual cap, final q_yes payout, zero positions, determinism via sorted elims.

## Edge Cases/Invariants
- Invariants: Actual q_no/yes < L_i preserved (raise on violation); virtual_yes >=0 if vc_enabled; total risk <=Z unchanged; deterministic (sort elims, sum active only).
- Edges: No elims raise; zero freed skips; negative virtual capped (sum may < pre_sum); single-res (mr_enabled=False) only final; inactive elim skipped.

# amm_math.py_context.md

## Overview
Module implementing core AMM mathematical functions for buy/sell costs and price computations in the Gaming Market engine, per TDD derivations for asymmetric weighted averages, quadratic solves, and asymptotic penalties. Focuses on pure calculations without state updates or LOB/auto-fills.

## Key Exports/Interfaces
- `get_effective_p_yes(binary: BinaryState) -> Decimal`: Returns effective p_yes = (q_yes + virtual_yes) / L.
- `get_effective_p_no(binary: BinaryState) -> Decimal`: Returns p_no = q_no / L.
- `get_new_p_yes_after_buy(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal`: Computes post-buy p_yes without state change.
- `get_new_p_yes_after_sell(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal`: Computes post-sell p_yes.
- `get_new_p_no_after_buy(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal`: Computes post-buy p_no.
- `get_new_p_no_after_sell(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal`: Computes post-sell p_no.
- `buy_cost_yes(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal`: Solves quadratic for buy YES cost X, applies penalty if p' > p_max; quantizes output.
- `sell_received_yes(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal`: Solves for sell YES received X, applies penalty if p' < p_min.
- `buy_cost_no(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal`: Symmetric to buy_cost_yes for NO (no virtual).
- `sell_received_no(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal`: Symmetric to sell_received_yes for NO.

## Dependencies/Imports
- From decimal: Decimal; typing: Dict, Any; mpmath: mp (for sqrt if needed, but uses utils).
- From app.utils: decimal_sqrt, solve_quadratic, safe_divide, validate_size, validate_price, price_value.
- From .state: BinaryState.
- From .params: EngineParams.
- Interactions: Called by orders.py for cost/pricing in apply_orders; uses utils for solves/validations; params provide mu/nu/kappa/p_max/p_min/eta.

## Usage Notes
- Pure functions: No state mutation; f_i passed from caller (1 - (N_active-1)*zeta).
- Use Decimal for precision; quantize costs/prices via price_value.
- Implements TDD quadratics/substitutions for coeffs; penalties ensure solvency (p' bounded).
- Deterministic: Relies on utils.solve_quadratic for positive root.

## Edge Cases/Invariants
- Delta=0 returns 0; negative delta raises via validate_size.
- Assumes discriminant >=0 per TDD proofs (raises if negative).
- Invariants: Post-penalty p' <= p_max / >= p_min, ensuring q_eff < L; handles zero subsidy/L>0.
- Edges: Asymptotic (large delta: X->inf/0); small delta approximates linear.

# engine_orders.py_context.md

## Overview
Module orchestrating batch order processing in the engine, implementing apply_orders as the main entry for deterministic handling of market/limit orders, integrating LOB/cross-matching, AMM trades, impacts, auto-fills, and state updates per TDD derivations and impl plan §4 (engine API).

## Key Exports/Interfaces
- `class Order(TypedDict)`: {'order_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'type': str, 'is_buy': bool, 'size': Decimal, 'limit_price': Decimal | None, 'max_slippage': Decimal | None, 'af_opt_in': bool, 'ts_ms': int}.
- `class Fill(TypedDict)`: {'trade_id': str, 'buy_user_id': str, 'sell_user_id': str, 'outcome_i': int, 'yes_no': str, 'price': Decimal, 'size': Decimal, 'fee': Decimal, 'tick_id': int, 'ts_ms': int}.
- `apply_orders(state: EngineState, orders: List[Order], params: EngineParams, current_time: int) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]`: Processes sorted orders; adds limits to pools, performs cross-matches if enabled, matches/matches AMM for markets with slippage checks/rejects; applies impacts/auto-fills; returns fills, updated state, events (e.g., ORDER_ACCEPTED/REJECTED/FILLED).

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any, Tuple; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies, get_p_yes, get_p_no.
- From .params: EngineParams.
- From .amm_math: buy_cost_yes, sell_received_yes, buy_cost_no, sell_received_no, get_effective_p_yes, get_effective_p_no.
- From .impact_functions: compute_dynamic_params, compute_f_i, apply_own_impact, apply_cross_impacts, apply_asymptotic_penalty.
- From .lob_matching: add_to_lob_pool, cross_match_binary, match_market_order.
- From .autofill: trigger_auto_fills.
- From app.utils: usdc_amount, price_value, validate_price, validate_size, safe_divide.
- Interactions: Mutates state in-place (V, q, subsidies, lob_pools); called by runner/batch_runner.py in tick loops; uses amm_math for quadratics, impact_functions for diversions/penalties, lob_matching for LOB/cross, autofill on triggers; events for services/realtime.py.

## Usage Notes
- Deterministic: Sort orders by ts_ms, binaries by outcome_i; use Decimal for precision, price_value/usdc_amount for quantization.
- Handles partial fills, rejects on slippage > max_slippage (post-simulation); fees via params['fee_rate']; gas deductions implied (DB side).
- Dynamic params via compute_dynamic_params; N_active from active binaries; symmetric YES/NO handling.
- Implements TDD quadratics/penalties/diversions/cross-matching/auto-fills; invariants enforced via validations/penalties.
- JSON-compatible: Events as dicts; state mutations for DB save via queries.py.

## Edge Cases/Invariants
- Edges: Zero size skips (validate_size raises); inactive binary rejects; empty orders returns empty; oversized AMM via penalties (no rejection except slippage); zero subsidy continues; zeta clamped for f_i >0.
- Invariants: q_yes_eff + q_no < 2*L_i preserved (penalties); total risk <=Z; deterministic fills/events; post-update subsidies recomputed; slippage = (effective_p - current_p)/current_p for buys (symmetric sells).

# autofill.py_context.md

## Overview
Module implementing auto-filling logic on cross-impacts for opt-in limit orders, capturing seigniorage with σ allocation, binary search for max Δ respecting tick prices, and caps per TDD; updates state in-place for V_i (system surplus), q_yes/no (mint/burn), lob_pools (fills pro-rata via shares).

## Key Exports/Interfaces
- `binary_search_max_delta(pool_tick: Decimal, is_buy: bool, is_yes: bool, binary: BinaryState, params: EngineParams, f_i: Decimal, max_high: Decimal) -> Decimal`: Binary search (20 iter) for max Δ s.t. p' <=/>= tick on buy/sell; uses amm_math buy_cost/sell_received.
- `update_pool_and_get_deltas(pool: Dict[str, any], delta: Decimal, charge: Decimal, is_buy: bool) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]`: Pro-rata fill pool shares, compute user position/balance deltas; reduces volume/shares.
- `apply_rebates(surplus: Decimal, sigma: Decimal, original_volume: Decimal, shares: Dict[str, Decimal], balance_deltas: Dict[str, Decimal]) -> None`: Distribute (1-σ) surplus pro-rata as balance deltas.
- `auto_fill(state: EngineState, j: int, diversion: Decimal, params: EngineParams) -> Tuple[Decimal, List[AutoFillEvent]]`: Main func; for diversion >0 (price drop: auto-buy YES/NO pools tick > p) or <0 (rise: auto-sell < p); sorts ticks desc/asc, applies binary search/caps (af_cap_frac * |diversion|, af_max_pools, af_max_surplus * |diversion|/zeta), updates binary V/q/pools, returns total_surplus for trigger penalty reduction and events for logging.

## Dependencies/Imports
- From decimal: Decimal; typing: Dict, List, Tuple.
- From app.utils: safe_divide, validate_size, price_value, usdc_amount.
- From .amm_math: buy_cost_yes/no, sell_received_yes/no, get_effective_p_yes/no, get_new_p_yes/no_after_buy/sell.
- From .state: BinaryState, EngineState, get_p_yes/no, update_subsidies.
- From .params: EngineParams.
- Interactions: Called by orders.py post-diversion in apply_orders; uses amm_math for X/p', state for in-place V/q/lob_pools updates (lob_pools as dict['YES'/'NO']['buy'/'sell'][int tick: {'volume': Decimal, 'shares': Dict[str, Decimal]}]), params for af_enabled/sigma/caps/zeta/tick_size.

## Usage Notes
- Pure functions except in-place state mutations for efficiency; AutoFillEvent TypedDict for events (type, binary_id, is_yes, tick, delta, surplus, user_deltas); use Decimal for precision, validate_size(delta>0); integrate with orders.py for repricing trigger (reduce η by total_surplus / X_trigger); handles YES/NO separately, batch post-updates; for mr_enabled, respects binary['active'] in f_j via N_active count.

## Edge Cases/Invariants
- Zero diversion/volume/surplus: Skip, return 0/[]; empty pools: Continue; surplus <=0: Skip fill; caps truncate delta/surplus; deterministic: Sort ticks by int key desc/asc, pro-rata FIFO-irrelevant (shares dict keys arbitrary but consistent); invariants: q_eff < L preserved via amm_math penalties, V += sigma*surplus >=0, volume/shares >=0, no cascades via af_max_pools/surplus caps; edges: Negative diversion (sells trigger auto-sell), inactive binary skip, small delta quantize with price_value/usdc_amount.

# impact_functions.py_context.md

## Overview
Module handling cross-impacts, diversions, own impacts, and asymmetry logic for the AMM, including dynamic parameter interpolation per TDD addendum and implementation plan. Focuses on state updates for trade impacts without AMM solves, integrating with amm_math for effective prices.

## Key Exports/Interfaces
- `compute_dynamic_params(params: EngineParams, current_time: int, round_num: Optional[int] = None) -> Dict[str, Decimal]`: Interpolates mu, nu, kappa, zeta linearly from start/end values based on time; resets per round if mr_enabled and 'reset' mode.
- `compute_f_i(params: EngineParams, zeta: Decimal, state: EngineState) -> Decimal`: Computes f_i = 1 - (N_active - 1) * zeta, with N_active from active binaries.
- `apply_own_impact(state: EngineState, i: int, X: Decimal, is_buy: bool, is_yes: bool, f_i: Decimal, params: EngineParams) -> None`: Updates V_i with sign * f_i * X, recomputes subsidy/L_i.
- `apply_cross_impacts(state: EngineState, i: int, X: Decimal, is_buy: bool, zeta: Decimal, params: EngineParams) -> None`: Diverts sign * zeta * X to each other active V_j, sorted by outcome_i for determinism; updates subsidies.
- `get_new_prices_after_impact(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal, is_buy: bool, is_yes: bool) -> tuple[Decimal, Decimal]`: Computes post-impact p_yes and p_no using effective supplies.
- `apply_asymptotic_penalty(X: Decimal, p_prime: Decimal, p_base: Decimal, is_buy: bool, params: EngineParams) -> Decimal`: Adjusts X with (p'/p_max)^eta on buy overflow or (p_min/p')^eta on sell underflow.

## Dependencies/Imports
- From decimal: Decimal; typing: Dict; typing_extensions: TypedDict; numpy: np (for potential numerics, though not used here).
- From app.utils: safe_divide, solve_quadratic, price_value.
- From .state: EngineState, BinaryState, get_binary, get_p_yes, get_p_no, update_subsidies.
- From .amm_math: get_effective_p_yes, get_effective_p_no.
- From .params: EngineParams.
- Interactions: Called by orders.py for impact applications in apply_orders; uses state for mutations, amm_math for prices; params for interpolation/toggles.

## Usage Notes
- Use Decimal for precision; state mutations in-place for efficiency; integrate with amm_math quadratics in orders.py flows. Dynamic params via linear t = current_time / total_duration, clamped [0,1]; zeta capped <=1/(N_active-1). Assumes X net of fees; caller handles fee collection. JSON-compatible via float casts in state.

## Edge Cases/Invariants
- Zeta clamped for f_i >0; N_active from active flags only (multi-res handling). Zero subsidy: trades continue. Negative discriminant/ValueError from solves propagated. Deterministic: Sort binaries by outcome_i; invariants: q_yes_eff + q_no < 2*L_i preserved via penalties; virtual_yes >=0 if vc_enabled. Edges: t=0/end, no active binaries raise implicitly.

# lob_matching.py_context.md

## Overview
Module for limit order book (LOB) operations in the engine, including pool management at tick granularity, pro-rata matching, cross-matching YES/NO limits if cm_enabled, and market order fills vs LOB per TDD cross-matching mechanics and impl plan batch execution.

## Key Exports/Interfaces
- `get_pool_key(tick: int, af_opt_in: bool) -> int`: Encodes tick with sign for opt-in (positive if opt-in).
- `get_tick_from_key(key: int) -> int`: Extracts absolute tick from key.
- `is_opt_in_from_key(key: int) -> bool`: Checks if key positive for opt-in.
- `add_to_lob_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, amount: Decimal, af_opt_in: bool) -> None`: Adds amount to pool, updates volume/shares.
- `cancel_from_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, af_opt_in: bool) -> Decimal`: Removes user share, returns amount; cleans empty pools.
- `cross_match_binary(state: EngineState, i: int, params: EngineParams, current_ts: int, tick_id: int) -> List[Dict[str, Any]]`: Performs cross-matching YES buys with NO sells if cm_enabled, sorted descending ticks; updates V, q_yes, subsidies; pro-rata fills; returns aggregated fills.
- `match_market_order(state: EngineState, i: int, is_buy: bool, is_yes: bool, size: Decimal, params: EngineParams, current_ts: int, tick_id: int) -> tuple[List[Dict[str, Any]], Decimal]`: Matches market order vs opposing pools (sorted by price), pro-rata fills with fees; returns fills and remaining size.

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies.
- From .params: EngineParams.
- From app.utils: usdc_amount, price_value, validate_price, validate_size, safe_divide.
- From .amm_math: get_effective_p_yes, get_effective_p_no.
- Interactions: Mutates state.lob_pools in-place; called by orders.py for matching in apply_orders; integrates with impact_functions.py for post-match updates; state serialized to DB via queries.py.

## Usage Notes
- Pools stored in state.lob_pools as nested dicts: yes_no -> buy/sell -> key(int): {'volume': Decimal, 'shares': {user_id: Decimal}}; keys encode af_opt_in.
- Deterministic: Sort ticks descending (buys/cross) or ascending (sells); pro-rata via shares ratios.
- Implements TDD solvency: In cross-match, caps fill to ensure V += (price_yes - price_no)*fill >= fill; fees via f_match.
- Use Decimal for precision; validate_size/price on inputs; handle partial fills.

## Edge Cases/Invariants
- Assumes active binaries only (ignore inactive); empty/zero volume pools deleted; partial fills ok; no matches if prices <1 or yes <= no.
- Invariants: Volume >=0; shares sum = volume; q_yes + q_no <2*L preserved (cross-match adds balanced); deterministic with hash(ts) for IDs.
- Edges: Oversized fill capped; negative keys for non-opt-in; zero fill skips; assumes tick_size >0, cm_enabled toggles.

# params.py_context.md

## Overview
Defines AMM parameters as TypedDict for engine configuration, with defaults, validation, and quadratic solver helper. Implements tunable params per TDD (e.g., alpha/beta for liquidity/imbalance) and plan's dynamic interpolation needs.

## Key Exports/Interfaces
- `class Params(TypedDict)`: Dict with keys: alpha (float), beta (float), trade_fee (float), liquidity_initial (float), min_liquidity (float), max_imbalance_ratio (float), min_auto_fill (float), resolution_prob (float); for AMM config per TDD Section Symbols.
- `get_default_params() -> Params`: Returns default dict (e.g., alpha=1.0, trade_fee=0.01).
- `validate_params(params: Params) -> None`: Raises ValueError on invalid values (e.g., alpha <=0, trade_fee not in [0,1)).
- `solve_quadratic(a: float, b: float, c: float) -> float`: Returns min positive root using np.roots; for AMM pricing per TDD Derivations (selects smallest for min delta, raises if no positive).

## Dependencies/Imports
- Imports: typing (TypedDict), numpy (np.roots for quadratic stability).
- Interactions: Provides Params to engine/state.py for initialization; called in engine/orders.py for solves; JSON-serializable for DB config table; overlaps with config.py defaults.

## Usage Notes
- Use for engine init/validation; numpy ensures numerical stability in quadratics. Tie to TDD ranges (e.g., trade_fee (0,0.05)); extend for dynamic interp (start/end values) per addendum. Handle in tests: defaults match TDD, validation covers mins/maxes, solve returns positive min root.

## Edge Cases/Invariants
- Invariants: All params positive/non-neg per validation; quadratic discriminant >=0 assumed (from TDD proofs), positive root exists. Edges: Zero alpha raises error; no roots raises ValueError; ensures q < L_i via params in solves. Deterministic: No random; defaults for demo solvency.