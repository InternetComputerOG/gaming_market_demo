# test_amm_math.py_context.md

## Overview
Unit tests for amm_math.py, verifying AMM quadratics, price computations, penalties, and invariants per TDD derivations (e.g., positive roots, discriminant >=0, p' bounds). Uses pytest with fixtures for defaults; covers edges like zero delta, large trades triggering penalties, numerical stability.

## Key Exports/Interfaces
- `@pytest.fixture def default_params() -> EngineParams`: Returns default TypedDict with TDD values (e.g., n_outcomes=3, z=10000, mu_start=1, p_max=0.99).
- `@pytest.fixture def default_binary(default_params) -> BinaryState`: Initializes BinaryState with L=z/n_outcomes, q_yes=q_no=L/2, virtual_yes=0.
- `@pytest.fixture def f_i(default_params) -> Decimal`: Computes 1 - (n_outcomes-1)*zeta_start.
- Tests: `test_get_effective_p_yes(binary)`, `test_get_effective_p_no(binary)`, `test_get_new_p_yes_after_buy(binary, params, f_i)`, `test_get_new_p_yes_after_sell(...)`, similarly for NO; `test_buy_cost_yes(...)` (verifies quadratic coeffs, disc>=0, penalty if p'>p_max); `test_buy_cost_yes_zero_delta(...)` (cost=0); `test_buy_cost_yes_penalty(...)` (large delta inflates cost); `test_sell_received_yes(...)`; `test_buy_cost_no(...)`; `test_sell_received_no(...)`; `test_validate_size_negative()` (raises ValueError); `test_invariant_preservation_buy(...)` (new_q_eff < new_L); `test_discriminant_non_negative(...)` (disc>=0).

## Dependencies/Imports
- Imports: pytest, decimal (getcontext), typing (Dict, Any); from app.engine: amm_math (functions under test), state (BinaryState), params (EngineParams); from app.utils: validate_size, validate_price, price_value, solve_quadratic, safe_divide, decimal_sqrt.
- Interactions: Uses fixtures to mock state/params; asserts via Decimal comparisons; ties to TDD quadratics/penalties; no DB/runner calls, pure unit.

## Usage Notes
- Run with pytest; uses Decimal for precision (prec=28); asserts close for floats not used (Decimal exact); deterministic (no random); extend for dynamic params interpolation if needed. Implements TDD proofs (e.g., disc>=0, X>0, invariants q_eff < L).

## Edge Cases/Invariants
- Edges: delta=0 (cost=0), negative delta (raises), large delta (penalty, X→∞), κ=0 (linear approx), η=1 (minimal penalty), f_i<=0 raises implicitly via validate. Invariants: disc>=0 per TDD, q_eff < L post-trade, p'<p_max post-penalty; assumes valid params (zeta<1/(n-1)).