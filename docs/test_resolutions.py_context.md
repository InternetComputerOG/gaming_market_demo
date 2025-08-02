# test_resolutions.py_context.md

## Overview
Unit tests for resolutions.py using pytest; verifies multi-resolution mechanics like eliminations, payouts, redistribution, renormalization per TDD derivations/proofs; ensures solvency invariants, active flags, events; covers single/multi-res toggles.

## Key Exports/Interfaces
- Fixtures: default_params() -> EngineParams; initial_state(default_params) -> EngineState; mock_positions() -> List[Dict[str, Any]].
- Tests: test_intermediate_resolution(params, state, positions, mr_enabled, vc_enabled); test_final_resolution(params, state, positions, vc_enabled); test_virtual_cap_negative(params, state, positions); test_zero_positions(params, state); test_single_resolution_no_mr(params, state, positions).
- Helpers: assert_solvency(state: EngineState); calculate_pre_sum_yes(state: EngineState) -> Decimal.

## Dependencies/Imports
- From pytest: fixture, mark.parametrize; unittest.mock: patch.
- From app.engine: resolutions (trigger_resolution), state (EngineState, BinaryState, init_state, get_binary, get_p_yes, get_p_no, update_subsidies), params (EngineParams), amm_math (get_effective_p_yes/no), utils (Decimal, usdc_amount, price_value, safe_divide).
- Interactions: Patches fetch_positions; calls init_state, update_subsidies, trigger_resolution; asserts on payouts/state/events.

## Usage Notes
- Parametrized for mr_enabled/vc_enabled; uses Decimal for precision, pytest.approx for floats (1e-6 tol); mocks positions for payouts; assumes JSON-compatible state; deterministic (no random).
- Covers TDD renormalization (target_p = old_p / post_sum * pre_sum_yes), virtual cap if vc_enabled; integrates with state mutations, amm_math prices.

## Edge Cases/Invariants
- Edges: Negative virtual capped=0 (vc_enabled), zero freed/positions skips, inactive skips, sum_yes <= pre if capped; single-res as final auto-elim.
- Invariants: q_yes + q_no < 2*L post-res; actual payouts exclude virtuals; total risk <=Z; deterministic sorts by outcome_i; raises on invalid elims/negative disc.