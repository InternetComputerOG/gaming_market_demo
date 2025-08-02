# services_resolutions.py_context.md

## Overview
Service for triggering resolutions (intermediate/final), handling payouts, state updates, and event publishing in the Gaming Market Demo. Implements automatic resolutions with freezes, eliminations, liquidity redistribution, and renormalization per TDD multi-resolution mechanics and impl plan automatic events.

## Key Exports/Interfaces
- `get_active_outcomes(state: EngineState) -> List[int]`: Returns sorted list of active outcome indices.
- `compute_pre_sum_yes(state: EngineState) -> Decimal`: Computes sum of effective p_yes across active binaries.
- `apply_payouts(payouts: Dict[str, Decimal]) -> None`: Atomically updates user balances in DB from payouts.
- `trigger_resolution_service(is_final: bool, elim_outcomes: Union[List[int], int], current_time: int) -> None`: Orchestrates resolution: loads state/params, calls engine.trigger_resolution, applies payouts, saves state, inserts events, updates metrics/status, publishes realtime.

## Dependencies/Imports
- From typing: List, Dict, Any, Union; typing_extensions: TypedDict; decimal: Decimal; supabase: Client.
- From app.config: get_supabase_client, EngineParams.
- From app.utils: get_current_ms, serialize_state, deserialize_state, usdc_amount, safe_divide.
- From app.db.queries: fetch_engine_state, save_engine_state, load_config, update_config, insert_events, update_metrics, fetch_positions, atomic_transaction.
- From app.engine.resolutions: trigger_resolution.
- From app.engine.state: EngineState.
- From app.services.realtime: publish_resolution_update.
- Interactions: Called by timer_service.py for timed triggers; updates DB config/status, state JSONB; uses engine for core logic.

## Usage Notes
- Use Decimal for precision in sums/p_yes; serialize for JSONB. Supports mr_enabled toggle (list elims intermediate, int final). Status set FROZEN then RESOLVED/RUNNING. Payouts based on actual q (not virtual). Tie to TDD: Renormalization preserves pre_sum_yes via virtual_yes adjustments, cap >=0 if vc_enabled.

## Edge Cases/Invariants
- Invariants: Actual q_yes/no < L_i preserved (engine raises on violation); virtual_yes >=0 capped; pre_sum_yes from active only; deterministic (sort elims).
- Edges: No elims/zero freed ok; negative virtual capped; no active raise; single-res (mr_enabled=False) only final; inactive elim skipped. For tests: Cover payouts reconciliation, renormalization sum preservation, edges like zero positions/subsidy.