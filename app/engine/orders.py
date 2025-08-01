from decimal import Decimal
from typing import List, Dict, Any, Tuple
from typing_extensions import TypedDict

from .state import EngineState, BinaryState, get_binary, update_subsidies, get_p_yes, get_p_no
from .params import EngineParams
from .amm_math import buy_cost_yes, sell_received_yes, buy_cost_no, sell_received_no, get_effective_p_yes, get_effective_p_no
from .impact_functions import compute_dynamic_params, compute_f_i, apply_own_impact, apply_cross_impacts, apply_asymptotic_penalty
from .lob_matching import add_to_lob_pool, cross_match_binary, match_market_order
from .autofill import trigger_auto_fills
from app.utils import usdc_amount, price_value, validate_price, validate_size, safe_divide

class Order(TypedDict):
    order_id: str
    user_id: str
    outcome_i: int
    yes_no: str
    type: str
    is_buy: bool
    size: Decimal
    limit_price: Decimal | None
    max_slippage: Decimal | None
    af_opt_in: bool
    ts_ms: int

class Fill(TypedDict):
    trade_id: str
    buy_user_id: str
    sell_user_id: str
    outcome_i: int
    yes_no: str
    price: Decimal
    size: Decimal
    fee: Decimal
    tick_id: int
    ts_ms: int

def apply_orders(
    state: EngineState,
    orders: List[Order],
    params: EngineParams,
    current_time: int
) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]:
    # Sort orders by ts_ms for deterministic processing
    orders = sorted(orders, key=lambda o: o['ts_ms'])

    # Compute dynamic parameters based on current time
    dyn_params = compute_dynamic_params(params, current_time)
    zeta = dyn_params['zeta']
    params_dyn = {**params, **dyn_params}  # Merge for use in functions

    # Determine N_active from active binaries
    active_binaries = [b for b in state['binaries'] if b['active']]
    N_active = len(active_binaries)

    fills: List[Fill] = []
    events: List[Dict[str, Any]] = []

    # Process all LIMIT orders first to add to pools
    for order in orders:
        if order['type'] != 'LIMIT':
            continue
        i = order['outcome_i']
        binary = get_binary(state, i)
        if not binary['active']:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': 'binary inactive'}})
            continue
        try:
            validate_size(order['size'])
            if order['limit_price'] is not None:
                validate_price(order['limit_price'])
        except ValueError as e:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': str(e)}})
            continue
        tick = int(order['limit_price'] / Decimal(params_dyn['tick_size']))  # Per TDD tick granularity
        add_to_lob_pool(state, i, order['yes_no'], order['is_buy'], tick, order['user_id'], order['size'], order['af_opt_in'])
        events.append({'type': 'ORDER_ACCEPTED', 'payload': {'order_id': order['order_id'], 'type': 'LIMIT'}})

    # Perform cross-matching for all binaries if enabled
    if params_dyn['cm_enabled']:
        for b in state['binaries']:
            if b['active']:
                cm_fills = cross_match_binary(state, b['outcome_i'], params_dyn, current_time, tick_id=0)  # tick_id placeholder
                fills.extend(cm_fills)

    # Process MARKET orders
    for order in orders:
        if order['type'] != 'MARKET':
            continue
        i = order['outcome_i']
        binary = get_binary(state, i)
        if not binary['active']:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': 'binary inactive'}})
            continue
        try:
            validate_size(order['size'])
        except ValueError as e:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': str(e)}})
            continue
        is_yes = order['yes_no'] == 'YES'
        is_buy = order['is_buy']
        size = order['size']
        # Match against LOB first
        lob_fills, remaining = match_market_order(state, i, is_buy, is_yes, size, params_dyn, current_time, tick_id=0)
        fills.extend(lob_fills)
        if remaining <= Decimal('0'):
            events.append({'type': 'ORDER_FILLED', 'payload': {'order_id': order['order_id']}})
            continue
        # AMM for remaining
        f_i = compute_f_i(params_dyn, zeta, state)
        current_p = get_effective_p_yes(binary) if is_yes else get_effective_p_no(binary)
        if is_yes:
            if is_buy:
                X = buy_cost_yes(binary, remaining, params_dyn, f_i)
            else:
                X = sell_received_yes(binary, remaining, params_dyn, f_i)
        else:
            if is_buy:
                X = buy_cost_no(binary, remaining, params_dyn, f_i)
            else:
                X = sell_received_no(binary, remaining, params_dyn, f_i)
        # Compute new price after impact
        new_p_yes, new_p_no = get_new_prices_after_impact(binary, remaining, X, f_i, is_buy, is_yes)
        effective_p = new_p_yes if is_yes else new_p_no
        # Apply asymptotic penalty if needed
        X = apply_asymptotic_penalty(X, effective_p, current_p, is_buy, params_dyn)
        # Recompute effective_p post-penalty (approximate, as penalty adjusts X)
        effective_p = (get_effective_p_yes(binary) + remaining if is_buy and is_yes else get_effective_p_yes(binary) - remaining if not is_buy and is_yes else ...) / (L + f_i * X * (1 if is_buy else -1))  # Simplified; use full get_new_prices
        # Use get_new_prices_after_impact again with adjusted X
        new_p_yes, new_p_no = get_new_prices_after_impact(binary, remaining, X, f_i, is_buy, is_yes)
        effective_p = new_p_yes if is_yes else new_p_no
        # Compute slippage
        if is_buy:
            slippage = safe_divide(effective_p - current_p, current_p)
        else:
            slippage = safe_divide(current_p - effective_p, current_p)
        if order['max_slippage'] is not None and slippage > Decimal(order['max_slippage']):
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': 'max slippage exceeded'}})
            continue
        # Apply fee (on trade value)
        fee = Decimal(params_dyn['fee_rate']) * remaining * effective_p
        # Create AMM fill
        fill: Fill = {
            'trade_id': str(len(fills)),  # Deterministic ID for demo
            'buy_user_id': order['user_id'] if is_buy else 'AMM',
            'sell_user_id': 'AMM' if is_buy else order['user_id'],
            'outcome_i': i,
            'yes_no': order['yes_no'],
            'price': price_value(effective_p),
            'size': usdc_amount(remaining),
            'fee': usdc_amount(fee),
            'tick_id': 0,  # Placeholder
            'ts_ms': current_time
        }
        fills.append(fill)
        # Apply own impact
        apply_own_impact(state, i, X, is_buy, is_yes, f_i, params_dyn)
        # Apply cross impacts (diversions)
        apply_cross_impacts(state, i, X, is_buy, zeta, params_dyn)
        # Update subsidies across all binaries
        update_subsidies(state, params_dyn)
        # Trigger auto-fills if enabled
        if params_dyn['af_enabled']:
            trigger_auto_fills(state, i, X, is_buy, params_dyn, current_time)
        events.append({'type': 'ORDER_FILLED', 'payload': {'order_id': order['order_id']}})

    return fills, state, events