# ticks.py_context.md

## Overview
Service for tick processing, computing summaries (prices, volumes, MM risk/profit), inserting ticks to DB, and updating metrics per impl plan §6; integrates with batch_runner for post-engine atomic ops.

## Key Exports/Interfaces
- `class Fill(TypedDict)`: Dict for trade fills with keys: trade_id (str), buy_user_id (str), sell_user_id (str), outcome_i (int), yes_no (str), price (float), size (float), fee (float), tick_id (int), ts_ms (int).
- `def compute_summary(state: EngineState, fills: List[Fill]) -> Dict[str, Any]`: Computes JSON-compatible summary with 'prices' (dict of outcome_i: {'p_yes': float, 'p_no': float, 'active': bool}), 'volume' (sum sizes), 'mm_risk' (sum subsidies), 'mm_profit' (sum seigniorage + fees), 'n_active' (int); sorts binaries by outcome_i for determinism.
- `def create_tick(state: EngineState, fills: List[Fill], tick_id: int) -> None`: Inserts tick to DB with ts_ms and summary; updates metrics with volume, mm_risk, mm_profit.

## Dependencies/Imports
- From typing: List, Dict, Any; typing_extensions: TypedDict.
- From app.utils: get_current_ms.
- From app.db.queries: insert_tick, update_metrics (get_current_tick imported but unused).
- From app.engine.state: EngineState, BinaryState, get_p_yes, get_p_no.
- Interactions: Called by runner/batch_runner.py after apply_orders; uses state for summaries per TDD state fields; DB inserts for persistence.

## Usage Notes
- Summaries JSONB-compatible (floats from Decimals); mm_risk = sum(subsidy_i), mm_profit = sum(seigniorage_i) + sum(fees) per TDD; tie to multi-res via active flags. Deterministic: Sort binaries; use in realtime.py for broadcasts.

## Edge Cases/Invariants
- Empty fills: volume=0; zero subsidies/mm_risk=0; no binaries: empty prices/n_active=0. Invariants: Prices <1 per TDD; summaries positive/non-neg; floats for JSON; assumes valid state (q_eff < L_i enforced elsewhere).