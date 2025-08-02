# engine_orders.py_context.md

## Overview
Module orchestrating batch order processing in the engine, implementing apply_orders as the main entry for deterministic handling of market/limit orders, integrating LOB/cross-matching, AMM trades, impacts, auto-fills, and state updates per TDD derivations and impl plan §4 (engine API).

## Key Exports/Interfaces
- `class Order(TypedDict)`: {'order_id': str, 'user_id': str, 'outcome_i': int, 'yes_no': str, 'type': str, 'is_buy': bool, 'size': Decimal, 'limit_price': Decimal | None, 'max_slippage': Decimal | None, 'af_opt_in': bool, 'ts_ms': int}.
- `class Fill(TypedDict)`: {'trade_id': str, 'buy_user_id': str, 'sell_user_id': str, 'outcome_i': int, 'yes_no': str, 'price': Decimal, 'size': Decimal, 'fee': Decimal, 'tick_id': int, 'ts_ms': int}.
- `apply_orders(state: EngineState, orders: List[Order], params: EngineParams, current_time: int) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]`: Processes sorted orders; adds limits to pools, performs cross-matches if enabled, matches/matches AMM for markets with slippage checks/rejects; applies impacts/auto-fills; returns fills, updated state, events (e.g., ORDER_ACCEPTED/REJECTED/FILLED).

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any, Tuple; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies, get_p_yes, get_p_no.
- From .params: EngineParams.
- From .amm_math: buy_cost_yes, sell_received_yes, buy_cost_no, sell_received_no, get_effective_p_yes, get_effective_p_no.
- From .impact_functions: compute_dynamic_params, compute_f_i, apply_own_impact, apply_cross_impacts, apply_asymptotic_penalty.
- From .lob_matching: add_to_lob_pool, cross_match_binary, match_market_order.
- From .autofill: trigger_auto_fills.
- From app.utils: usdc_amount, price_value, validate_price, validate_size, safe_divide.
- Interactions: Mutates state in-place (V, q, subsidies, lob_pools); called by runner/batch_runner.py in tick loops; uses amm_math for quadratics, impact_functions for diversions/penalties, lob_matching for LOB/cross, autofill on triggers; events for services/realtime.py.

## Usage Notes
- Deterministic: Sort orders by ts_ms, binaries by outcome_i; use Decimal for precision, price_value/usdc_amount for quantization.
- Handles partial fills, rejects on slippage > max_slippage (post-simulation); fees via params['fee_rate']; gas deductions implied (DB side).
- Dynamic params via compute_dynamic_params; N_active from active binaries; symmetric YES/NO handling.
- Implements TDD quadratics/penalties/diversions/cross-matching/auto-fills; invariants enforced via validations/penalties.
- JSON-compatible: Events as dicts; state mutations for DB save via queries.py.

## Edge Cases/Invariants
- Edges: Zero size skips (validate_size raises); inactive binary rejects; empty orders returns empty; oversized AMM via penalties (no rejection except slippage); zero subsidy continues; zeta clamped for f_i >0.
- Invariants: q_yes_eff + q_no < 2*L_i preserved (penalties); total risk <=Z; deterministic fills/events; post-update subsidies recomputed; slippage = (effective_p - current_p)/current_p for buys (symmetric sells).