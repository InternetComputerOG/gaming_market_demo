# test_orders.py_context.md

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