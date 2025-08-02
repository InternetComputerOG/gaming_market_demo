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