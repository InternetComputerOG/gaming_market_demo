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
- From .params: EngineParams.
- From .amm_math: get_effective_p_yes, get_effective_p_no.
- Interactions: Called by orders.py for impact applications in apply_orders; uses state for mutations, amm_math for prices; params for interpolation/toggles.

## Usage Notes
- Use Decimal for precision; state mutations in-place for efficiency; integrate with amm_math quadratics in orders.py flows. Dynamic params via linear t = current_time / total_duration, clamped [0,1]; zeta capped <=1/(N_active-1). Assumes X net of fees; caller handles fee collection. JSON-compatible via float casts in state.

## Edge Cases/Invariants
- Zeta clamped for f_i >0; N_active from active flags only (multi-res handling). Zero subsidy: trades continue. Negative discriminant/ValueError from solves propagated. Deterministic: Sort binaries by outcome_i; invariants: q_yes_eff + q_no < 2*L_i preserved via penalties; virtual_yes >=0 if vc_enabled. Edges: t=0/end, no active binaries raise implicitly.