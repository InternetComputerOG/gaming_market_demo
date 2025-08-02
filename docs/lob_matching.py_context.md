# lob_matching.py_context.md

## Overview
Module for limit order book (LOB) operations in the engine, including pool management at tick granularity, pro-rata matching, cross-matching YES/NO limits if cm_enabled, and market order fills vs LOB per TDD cross-matching mechanics and impl plan batch execution.

## Key Exports/Interfaces
- `get_pool_key(tick: int, af_opt_in: bool) -> int`: Encodes tick with sign for opt-in (positive if opt-in).
- `get_tick_from_key(key: int) -> int`: Extracts absolute tick from key.
- `is_opt_in_from_key(key: int) -> bool`: Checks if key positive for opt-in.
- `add_to_lob_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, amount: Decimal, af_opt_in: bool) -> None`: Adds amount to pool, updates volume/shares.
- `cancel_from_pool(state: EngineState, i: int, yes_no: str, is_buy: bool, tick: int, user_id: str, af_opt_in: bool) -> Decimal`: Removes user share, returns amount; cleans empty pools.
- `cross_match_binary(state: EngineState, i: int, params: EngineParams, current_ts: int, tick_id: int) -> List[Dict[str, Any]]`: Performs cross-matching YES buys with NO sells if cm_enabled, sorted descending ticks; updates V, q_yes, subsidies; pro-rata fills; returns aggregated fills.
- `match_market_order(state: EngineState, i: int, is_buy: bool, is_yes: bool, size: Decimal, params: EngineParams, current_ts: int, tick_id: int) -> tuple[List[Dict[str, Any]], Decimal]`: Matches market order vs opposing pools (sorted by price), pro-rata fills with fees; returns fills and remaining size.

## Dependencies/Imports
- From decimal: Decimal; typing: List, Dict, Any; typing_extensions: TypedDict.
- From .state: EngineState, BinaryState, get_binary, update_subsidies.
- From .params: EngineParams.
- From app.utils: usdc_amount, price_value, validate_price, validate_size, safe_divide.
- From .amm_math: get_effective_p_yes, get_effective_p_no.
- Interactions: Mutates state.lob_pools in-place; called by orders.py for matching in apply_orders; integrates with impact_functions.py for post-match updates; state serialized to DB via queries.py.

## Usage Notes
- Pools stored in state.lob_pools as nested dicts: yes_no -> buy/sell -> key(int): {'volume': Decimal, 'shares': {user_id: Decimal}}; keys encode af_opt_in.
- Deterministic: Sort ticks descending (buys/cross) or ascending (sells); pro-rata via shares ratios.
- Implements TDD solvency: In cross-match, caps fill to ensure V += (price_yes - price_no)*fill >= fill; fees via f_match.
- Use Decimal for precision; validate_size/price on inputs; handle partial fills.

## Edge Cases/Invariants
- Assumes active binaries only (ignore inactive); empty/zero volume pools deleted; partial fills ok; no matches if prices <1 or yes <= no.
- Invariants: Volume >=0; shares sum = volume; q_yes + q_no <2*L preserved (cross-match adds balanced); deterministic with hash(ts) for IDs.
- Edges: Oversized fill capped; negative keys for non-opt-in; zero fill skips; assumes tick_size >0, cm_enabled toggles.