# test_state.py_context.md

## Overview
Implements unit tests for EngineState management in engine/state.py, covering initialization, serialization/deserialization, getters, and updates per TDD state variables and invariants (e.g., subsidy phase-out, p_yes/no=0.5 initial).

## Key Exports/Interfaces
- No exports; pytest test functions:
  - `test_init_state_defaults`: Verifies init_state defaults (p=0.5, invariants like subsidy>0, L=V+subsidy, q_yes+virtual_yes < L).
  - `test_init_state_varying_n`: Parametrized for n_outcomes=3/10, checks binaries len and pre_sum_yes.
  - `test_serialize_deserialize_round_trip`: Tests round-trip with lob_pools (str/int key handling).
  - `test_get_binary_valid/invalid`: Checks retrieval, raises ValueError on invalid outcome_i.
  - `test_get_p_yes_no`: Verifies p computations with/without virtual_yes.
  - `test_update_subsidies`: Parametrized for V multipliers (0/0.5/1.5), checks phase-out to zero.
  - `test_update_subsidies_invariants`: Ensures q_eff < L post-update.
  - `test_active_flags`: Verifies init active=True, p works if inactive.
- Fixtures: `default_params` (from config), `initial_state` (init_state call).

## Dependencies/Imports
- Imports: pytest, typing/typing_extensions (TypedDict), numpy (approx assertions), app.engine.state (*), app.config (get_default_engine_params).
- Interactions: Calls init_state/get_p_yes_no/update_subsidies from state.py; uses default_params from config.py; no DB/service calls (pure unit).

## Usage Notes
- Uses pytest with parametrize for edges; numpy for float precision (e.g., pytest.approx); deterministic (no random); ties to TDD invariants/proofs (e.g., q_yes + q_no < 2*L, solvency q_eff < L_i); covers multi-res via active flags indirectly.

## Edge Cases/Invariants
- Edges: Zero subsidy (V >= z/n/gamma), invalid outcome_i (ValueError), serialization with int/str ticks, virtual_yes>0/negative cap implied, varying N=3-10.
- Invariants: Tests subsidy>=0, L>0, initial p=0.5, q_yes/no >=q0, virtual_yes>=0, active=True init; solvency post-init/update; deterministic assertions.