# services_orders.py_context.md

## Overview
Service for handling order submission, validation, cancellation, and DB operations in the Gaming Market Demo. Implements order lifecycle per impl plan (gas deduction on submit, batch buffering in DB, conservative estimates for slippage/confirmation UX), tying to TDD order types/validations.

## Key Exports/Interfaces
- `class Order(TypedDict)`: {'order_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'type': str, 'is_buy': bool, 'size': Decimal, 'limit_price': Optional[Decimal], 'max_slippage': Optional[Decimal], 'af_opt_in': bool, 'ts_ms': int}.
- `submit_order(user_id: str, order_data: Dict[str, Any]) -> str`: Validates order (size, price, balance with est slippage + gas_fee), deducts gas_fee, inserts to DB for batch, publishes event; raises ValueError on invalid/frozen; returns order_id.
- `cancel_order(order_id: str, user_id: str) -> None`: Validates ownership/status, refunds unfilled via engine cancel_from_pool, updates status to CANCELED, publishes event; raises ValueError on invalid.
- `get_user_orders(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]`: Fetches user's orders from DB, filtered by status.
- `estimate_slippage(outcome_i: int, yes_no: str, size: Decimal, is_buy: bool, max_slippage: Optional[Decimal]) -> Dict[str, Any]`: Simulates apply_orders on cloned state for conservative slippage est (abstracts penalties/auto-fills), returns {'estimated_slippage': Decimal, 'would_reject': bool, 'est_cost': Decimal}.

## Dependencies/Imports
- From decimal: Decimal; typing: Dict, Any, List, Optional; typing_extensions: TypedDict.
- From app.config: get_supabase_client, get_current_config (for params/status/gas_fee).
- From app.db.queries: fetch_engine_state, update_user_balance, insert_order, update_order_status, fetch_user_orders, fetch_user_balance, fetch_user_tokens, fetch_order, get_current_params.
- From app.engine.orders: Order (EngineOrder), apply_orders.
- From app.utils: usdc_amount, price_value, validate_size, validate_price, validate_balance_buy, validate_balance_sell, get_current_ms, safe_divide.
- From app.services.realtime: publish_event.
- Interactions: Calls DB for inserts/updates/fetches; uses engine apply_orders for sim in estimate_slippage; publishes to realtime on submit/cancel; assumes batch_runner handles actual processing.

## Usage Notes
- Use Decimal for precision, usdc_amount/price_value for quantization; JSON-compatible dicts for events.
- Gas_fee deducted always (even rejection); slippage est conservative (10% buffer) for UX confirmation, simulates full flow including auto-fills if enabled.
- Deterministic: ts_ms from get_current_ms; status updates for OPEN/FILLED/REJECTED/CANCELED per batch.
- Implements TDD validations (positive size, price [0,1], sufficient balance est including gas); integrates with batch_runner for apply_orders.

## Edge Cases/Invariants
- Edges: Zero size/negative raises; frozen/resolved rejects; insufficient balance/tokens raises (conservative est); slippage > max in sim returns would_reject=True but submit may differ post-batch.
- Invariants: Gas deducted before insert; orders sorted by ts_ms in batch; balance >=0 enforced via validations; solvency via engine invariants (q_eff < L_i); deterministic fetches/sims; rejection updates status but gas lost.