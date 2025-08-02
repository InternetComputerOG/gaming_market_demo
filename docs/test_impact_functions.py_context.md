# test_impact_functions.py_context.md

## Overview
Unit tests for impact_functions.py using pytest, covering dynamic param interpolation, f_i computation, own/cross impact applications, new price calculations, and asymptotic penalties. Ensures TDD invariants like positive f_i, price bounds, and state mutations per derivations; uses Decimal for precision.

## Key Exports/Interfaces
- `@pytest.fixture def default_params() -> EngineParams`: Returns default TypedDict with TDD values (e.g., n_outcomes=3, z='10000.0', mu_start='1.0'/end='2.0').
- `@pytest.fixture def initial_state(default_params) -> EngineState`: Initializes state via init_state.
- `test_compute_dynamic_params_linear(params)`: Verifies linear interpolation (e.g., mu at t=500/1000 = '1.5').
- `test_compute_dynamic_params_clamp()`: Checks t=0/start, t>T/end.
- `test_compute_dynamic_params_reset_mode()`: Tests 'reset' mode per round in mr_enabled.
- `test_compute_f_i()`: Asserts f_i =1-(N_active-1)*zeta, using active flags.
- `test_apply_own_impact_buy_yes()`: Verifies V_i += f_i*X, subsidy/L recompute.
- `test_apply_own_impact_sell_no()`: Verifies V_i -= f_i*X.
- `test_apply_cross_impacts_buy()`: Checks V_j += zeta*X for j!=i, active only.
- `test_apply_cross_impacts_sell_inactive()`: Ignores inactive in diversion.
- `test_get_new_prices_after_impact_buy_yes()`: Computes p_yes'=(q_yes+delta+virtual_yes)/(L+f_i*X), p_no'=q_no/(L+f_i*X).
- `test_get_new_prices_after_impact_sell_no_virtual()`: Similar for sell, with virtual_yes.
- `test_apply_asymptotic_penalty_buy_overflow()`: Asserts X' = X*(p'/p_max)^eta >X.
- `test_apply_asymptotic_penalty_sell_underflow()`: Asserts X' = X*(p_min/p')^eta <X.
- `test_apply_asymptotic_penalty_no_penalty()`: X unchanged if within bounds.

## Dependencies/Imports
- pytest; decimal (getcontext); typing/typing_extensions (Dict, Optional, TypedDict).
- From app.engine: impact_functions (all exports), state (EngineState, BinaryState, init_state, get_binary, update_subsidies, get_p_yes, get_p_no), params (EngineParams).
- From app.utils: safe_divide, price_value.
- Interactions: Uses fixtures for params/state; calls impact functions directly; asserts via Decimal equality.

## Usage Notes
- Tests pure functions/state mutations; Decimal precision=28; no DB/mocks, deterministic; tolerance implicit in exact asserts.
- Tie to TDD: Covers quadratics/impacts/diversions/virtual_yes/active flags per derivations; dynamic interp per addendum.
- For integration: Ensures impact logic preserves invariants (e.g., L=V+subsidy>0, p< p_max).

## Edge Cases/Invariants
- Edges: t=0/end, zeta max (f_i~0 raises implicitly), inactive N_active=1 (f_i=1), virtual_yes in eff p, Δ=0 unchanged.
- Invariants: f_i>0 clamped, V>=0, subsidy>=0, p_yes/no in [0,1), deterministic sorts ignored (no lists), post-impact L> q_yes_eff + q_no.