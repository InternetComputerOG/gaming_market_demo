# test_params.py_context.md

## Overview
Unit tests for params.py using pytest; covers defaults alignment with TDD (e.g., alpha=μ=1.0), validation raises on invalid ranges (per TDD symbols/ranges), and solve_quadratic numerical stability/selects min positive root (per TDD quadratics derivations).

## Key Exports/Interfaces
- No exports; pytest functions:
  - `test_get_default_params()`: Asserts defaults match TDD (e.g., alpha=1.0, beta=1.0, trade_fee=0.01, liquidity_initial=10000/3).
  - `test_validate_params_valid()`: No raise on defaults.
  - `test_validate_params_invalid_*()`: Raises ValueError on alpha<=0, beta<=0, trade_fee<0 or >=1, liquidity_initial<=0, max_imbalance_ratio>=1.
  - `test_solve_quadratic_*()`: Asserts min positive root (e.g., roots [1,2] ->1), TDD-like coeffs positive, edges (no positive/disc<0 raise ValueError), zero a raises.

## Dependencies/Imports
- Imports: pytest, numpy (np.roots/allclose), typing_extensions (TypedDict).
- From app.engine.params: Params, get_default_params, validate_params, solve_quadratic.
- Interactions: Pure unit; no DB/UI; tests TDD invariants (e.g., positive roots exist per proofs).

## Usage Notes
- Use pytest; numpy for float asserts; covers TDD ranges (e.g., alpha>0); deterministic; extend for dynamic interp if added (start/end validation).

## Edge Cases/Invariants
- Invariants: Discriminant>=0 assumed (TDD proofs), positive min root exists; tests zero coeffs, negative disc/no positive, double roots.
- Edges: Invalid params raise specific msgs; quadratic selects min positive (for min delta per TDD).