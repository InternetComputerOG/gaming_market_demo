from decimal import Decimal
from typing import List, Dict, Any, Tuple
from typing_extensions import TypedDict
import uuid

from .state import EngineState, BinaryState, get_binary, update_subsidies, get_p_yes, get_p_no
from .params import EngineParams
from .amm_math import buy_cost_yes, sell_received_yes, buy_cost_no, sell_received_no, get_effective_p_yes, get_effective_p_no
from .impact_functions import compute_dynamic_params, compute_f_i, apply_own_impact, apply_cross_impacts, apply_asymptotic_penalty, get_new_prices_after_impact
from .lob_matching import add_to_lob_pool, cross_match_binary, match_market_order
from .autofill import trigger_auto_fills
from app.utils import usdc_amount, price_value, validate_price, validate_size, safe_divide, validate_engine_state, validate_binary_state, validate_solvency_invariant

# AMM User ID - special UUID for AMM trades to satisfy database foreign key constraints
AMM_USER_ID = '00000000-0000-0000-0000-000000000000'

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
    fill_type: str  # 'CROSS_MATCH', 'LOB_MATCH', 'AMM', 'AUTO_FILL'
    price_yes: Decimal | None  # For cross-matches: YES limit price
    price_no: Decimal | None   # For cross-matches: NO limit price

