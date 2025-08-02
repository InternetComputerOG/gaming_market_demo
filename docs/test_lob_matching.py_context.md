# test_lob_matching.py_context.md

## Overview
Unit tests for lob_matching.py, covering pool management, additions/cancellations, cross-matching (YES/NO if cm_enabled), market order matching (pro-rata, fees via f_match), and edges per TDD LOB/cross mechanics and impl plan batch execution. Uses pytest with fixtures for state/params; ensures determinism, Decimal precision, and invariants like q_yes + q_no < 2*L.

## Key Exports/Interfaces
- Fixtures: `default_params() -> EngineParams`: Returns TypedDict with defaults (e.g., n_outcomes=3, cm_enabled=True, tick_size=0.01).
- `init_state(default_params) -> EngineState`: Initializes state with binaries (V=0, L=subsidy, q_yes/no=q0, empty lob_pools).
- Test funcs: `test_get_pool_key()`, `test_get_tick_from_key()`, `test_is_opt_in_from_key()`: Basic key encoding.
- `test_add_to_lob_pool(state, params)`: Verifies pool volume/shares updates.
- `test_cancel_from_pool(state, params)`: Checks removal, returns amount, cleans empty.
- `test_cross_match_binary(state, params)`: Tests YES buy/NO sell matches (if cm_enabled), V/q updates, fees, pool clears.
- `test_match_market_order(state, params)`: Validates market fills vs sell pools (sorted asc), partials, remaining, invariants.
- `test_edge_cases(state, params)`: Covers empty/zero/inactive/invalid/negative cases, raises ValueErrors.

## Dependencies/Imports
- pytest; decimal: Decimal; typing: List/Dict/Any; typing_extensions: TypedDict.
- From .lob_matching: all exports (add_to_lob_pool, cancel_from_pool, etc.).
- From .state: EngineState/BinaryState/get_binary/update_subsidies.
- From .params: EngineParams.
- From app.utils: usdc_amount/price_value/validate_size/safe_divide.
- Interactions: Mutates mock state in-place; no DB; asserts on fills/remaining/state post-calls; ties to amm_math for pricing if needed in invariants.

## Usage Notes
- Pure unit tests (no DB/network); use Decimal for assertions; fixtures provide deterministic setup (e.g., q0 adjusted for L=~3333.33, p=0.5).
- Covers TDD solvency (V += (p_yes + p_no - f_match)*size >= size); impl plan toggles (cm_enabled).
- For integration: Tests ensure lob_matching interfaces stable; use in other tests for mock calls.

## Edge Cases/Invariants
- Edges: Zero/negative sizes raise ValueError; empty pools skip/raise; inactive binaries raise; invalid ticks raise; partial fills preserve shares.
- Invariants: Post-match q_yes + q_no < 2*L (via update_subsidies/assert); volume/shares >=0; deterministic sorts (ticks desc/asc); no auto-fill/impact calls here (isolated).