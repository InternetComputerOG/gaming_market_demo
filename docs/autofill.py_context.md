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