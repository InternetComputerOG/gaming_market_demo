# test_autofill.py_context.md

## Overview
Pytest-based unit tests for autofill.py, covering binary search, pool updates, rebates, auto-fill logic, edges, determinism, and invariants per TDD auto-filling/seigniorage and implementation plan's engine testing.

## Key Exports/Interfaces
- Fixtures: `default_params() -> EngineParams`: Defaults from TDD (e.g., n_outcomes=3, zeta_start=0.1).
- `initial_state(default_params) -> EngineState`: Initializes binaries with q0, subsidy.
- `sample_binary(initial_state) -> BinaryState`: Retrieves binary 1.
- `add_sample_pools(binary: BinaryState, is_yes: bool, is_buy: bool, tick: int, volume: Decimal, shares: Dict[str, Decimal]) -> None`: Adds test pools.
- Tests: `test_binary_search_max_delta_buy_yes`, `test_binary_search_max_delta_sell_yes`: Verify max Δ for p' <=/>= tick.
- `test_update_pool_and_get_deltas`: Checks pro-rata deltas, volume reduction.
- `test_apply_rebates`: Verifies (1-σ) surplus distribution.
- `test_auto_fill_buy_diversion`, `test_auto_fill_zero_diversion`, `test_auto_fill_no_pools`, `test_auto_fill_caps`: Test triggers, skips, caps (af_max_pools/surplus/frac).
- `test_auto_fill_determinism`: Ensures sorted ticks for consistent results.
- `test_auto_fill_negative_surplus`: Skips if surplus <=0.
- `test_auto_fill_invariants`: Asserts q_yes + q_no < 2*L, p_yes < p_max post-fill.

## Dependencies/Imports
- pytest; decimal: Decimal; typing: Dict, List, Tuple.
- From app.engine.autofill: binary_search_max_delta, update_pool_and_get_deltas, apply_rebates, auto_fill, AutoFillEvent.
- From app.engine.state: EngineState, BinaryState, get_binary, update_subsidies.
- From app.engine.params: EngineParams.
- From app.engine.amm_math: buy_cost_yes, sell_received_yes, get_effective_p_yes.
- From app.engine.impact_functions: compute_f_i.
- From app.utils: usdc_amount, price_value, validate_size, safe_divide.
- Interactions: Uses autofill funcs for testing; mocks state mutations; asserts via amm_math prices.

## Usage Notes
- Run with pytest; Decimal precision for financials; fixtures setup TDD defaults (q0=5000, z=10000).
- Covers TDD proofs (no cascades via caps, q_eff < L via penalties, seigniorage >=0); integrate with engine tests for full coverage.
- Deterministic: Fixed params, sorted pools; no random.

## Edge Cases/Invariants
- Zero diversion/pools/surplus: Return 0/[].
- Caps: Truncate Δ/surplus/pools.
- Negative surplus: Skip.
- Determinism: Tick sort desc/asc.
- Invariants: Post-fill q_yes + q_no < 2*L, p_yes < p_max, V/seigniorage >=0; validates size/price.
- Edges: Below/above p ticks, large diversion, multi-pools > max.