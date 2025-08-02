## Overview
Provides general utility functions for timestamp handling, decimal precision arithmetic, input validation, state serialization, and mathematical helpers like quadratic solves, supporting deterministic computations across engine and services per implementation plan.

## Key Exports/Interfaces
- `USDC_DECIMALS: int = 6`: Constant for USDC decimal places.
- `PRICE_DECIMALS: int = 4`: Constant for price decimal places.
- `get_current_ms() -> int`: Returns current timestamp in milliseconds.
- `to_ms(ts: float) -> int`: Converts float timestamp to milliseconds.
- `from_ms(ms: int) -> float`: Converts milliseconds to float timestamp.
- `usdc_amount(amount: float | str | Decimal) -> Decimal`: Quantizes amount to USDC precision.
- `price_value(p: float | str | Decimal) -> Decimal`: Quantizes price to PRICE_DECIMALS.
- `validate_price(p: Decimal) -> None`: Raises ValueError if p not in [0,1].
- `validate_size(s: Decimal) -> None`: Raises ValueError if s <=0.
- `validate_balance_buy(balance: Decimal, size: Decimal, est_price: Decimal, gas_fee: Decimal) -> None`: Raises ValueError if balance < size * est_price + gas_fee.
- `validate_balance_sell(tokens: Decimal, size: Decimal) -> None`: Raises ValueError if tokens < size.
- `serialize_state(state: Dict[str, Any]) -> str`: JSON-serializes state, handling Decimal and numpy floats.
- `deserialize_state(json_str: str) -> Dict[str, Any]`: Deserializes JSON to dict.
- `decimal_sqrt(d: Decimal) -> Decimal`: Computes square root using mpmath; raises on negative.
- `solve_quadratic(a: Decimal, b: Decimal, c: Decimal) -> Decimal`: Solves quadratic equation (positive root); raises on negative discriminant. Implements TDD quadratic for AMM costs.
- `safe_divide(num: Decimal, den: Decimal) -> Decimal`: Divides with zero-check; raises ValueError on den=0.

## Dependencies/Imports
- Imports: json, time, decimal (getcontext), typing (Dict, Any), mpmath (mp), numpy (np).
- Interactions: Used by engine/* (e.g., quadratics in amm_math.py, sqrt in solves), services/* (validations in orders.py), db/queries.py (timestamps), runner/* (ms intervals); provides precision helpers for all Decimal ops.

## Usage Notes
- Use Decimal for all financial calcs to maintain 6-decimal USDC precision (adjusted from TDD's 18 for demo simplicity); serialize_state ensures JSONB compatibility for DB state. Employ solve_quadratic in AMM/impact functions per TDD Derivations. Validations enforce TDD invariants like positive sizes, prices in [0,1]. Timestamps in ms for batch intervals and events.

## Edge Cases/Invariants
- Assumes Decimal inputs for precision; raises on invalid (e.g., negative sqrt/discriminant, zero divide) to prevent invalid states. Deterministic: No random elements; quadratics assume positive discriminant per TDD proofs. Invariants: Quantized values prevent overflow; validations ensure sufficient funds conservatively (est_price includes slippage). For tests: Cover edges like zero size, p=0/1, negative disc, exact quantize.