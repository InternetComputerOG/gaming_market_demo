# ticks.py_context.md

## Overview
Service module for tick processing in the Gaming Market Demo, including summary computation with LOB/cross-matching metrics, fill normalization, cross-match event extraction, tick creation (DB insertion/metrics update), and LOB pool statistics for admin monitoring. Implements enhanced LOB integration per TDD cross-matching/auto-filling and Implan §3.3 (LOB activity in summaries); called by batch_runner.py for post-engine tick handling (Lines 1-20: Imports/setup; 21-150: compute_summary; 151-220: normalize_fills; 221-300: extract_events; 301-400: create_tick; 401-end: get_lob_stats).

## Key Exports/Interfaces
- **Fill** (TypedDict, Lines 30-45): Enhanced fill for LOB/cross/AMM; fields: trade_id (str), buy_user_id (str), sell_user_id (str), outcome_i (int), yes_no (str), price (float), size (float), fee (float), tick_id (int), ts_ms (int), fill_type (str: 'CROSS_MATCH'/'LOB_MATCH'/'AMM'), price_yes/price_no (Optional[float]).
- **CrossMatchEvent** (TypedDict, Lines 50-70): Cross-match record; fields: event_id (str), outcome_i (int), yes_tick/no_tick (int), price_yes/price_no (float), fill_size (float), fee (float), yes_pool_volume_before/after (float), no_pool_volume_before/after (float), solvency_condition (float), min_required (float), tick_id (int), ts_ms (int).
- **compute_summary(state: EngineState, fills: List[Fill], cross_match_events: List[CrossMatchEvent] = None) -> Dict[str, Any]** (Lines 75-150): Computes stats from state/fills/events incl LOB activity (total_lob_volume/cross_match_count/etc), per-binary pools, cross-matching metrics (avg_solvency_margin/pool_utilization); aggregates mm_risk/profit, uses get_p_yes/no; returns nested dict with 'p_yes'/'p_no' lists, 'volume', etc.
- **normalize_fills_for_summary(fills: List[Dict[str, Any]]) -> List[Fill]** (Lines 155-220): Normalizes raw fills to Fill format, classifying by type ('CROSS_MATCH' if price_yes/no present, 'AMM' if AMM_USER_ID, else 'LOB_MATCH'); computes effective_price for cross.
- **extract_cross_match_events(fills: List[Fill], state: EngineState) -> List[CrossMatchEvent]** (Lines 225-300): Extracts events from cross fills; computes solvency/min_required (hardcoded f_match=0.02), estimates pool volumes (e.g., size * price_yes * 1.1 before/0.1 after); simplified tick=price*100.
- **create_tick(state: EngineState, raw_fills: List[Dict[str, Any]], tick_id: int, timestamp: int) -> None** (Lines 305-400): Normalizes fills, extracts events, computes summary, inserts tick/summary to DB via insert_tick, updates metrics with LOB/cross data via update_metrics; stores events in summary (no separate table).
- **get_lob_pool_statistics(state: EngineState) -> Dict[str, Any]** (Lines 405-end): Extracts LOB stats (total_pools/active_pools/total_volume/active_users/per_outcome breakdowns); parses pool_key ('outcome_i:yes_no:is_buy:tick'), sums volumes/shares; returns dict for admin dashboard.

## Dependencies/Imports
- Imports: typing (TypedDict/Dict/Any/List/Optional), decimal.Decimal (Lines 1-5).
- From app: engine.state (EngineState/get_binary/get_p_yes/no), utils (price_value/usdc_amount), db (get_db/insert_tick/update_metrics) (Lines 6-10).
- Interactions: Uses state for binary/LOB pool analysis; DB for tick/metrics insertion; called by batch_runner.py post-apply_orders; integrates with engine/orders.py for fills (raw_fills from apply_orders); admin dashboard in streamlit_admin.py may use get_lob_pool_statistics.

## Usage Notes
- Implements TDD LOB/cross-matching enhancements (§Derivations) for summaries/events; use Decimal for precision but converts to float for summary/DB JSONB.
- Tick creation normalizes fills, extracts events (simplified estimates), computes summary per Implan §3.3 (LOB metrics); metrics_data incl lob_total_volume/cross_match_volume/etc for update_metrics.
- AMM_USER_ID matches engine/orders.py for classification; fill_type defaults 'AMM' for compat.
- get_lob_pool_statistics for admin monitoring (per-outcome pool counts/volumes); assumes state['lob_pools'] as dict with keys 'outcome_i:yes_no:is_buy:tick'.
- Deterministic: Aggregates from state/fills; no engine calls, but uses get_p_yes/no.

## Edge Cases/Invariants
- Edges: Empty fills/events → zero metrics; no lob_pools → zero stats; cross fills without price_yes/no → not extracted; malformed pool_key → skipped in stats.
- Invariants: Summary 'mm_risk' = sum |q_yes - q_no|; 'mm_profit' += seigniorage + fees; lob_volume = cross + lob_match; solvency_condition = price_yes + price_no >= min_required (1 + f_match*(price_yes+price_no)/2); pool_utilization avg(yes/no) in 0-1; assumes N_active from state.active flags.

## Inconsistencies/Possible Issues
- Hardcoded f_match=0.02 in extract_events (Line 275) inconsistent with dynamic params in engine/params.py or config; should fetch from state/params per TDD/Implan.
- Simplified pool volume estimates (Lines 280-285: before=size*price*1.1, after=0.1) inaccurate; actual before/after from state.lob_pools not captured (requires pre/post snapshots in batch_runner).
- Tick calc int(price*100) (Lines 260-265) assumes tick_size=0.01 but per TDD tick_size configurable (default 0.01); use price/tick_size.
- create_tick stores events in summary but notes separate table needed (Line 370); incomplete per Implan observability (events table for audit).
- Integration with services_orders.py: Raw_fills may have varying structures (e.g., from apply_orders with 'source' absent); normalize assumes 'price_yes' present for cross, but engine may not set consistently—check engine_orders.py_context.md.
- With streamlit_app.py: get_lob_pool_statistics for admin, but streamlit_app.py_context.md mentions admin dashboard with graph/exports, not explicit stats; potential mismatch if UI expects per-outcome from DB vs state.
- No handling for multi-res active flags in summary (uses binary['active']); assumes all binaries processed, but TDD mr_enabled may filter.
- Metrics update (Lines 380-400) adds lob_*/cross_* keys, but db/schema.sql may need extension; assumes update_metrics handles extras.