def apply_orders(
    state: EngineState,
    orders: List[Order],
    params: EngineParams,
    current_time: int
) -> Tuple[List[Fill], EngineState, List[Dict[str, Any]]]:
    # Validate engine state at start of order processing
    try:
        validate_engine_state(state, params)
    except ValueError as e:
        # Log validation error and raise to prevent processing with invalid state
        raise ValueError(f"Engine state validation failed at start of apply_orders: {e}")
    
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
        
        # Validate binary state before processing
        try:
            validate_binary_state(binary, params_dyn)
        except ValueError as e:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': f'Binary state validation failed: {e}'}})
            continue
            
        if not binary['active']:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': 'binary inactive'}})
            continue
        try:
            validate_size(order['size'])
            if order['limit_price'] is not None:
                validate_price(order['limit_price'])
                # Validate limit price bounds per TDD [p_min, p_max]
                if order['limit_price'] < Decimal(str(params_dyn['p_min'])) or order['limit_price'] > Decimal(str(params_dyn['p_max'])):
                    raise ValueError(f"Limit price {order['limit_price']} outside bounds [{params_dyn['p_min']}, {params_dyn['p_max']}]")
        except ValueError as e:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': str(e)}})
            continue
        tick = int(order['limit_price'] / Decimal(params_dyn['tick_size']))  # Per TDD tick granularity
        add_to_lob_pool(state, i, order['yes_no'], order['is_buy'], tick, order['user_id'], order['size'], order['af_opt_in'], Decimal(params_dyn['tick_size']))
        events.append({'type': 'ORDER_ACCEPTED', 'payload': {'order_id': order['order_id'], 'type': 'LIMIT'}})

    # Perform cross-matching for all binaries if enabled
    # Cross-matching implements true limit price enforcement:
    # - YES buyers pay exactly their limit price T
    # - NO sellers receive exactly their limit price S  
    # - Trading fees applied separately: f_match * (T + S) / 2 split between sides
    # - System collateral: V_i += (T + S) * fill - fee
    if params_dyn['cm_enabled']:
        for b in state['binaries']:
            if b['active']:
                # Validate binary state before cross-matching
                try:
                    validate_binary_state(b, params_dyn)
                except ValueError as e:
                    # Log validation error but continue with other binaries
                    events.append({'type': 'VALIDATION_ERROR', 'payload': {'outcome_i': b['outcome_i'], 'reason': f'Binary state validation failed before cross-matching: {e}'}})
                    continue
                    
                cm_fills = cross_match_binary(state, b['outcome_i'], params_dyn, current_time, tick_id=0)  # tick_id placeholder
                
                # Convert cross-match fills to proper Fill format with dual prices
                for cm_fill in cm_fills:
                    fill: Fill = {
                        'trade_id': cm_fill['trade_id'],
                        'buy_user_id': cm_fill['buy_user_id'],
                        'sell_user_id': cm_fill['sell_user_id'],
                        'outcome_i': cm_fill['outcome_i'],
                        'yes_no': cm_fill['yes_no'],
                        'price': price_value(cm_fill['price_yes']),  # Use YES price as primary price for compatibility
                        'size': usdc_amount(cm_fill['size']),
                        'fee': usdc_amount(cm_fill['fee']),
                        'tick_id': cm_fill['tick_id'],
                        'ts_ms': cm_fill['ts_ms'],
                        'fill_type': 'CROSS_MATCH',
                        'price_yes': price_value(cm_fill['price_yes']),
                        'price_no': price_value(cm_fill['price_no'])
                    }
                    fills.append(fill)
                
                # Validate solvency after cross-matching
                try:
                    validate_solvency_invariant(b)
                except ValueError as e:
                    # This is critical - solvency violation should halt processing
                    raise ValueError(f"Solvency invariant violated after cross-matching for binary {b['outcome_i']}: {e}")

    # Process MARKET orders
    for order in orders:
        if order['type'] != 'MARKET':
            continue
        i = order['outcome_i']
        binary = get_binary(state, i)
        
        # Validate binary state before processing market order
        try:
            validate_binary_state(binary, params_dyn)
        except ValueError as e:
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': f'Binary state validation failed: {e}'}})
            continue
            
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
        # Match against LOB first - implements true limit price enforcement
        # Market orders get filled at limit order prices (at-or-better execution)
        # Fees are applied transparently and separately from execution prices
        lob_fills, remaining = match_market_order(state, i, is_buy, is_yes, size, params_dyn, current_time, tick_id=0)
        
        # Convert LOB fills to proper Fill format with fill_type
        for lob_fill in lob_fills:
            fill: Fill = {
                'trade_id': lob_fill['trade_id'],
                'buy_user_id': lob_fill['buy_user_id'],
                'sell_user_id': lob_fill['sell_user_id'],
                'outcome_i': lob_fill['outcome_i'],
                'yes_no': lob_fill['yes_no'],
                'price': price_value(lob_fill['price']),
                'size': usdc_amount(lob_fill['size']),
                'fee': usdc_amount(lob_fill['fee']),
                'tick_id': lob_fill['tick_id'],
                'ts_ms': lob_fill['ts_ms'],
                'fill_type': 'LOB_MATCH',
                'price_yes': None,  # LOB matches have single price
                'price_no': None
            }
            fills.append(fill)
        
        # Update q_yes/q_no for LOB market matches (per TDD: market orders vs LOB should update the traded q)
        if lob_fills:
            binary = get_binary(state, i)
            total_lob_fill_size = sum(Decimal(fill['size']) for fill in lob_fills)
            if is_yes:
                if is_buy:
                    binary['q_yes'] = float(Decimal(binary['q_yes']) + total_lob_fill_size)
                else:
                    binary['q_yes'] = float(Decimal(binary['q_yes']) - total_lob_fill_size)
            else:
                if is_buy:
                    binary['q_no'] = float(Decimal(binary['q_no']) + total_lob_fill_size)
                else:
                    binary['q_no'] = float(Decimal(binary['q_no']) - total_lob_fill_size)
            
            # Validate solvency after LOB q updates
            try:
                validate_solvency_invariant(binary)
            except ValueError as e:
                # Critical error - rollback the LOB q changes and reject order
                if is_yes:
                    if is_buy:
                        binary['q_yes'] = float(Decimal(binary['q_yes']) - total_lob_fill_size)
                    else:
                        binary['q_yes'] = float(Decimal(binary['q_yes']) + total_lob_fill_size)
                else:
                    if is_buy:
                        binary['q_no'] = float(Decimal(binary['q_no']) - total_lob_fill_size)
                    else:
                        binary['q_no'] = float(Decimal(binary['q_no']) + total_lob_fill_size)
                # Remove the LOB fills that were just added
                for _ in range(len(lob_fills)):
                    fills.pop()
                events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': f'LOB solvency invariant violated: {e}'}})
                continue
        
        if remaining <= Decimal('0'):
            events.append({'type': 'ORDER_FILLED', 'payload': {'order_id': order['order_id']}})
            continue
        # AMM for remaining
        f_i = compute_f_i(params_dyn, zeta, state)
        current_p = get_effective_p_yes(binary) if is_yes else get_effective_p_no(binary)
        if is_yes:
            if is_buy:
                X = buy_cost_yes(binary, remaining, params_dyn, f_i, dyn_params)
            else:
                X = sell_received_yes(binary, remaining, params_dyn, f_i, dyn_params)
        else:
            if is_buy:
                X = buy_cost_no(binary, remaining, params_dyn, f_i, dyn_params)
            else:
                X = sell_received_no(binary, remaining, params_dyn, f_i, dyn_params)
        # Compute new price after impact (penalty already applied in AMM cost functions)
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
        # Apply AMM fee (on trade value) - consistent with LOB fee transparency
        # AMM fees are separate from execution prices, maintaining user experience consistency
        fee = Decimal(params_dyn['f']) * remaining * effective_p
        # Create AMM fill
        fill: Fill = {
            'trade_id': str(uuid.uuid4()),  # Generate proper UUID for database compatibility
            'buy_user_id': order['user_id'] if is_buy else AMM_USER_ID,
            'sell_user_id': AMM_USER_ID if is_buy else order['user_id'],
            'outcome_i': i,
            'yes_no': order['yes_no'],
            'price': price_value(effective_p),
            'size': usdc_amount(remaining),
            'fee': usdc_amount(fee),
            'tick_id': 0,  # Placeholder
            'ts_ms': current_time,
            'fill_type': 'AMM',
            'price_yes': None,  # AMM fills have single price
            'price_no': None
        }
        fills.append(fill)
        
        # Add AMM fee to seigniorage for proper fee tracking (fixes audit issue #1)
        binary['seigniorage'] = float(Decimal(binary['seigniorage']) + fee)
        
        # Update token supplies to reflect the trade
        binary = get_binary(state, i)
        if is_yes:
            if is_buy:
                binary['q_yes'] = float(Decimal(binary['q_yes']) + remaining)
            else:
                binary['q_yes'] = float(Decimal(binary['q_yes']) - remaining)
        else:
            if is_buy:
                binary['q_no'] = float(Decimal(binary['q_no']) + remaining)
            else:
                binary['q_no'] = float(Decimal(binary['q_no']) - remaining)
        
        # Validate solvency after token supply update
        try:
            validate_solvency_invariant(binary)
        except ValueError as e:
            # Critical error - rollback the token supply change and reject order
            if is_yes:
                if is_buy:
                    binary['q_yes'] = float(Decimal(binary['q_yes']) - remaining)
                else:
                    binary['q_yes'] = float(Decimal(binary['q_yes']) + remaining)
            else:
                if is_buy:
                    binary['q_no'] = float(Decimal(binary['q_no']) - remaining)
                else:
                    binary['q_no'] = float(Decimal(binary['q_no']) + remaining)
            # Remove the fill that was just added
            fills.pop()
            events.append({'type': 'ORDER_REJECTED', 'payload': {'order_id': order['order_id'], 'reason': f'Solvency invariant violated: {e}'}})
            continue
            
        # Apply own impact
        apply_own_impact(state, i, X, is_buy, is_yes, f_i, params_dyn)
        # Apply cross impacts (diversions)
        apply_cross_impacts(state, i, X, is_buy, zeta, params_dyn)
        # Update subsidies across all binaries
        update_subsidies(state, params_dyn)
        
        # Validate solvency after impact and subsidy updates
        try:
            validate_solvency_invariant(binary)
        except ValueError as e:
            # This should not happen if the AMM math is correct, but catch it as a safety net
            raise ValueError(f"Solvency invariant violated after impact/subsidy updates for binary {i}: {e}")
        
        # Trigger auto-fills if enabled
        if params_dyn['af_enabled']:
            auto_fill_events = trigger_auto_fills(state, i, X, is_buy, params_dyn, current_time)
            
            # Convert auto-fill events to Fill objects for proper processing
            for af_event in auto_fill_events:
                if af_event['type'] in ['auto_fill_buy', 'auto_fill_sell']:
                    # Extract auto-fill details from event
                    af_is_buy = af_event['type'] == 'auto_fill_buy'
                    af_is_yes = af_event['is_yes']
                    af_delta = af_event['delta']
                    af_tick = af_event['tick']
                    af_price = price_value(Decimal(af_tick) * Decimal(params_dyn['tick_size']))
                    
                    # Create auto-fill as Fill object
                    af_fill: Fill = {
                        'trade_id': str(uuid.uuid4()),
                        'buy_user_id': AMM_USER_ID if af_is_buy else AMM_USER_ID,  # Auto-fills are AMM-like
                        'sell_user_id': AMM_USER_ID if not af_is_buy else AMM_USER_ID,
                        'outcome_i': af_event['binary_id'],
                        'yes_no': 'YES' if af_is_yes else 'NO',
                        'price': af_price,
                        'size': usdc_amount(af_delta),
                        'fee': usdc_amount(Decimal('0')),  # Auto-fills capture seigniorage, no separate fee
                        'tick_id': 0,  # Placeholder
                        'ts_ms': current_time,
                        'fill_type': 'AUTO_FILL',
                        'price_yes': None,  # Auto-fills have single price like AMM
                        'price_no': None
                    }
                    fills.append(af_fill)
            
            events.extend(auto_fill_events)
        events.append({'type': 'ORDER_FILLED', 'payload': {'order_id': order['order_id']}})

    # Validate engine state and solvency for all binaries at end of order processing
    try:
        validate_engine_state(state, params_dyn)
        # Explicit solvency validation for all binaries (per checklist item #2)
        for i in range(len(state['binaries'])):
            binary = get_binary(state, i)
            if binary['active']:
                validate_solvency_invariant(binary)
    except ValueError as e:
        # Critical error - the entire order batch should be considered failed
        raise ValueError(f"Engine state/solvency validation failed at end of apply_orders: {e}")

    return fills, state, events