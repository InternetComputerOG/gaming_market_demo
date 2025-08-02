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