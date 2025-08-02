# positions.py_context.md

## Overview
Service module for managing user positions, balance updates, gas deductions, and payouts in the Gaming Market Demo. Handles position tracking per user/binary (actual tokens excluding virtuals), integrates with engine state for updates, and enforces TDD invariants like q < L_i via engine; supports multi-res payouts and gas on submissions per impl plan.

## Key Exports/Interfaces
- `class Position(TypedDict)`: Dict with `position_id: str`, `user_id: str`, `outcome_i: int`, `yes_no: str`, `tokens: Decimal`.
- `fetch_user_positions(user_id: str) -> List[Dict[str, Any]]`: Fetches and quantizes user positions from DB; returns list of dicts with Position fields.
- `update_position_from_fill(fill: Dict[str, Any], state: EngineState) -> None`: Updates state q_yes/q_no and DB position from fill; increments user trade_count; validates size/tokens.
- `apply_payouts(resolution_data: Dict[str, Any], state: EngineState) -> None`: Applies payouts to balances/net_pnl, zeros positions for eliminated outcomes in state/DB; handles final unfilled returns (stubbed); updates mm_profit metric from state seigniorage.
- `deduct_gas(user_id: str, gas_fee: Decimal) -> None`: Deducts quantized gas from balance (raises if insufficient); updates total_gas metric.
- `update_balance(user_id: str, delta: Decimal) -> None`: Adds quantized delta to balance (raises if negative); used for proceeds/payouts.

## Dependencies/Imports
- From typing: List, Dict, Any; typing_extensions: TypedDict; decimal: Decimal.
- From .db.queries: fetch_positions, update_position, update_metrics, get_db.
- From .engine.state: EngineState, BinaryState, get_binary.
- From .utils: usdc_amount, validate_balance_buy/sell, validate_size, safe_divide.
- Interactions: Queries DB for CRUD on positions/users/metrics; mutates EngineState q_yes/q_no/active; calls utils for validation/quantization.

## Usage Notes
- Use Decimal via usdc_amount for 6-decimal precision (TDD USDC); DB numeric(18,6) but demo simplified.
- Atomic via direct DB calls (wrap in transactions externally for multi-op); integrate with orders.py for post-fill updates, resolutions.py for payouts.
- Gas deducted pre-order (even rejects); track in metrics for CSV/rankings per impl plan.
- JSON-compatible: Positions as dicts for serialization.

## Edge Cases/Invariants
- Invariants: Tokens >=0 post-update (raises on negative); q < L_i preserved via engine (not enforced here); actual q for payouts (exclude virtual_yes).
- Edges: Zero positions/tokens ok; insufficient balance/gas raises ValueError; multi-res burns eliminated positions/active=False; final distributes unfilled (implement lob pro-rata).
- Deterministic: No random; uses DB selects (assume sorted by queries); for tests: Cover buy/sell fills (token +/-), payouts (balance+/positions=0), gas deduct (metrics+), edges like zero delta/insufficient.