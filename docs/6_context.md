# 6_context.md

## test_state.py_context.md

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

## test_params.py_context.md

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

## test_amm_math.py_context.md

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

## test_impact_functions.py_context.md

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

## test_autofill.py_context.md

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

## test_lob_matching.py_context.md

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

## test_orders.py_context.md

## Overview
Unit/integration tests for orders.py, focusing on apply_orders: covers market/limit processing, LOB/cross-matching, AMM trades with quadratics/penalties, impacts, auto-fills (binary search/seigniorage/caps), fees, state updates, events; validates invariants (q_eff + q_no < 2*L, determinism via sorted ts_ms), dynamic params, multi-res (N_active), edges (oversized penalties, rejects, zero subsidy/delta, partial fills, cascades prevention).

## Key Exports/Interfaces
- No exports; pytest tests/fixtures:
  - `@pytest.fixture default_params() -> EngineParams`: Returns dict with TDD defaults (n_outcomes=3, z=10000, etc., toggles True).
  - `@pytest.fixture initial_state(default_params) -> EngineState`: Calls init_state.
  - Tests: test_apply_orders_zero_orders, test_apply_market_buy_yes_basic (assert fills/price ~0.5+, p_yes>0.5), test_apply_limit_add (lob_pools update), test_limit_matching_with_market (partial fills, remaining volume), test_cross_matching_enabled (YES buy/NO sell match if sum>=1, q_yes/no up), test_auto_fill_triggered (diversion triggers, events, q fill), test_dynamic_params_interpolation (price differs by t, zeta change), test_multi_res_active_count (diversion only active, N_active affects f_i), test_oversized_penalty (p< p_max, high impact), test_slippage_reject (tight max_slippage: no fills, REJECTED), test_solvency_invariant_after_batch (q_eff + q_no <2*L, <L), test_determinism_same_inputs (same outputs), test_edge_zero_size_validation (raises), test_edge_negative_diversion_autofill (sell triggers auto-sell), test_caps_prevent_cascades (fills <= af_max_pools).

## Dependencies/Imports
- pytest; decimal: Decimal; typing: List/Dict/Any/Tuple; typing_extensions: TypedDict.
- From .orders: apply_orders/Order/Fill; .state: EngineState/BinaryState/init_state/get_binary/get_p_yes/get_p_no/update_subsidies; .params: EngineParams; .amm_math: get_effective_p_yes/get_effective_p_no; utils: usdc_amount/price_value/validate_size/validate_price/safe_divide.
- Interactions: Calls apply_orders with mocked state/orders/params/ts; asserts per TDD derivations (quadratics/penalties/diversions/auto-fills/cross-match); no DB, pure engine.

## Usage Notes
- Fixtures for params/state/orders; Decimal precision; mock ts_ms for determinism/interpolation; toggles in params; JSON-compatible asserts; per TDD proofs (disc>0, q<L preserved via penalties); cover toggles (cm/af/mr_enabled).

## Edge Cases/Invariants
- Edges: Zero/empty (unchanged), invalid raises, partial/pro-rata exact, oversized p~p_max, reject slippage>max (state unchanged), negative diversion (auto-sell), caps (fills<=max_pools/surplus), inactive no diversion, multi-res f_i>0 clamped.
- Invariants: Deterministic (sorted ts_ms, same inputs=outputs), q_eff< L (penalties), q_yes + q_no <2*L, V>=0, subsidy>=0, events match (FILLED/REJECTED/AUTO_FILL), precision via price_value.

## test_resolutions.py_context.md

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

## requirements.txt_context.md
The contents of this file are:
```
decimal
matplotlib
mpmath
numpy
pandas
pytest
streamlit
supabase
typing_extensions
```

## setup.py_context.md

## Overview
Packaging script for the Gaming Market Demo's engine package, enabling installation for testing and reuse per implementation plan's repository structure. Defines a simple setuptools configuration for the 'gaming-market-engine' package.

## Key Exports/Interfaces
- No exported functions or classes; executes `setup()` from setuptools to define package metadata and dependencies.

## Dependencies/Imports
- Imports: setuptools (setup, find_packages).
- Interactions: References app/engine directory for packaging; install_requires lists engine-specific deps (decimal, mpmath, numpy, typing_extensions) from requirements.txt; no runtime calls to other files.

## Usage Notes
- Run `python setup.py install` to package/install engine locally for unit tests; JSON-compatible with demo (no direct serialization); ties to TDD by supporting numpy for quadratics in engine/amm_math.py. Use for demo-scale testing without full app.

## Edge Cases/Invariants
- Invariants: Package name/version fixed; install_requires ensures numerical stability (numpy for solves). Edges: Missing deps raise errors; deterministic packaging (no dynamic content). Assumes Python >=3.12 per classifiers.