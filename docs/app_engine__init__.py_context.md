# app_engine__init__.py_context.md

## Overview
Package initializer for /app/engine, exporting core deterministic APIs and types for the Gaming Market engine per Implementation Plan section 4. Acts as a facade for submodules implementing AMM math, state management, and features like cross-matching, auto-filling, and multi-resolution.

## Key Exports/Interfaces
- EngineState(TypedDict): Opaque dict for market state; keys: binaries (List[Dict[str, Any]] with V, L, q_yes, q_no, virtual_yes, subsidy, seigniorage, active, lob_pools (Dict[int, Dict[str, Any]] for yes_buy/yes_sell/no_buy/no_sell volumes/shares)).
- EngineParams(TypedDict): Config dict; keys: n_outcomes (int), outcome_names (List[str]), z/float, gamma/float, q0/float, mu_start/end/float, nu_start/end/float, kappa_start/end/float, zeta_start/end/float, interpolation_mode/str ('reset'/'continue'), f/float, p_max/float, p_min/float, eta/float, tick_size/float, cm_enabled/bool, f_match/float, af_enabled/bool, sigma/float, af_cap_frac/float, af_max_pools/int, af_max_surplus/float, mr_enabled/bool, res_schedule/List[int], vc_enabled/bool.
- Order(TypedDict): Order details; keys: order_id/str, user_id/str, outcome_i/int, yes_no/str, type/str, size/float, limit_price/float|None, max_slippage/float|None, af_opt_in/bool, ts_ms/int.
- Fill(TypedDict): Trade fill; keys: trade_id/str, buy_user_id/str, sell_user_id/str, outcome_i/int, yes_no/str, price/float, size/float, fee/float, tick_id/int, ts_ms/int.
- apply_orders(state: EngineState, orders: List[Order], params: EngineParams, current_time: int) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]: Processes batched orders deterministically (sorted by ts_ms/order_id), handles LOB/cross-matching/AMM/auto-fills with toggles, dynamic params interpolation, returns fills/new_state/events; per TDD derivations (quadratics, penalties, diversions).
- trigger_resolution(state: EngineState, params: EngineParams, is_final: bool, elim_outcomes: List[int]|int) -> Tuple[Dict[str, float], EngineState, List[Dict]]: Triggers resolution (intermediate/final), computes payouts from actual q_yes/q_no (excluding virtuals/q0), renormalizes virtual_yes, returns payouts/new_state/events; per TDD multi-resolution.

## Dependencies/Imports
- From typing: List, Tuple, Dict, Any, TypedDict.
- From .orders: apply_orders.
- From .resolutions: trigger_resolution.
- Interacts with: db/queries.py (JSONB state fetch/save), services/* (calls APIs), runner/batch_runner.py (invokes apply_orders in ticks), utils.py (validation/fixed-point), numpy (in submodules for quadratics/searches/interpolations).

## Usage Notes
- Pure Python, deterministic (sort orders, no randomness); use for batch ticks in runner.
- JSON-serialize state for DB; implement submodules per TDD (e.g., amm_math for solves, autofill for binary searches).
- Handle toggles (cm/af/mr_enabled) and dynamic params (linear interpolation via current_time, reset per round if 'reset').
- Essential for tests: Cover quadratics, impacts, auto-fills, renormalizations, interpolations, edges (p_max/min, zero subsidy, negative virtual cap).

## Edge Cases/Invariants
- Invariants: q_yes_eff + q_no < 2*L_i per binary (solvency), p < p_max; total risk <=z; deterministic with sorted orders; f_i >0 (zeta <1/(N_active-1)).
- Assumptions: Valid params in ranges, active outcomes in computations; no rejections (asymptotic penalties); multi-res preserves pre_sum_yes via virtuals (cap >=0 if vc_enabled).
- Edges: Empty orders (no-op), oversized trades (infinite cost/zero receive), frozen status via runner, N=3-10.