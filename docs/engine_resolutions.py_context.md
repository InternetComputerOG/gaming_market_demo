# engine_resolutions.py_context.md

## Overview
Module for handling multi-resolution eliminations and final payouts in the engine, including NO payouts on eliminated outcomes, liquidity redistribution, and YES price renormalization via virtual_yes adjustments per TDD multi-resolution mechanics and implementation plan's trigger_resolution API.

## Key Exports/Interfaces
- `trigger_resolution(state: EngineState, params: EngineParams, is_final: bool, elim_outcomes: Union[List[int], int]) -> tuple[Dict[str, Decimal], EngineState, List[Dict[str, Any]]]`: Processes intermediate (list elims) or final (int winner) resolution; computes payouts from positions, subtracts from V_i, redistributes freed (L_i - total_q_no), renormalizes virtual_yes for remaining (target_p = (old_p / post_sum) * pre_sum_yes, cap >=0 if vc_enabled); mutates state (active=False, V/L updates, subsidies); returns user payouts, updated state, events list (e.g., {'type': 'ELIMINATION', ...}).

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any, Union; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies, get_p_yes.
- From .params: EngineParams.
- From app.utils: safe_divide, usdc_amount.
- From app.db.queries: fetch_positions.
- Interactions: Mutates state in-place (V/L/active/virtual_yes); fetches positions from DB for actual q_yes/no sums (excludes virtual); called by runner/timer_service.py for automatic resolutions; events for realtime.py pushes.

## Usage Notes
- Use Decimal for all calcs/quantization; state mutations ensure JSON-serializable floats; supports mr_enabled toggle (single-res as final auto-elim); pre_sum_yes from active p_yes sum; redistribute freed / remaining_active; integrates with orders.py invariants (no trades during pause implied).
- For tests: Cover solvency checks (raise if q_no > L), virtual cap, final q_yes payout, zero positions, determinism via sorted elims.

## Edge Cases/Invariants
- Invariants: Actual q_no/yes < L_i preserved (raise on violation); virtual_yes >=0 if vc_enabled; total risk <=Z unchanged; deterministic (sort elims, sum active only).
- Edges: No elims raise; zero freed skips; negative virtual capped (sum may < pre_sum); single-res (mr_enabled=False) only final; inactive elim skipped.