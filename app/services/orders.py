from decimal import Decimal
from typing import Dict, Any, List, Optional
from typing_extensions import TypedDict

from app.config import get_supabase_client
from app.db.queries import (
    fetch_engine_state, update_user_balance, insert_order, update_order_status, 
    fetch_user_orders, get_current_config, fetch_user_balance, fetch_user_position,
    save_engine_state
)
from app.engine.orders import Order as EngineOrder, apply_orders
from app.engine.params import EngineParams
from app.engine.state import EngineState, get_p_yes, get_p_no
from app.engine.lob_matching import cancel_from_pool, match_market_order
from app.engine.amm_math import buy_cost_yes, buy_cost_no, sell_received_yes, sell_received_no
from app.utils import (
    usdc_amount, price_value, validate_size, validate_price, validate_balance_buy, 
    validate_balance_sell, get_current_ms, safe_divide, validate_limit_price_bounds, 
    validate_binary_state
)
from app.services.realtime import publish_event

class Order(TypedDict):
    order_id: str
    user_id: str
    outcome_i: int
    yes_no: str
    type: str
    is_buy: bool
    size: Decimal
    limit_price: Optional[Decimal]
    max_slippage: Optional[Decimal]
    af_opt_in: bool
    ts_ms: int

def submit_order(user_id: str, order_data: Dict[str, Any]) -> str:
    client = get_supabase_client()
    config = get_current_config()
    params: EngineParams = config['params']
    gas_fee = Decimal(params['gas_fee'])

    size = usdc_amount(order_data['size'])
    validate_size(size)

    is_buy = order_data['is_buy']
    yes_no = order_data['yes_no']
    outcome_i = order_data['outcome_i']
    order_type = order_data['type']
    af_opt_in = order_data['af_opt_in']
    ts_ms = get_current_ms()

    if config['status'] in ['FROZEN', 'RESOLVED']:
        raise ValueError("Trading is currently frozen or resolved")

    if order_type == 'LIMIT':
        limit_price = price_value(order_data['limit_price'])
        validate_price(limit_price)
        
        # Validate limit price bounds per TDD requirements
        try:
            validate_limit_price_bounds(limit_price, Decimal(str(params['p_min'])), Decimal(str(params['p_max'])))
        except ValueError as e:
            raise ValueError(f"Limit price validation failed: {e}")
        
        max_slippage = None
    else:
        limit_price = None
        max_slippage = Decimal(order_data.get('max_slippage', '0.05'))

    # Enhanced balance validation with new fee structure
    state: EngineState = fetch_engine_state()
    binary = state['binaries'][outcome_i]
    
    # Validate binary state before order submission
    try:
        validate_binary_state(binary, params)
    except ValueError as e:
        raise ValueError(f"Binary state validation failed: {e}")
    
    # Enhanced balance checks for limit orders with new fee structure
    user_balance = Decimal(fetch_user_balance(user_id))
    
    if is_buy:
        if order_type == 'LIMIT':
            # For limit orders, user pays exactly their limit price + fees
            trading_cost = size * limit_price
            # Estimate trading fee based on limit price (conservative)
            est_trading_fee = params['f_match'] * size * limit_price / Decimal('2')
            total_cost = trading_cost + est_trading_fee + gas_fee
            
            if user_balance < total_cost:
                raise ValueError(f"Insufficient balance. Required: {total_cost:.4f} USDC, Available: {user_balance:.4f} USDC")
        else:
            # For market orders, estimate cost with slippage
            current_p = Decimal(get_p_yes(binary) if yes_no == 'YES' else get_p_no(binary))
            try:
                if yes_no == 'YES':
                    est_cost = buy_cost_yes(binary, size, params)
                else:
                    est_cost = buy_cost_no(binary, size, params)
                # Add conservative slippage buffer and gas fee
                total_cost = est_cost * Decimal('1.1') + gas_fee  # 10% slippage buffer
                
                if user_balance < total_cost:
                    raise ValueError(f"Insufficient balance for market order. Estimated cost: {total_cost:.4f} USDC, Available: {user_balance:.4f} USDC")
            except Exception as e:
                # Fallback to simple validation if AMM math fails
                validate_balance_buy(user_balance, size, current_p, gas_fee)
    else:
        # For sell orders, validate token holdings
        user_tokens = Decimal(fetch_user_position(user_id, outcome_i, yes_no))
        validate_balance_sell(user_tokens, size)

    # Deduct gas_fee regardless of later rejection
    new_balance = float(user_balance - gas_fee)
    update_user_balance(user_id, new_balance)

    order: Order = {
        'user_id': user_id,
        'outcome_i': outcome_i,
        'yes_no': yes_no,
        'type': order_type,
        'is_buy': is_buy,  # CRITICAL FIX: Store is_buy field for engine compatibility
        'size': float(size),
        'limit_price': float(limit_price) if limit_price is not None else None,
        'max_slippage': float(max_slippage) if max_slippage is not None else None,
        'af_opt_in': af_opt_in,
        'status': 'OPEN',  # CRITICAL FIX: Set status to OPEN so fetch_open_orders() can find it
        'remaining': float(size),  # Initially set to full size; updated by batch runner
        'ts_ms': ts_ms
    }

    order_id = insert_order(order)
    publish_event('demo', 'ORDER_SUBMITTED', {'order_id': order_id, 'user_id': user_id})

    return order_id

def cancel_order(order_id: str, user_id: str) -> None:
    """Cancel a limit order and refund unfilled portion to user.
    
    Args:
        order_id: The order ID to cancel
        user_id: The user requesting cancellation
        
    Raises:
        ValueError: If order doesn't exist, user doesn't own it, or order not cancellable
    """
    client = get_supabase_client()
    
    # Fetch order details - need to get from database
    orders = fetch_user_orders(client, user_id, 'OPEN')
    order = None
    for o in orders:
        if o['order_id'] == order_id:
            order = o
            break
    
    if not order:
        raise ValueError("Order not found or not owned by user")
    
    if order['status'] != 'OPEN':
        raise ValueError(f"Cannot cancel order with status: {order['status']}")
    
    # Only limit orders can be cancelled from LOB pools
    if order['type'] != 'LIMIT':
        raise ValueError("Only limit orders can be cancelled")

    # Get current state and config for cancellation
    state: EngineState = fetch_engine_state()
    config = get_current_config()
    params: EngineParams = config['params']
    
    try:
        # Cancel from LOB pool and get refund amount
        refund_amount = cancel_from_pool(
            state, 
            order['outcome_i'], 
            order['yes_no'], 
            order['is_buy'], 
            order['limit_price'], 
            user_id, 
            order['af_opt_in']
        )
        
        # Save updated engine state
        save_engine_state(client, state)
        
        # Refund the unfilled portion to user
        if refund_amount > 0:
            current_balance = Decimal(fetch_user_balance(user_id))
            new_balance = float(current_balance + refund_amount)
            update_user_balance(user_id, new_balance)
        
        # Update order status
        update_order_status(client, order_id, 'CANCELED')
        
        # Publish cancellation event
        publish_event('demo', 'ORDER_CANCELED', {
            'order_id': order_id, 
            'user_id': user_id,
            'refund_amount': float(refund_amount)
        })
        
    except Exception as e:
        raise ValueError(f"Failed to cancel order: {str(e)}")

def get_user_orders(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    return fetch_user_orders(user_id, status)

def estimate_slippage(outcome_i: int, yes_no: str, size: Decimal, is_buy: bool, max_slippage: Optional[Decimal]) -> Dict[str, Any]:
    """Estimate slippage for market orders interacting with LOB and AMM.
    
    This function simulates order execution to provide accurate slippage estimates
    that account for both LOB cross-matching and AMM fallback execution.
    
    Args:
        outcome_i: Binary outcome index
        yes_no: 'YES' or 'NO' token type
        size: Order size in tokens
        is_buy: True for buy orders, False for sell orders
        max_slippage: Maximum acceptable slippage (optional)
        
    Returns:
        Dict containing estimated_slippage, would_reject, est_cost, and breakdown
    """
    client = get_supabase_client()
    
    # Get current state and config
    state: EngineState = fetch_engine_state()
    config = get_current_config()
    params: EngineParams = config['params']
    current_time = get_current_ms()
    
    # Get current price for slippage calculation
    binary = state['binaries'][outcome_i]
    from app.engine.state import get_p_yes, get_p_no
    current_p = Decimal(get_p_yes(binary) if yes_no == 'YES' else get_p_no(binary))
    
    # Create simulation order
    sim_order: EngineOrder = {
        'order_id': 'sim',
        'user_id': 'sim',
        'outcome_i': outcome_i,
        'yes_no': yes_no,
        'type': 'MARKET',
        'is_buy': is_buy,
        'size': size,
        'limit_price': None,
        'max_slippage': max_slippage,
        'af_opt_in': True,
        'ts_ms': current_time
    }
    
    try:
        # Simulate order execution with LOB interaction
        import copy
        sim_state = copy.deepcopy(state)
        
        fills, new_state, _ = apply_orders(sim_state, [sim_order], params, current_time)
        
        if not fills:
            # No fills possible - likely insufficient liquidity or invalid order
            return {
                'estimated_slippage': Decimal('0'), 
                'would_reject': True, 
                'est_cost': Decimal('0'),
                'breakdown': {
                    'lob_fill': Decimal('0'),
                    'amm_fill': Decimal('0'),
                    'total_fee': Decimal('0'),
                    'effective_price': current_p
                },
                'error': 'No liquidity available'
            }
        
        # Calculate weighted average execution price and total cost
        total_filled = Decimal('0')
        total_cost = Decimal('0')
        total_fee = Decimal('0')
        lob_fill = Decimal('0')
        amm_fill = Decimal('0')
        
        for fill in fills:
            fill_size = Decimal(str(fill['size']))
            fill_price = Decimal(str(fill['price']))
            fill_fee = Decimal(str(fill.get('fee', 0)))
            
            total_filled += fill_size
            total_cost += fill_size * fill_price
            total_fee += fill_fee
            
            # Categorize fill source (LOB vs AMM)
            if fill.get('source') == 'lob':
                lob_fill += fill_size
            else:
                amm_fill += fill_size
        
        if total_filled == 0:
            effective_price = current_p
            slippage = Decimal('0')
        else:
            effective_price = total_cost / total_filled
            # Calculate slippage as percentage difference from current price
            if is_buy:
                slippage = safe_divide(effective_price - current_p, current_p)
            else:
                slippage = safe_divide(current_p - effective_price, current_p)
        
        # Check if order would be rejected due to slippage
        would_reject = max_slippage is not None and slippage > Decimal(str(max_slippage))
        
        # Calculate total estimated cost including fees
        est_total_cost = total_cost + total_fee
        
        # Include gas fee in total estimated cost per Implementation Plan requirements
        gas_fee = Decimal(str(params.get('gas_fee', 0)))
        total_est_cost = est_total_cost + gas_fee
        
        breakdown = {
            'lob_fill': lob_fill,
            'amm_fill': amm_fill,
            'total_fee': total_fee,
            'effective_price': effective_price,
            'filled_amount': total_filled
        }
        
        return {
            'estimated_slippage': float(slippage),
            'would_reject': would_reject,
            'est_cost': float(est_total_cost),
            'total_est_cost': float(total_est_cost),  # Include gas fee for UI display
            'gas_fee': float(gas_fee),
            'breakdown': breakdown
        }
        
    except Exception as e:
        # Fallback to simple estimation if simulation fails
        try:
            if is_buy:
                if yes_no == 'YES':
                    est_cost = buy_cost_yes(binary, size, params)
                else:
                    est_cost = buy_cost_no(binary, size, params)
                effective_price = est_cost / size
                slippage = safe_divide(effective_price - current_p, current_p)
            else:
                if yes_no == 'YES':
                    est_received = sell_received_yes(binary, size, params)
                else:
                    est_received = sell_received_no(binary, size, params)
                effective_price = est_received / size
                slippage = safe_divide(current_p - effective_price, current_p)
            
            would_reject = max_slippage is not None and slippage > Decimal(str(max_slippage))
            
            # Calculate fee as per TDD: fee = f * remaining * p_prime
            fee_fallback = Decimal(params.get('f', 0.01)) * size * effective_price
            total_cost_with_fee = (est_cost if is_buy else est_received) + fee_fallback
            
            return {
                'estimated_slippage': slippage,
                'would_reject': would_reject,
                'est_cost': total_cost_with_fee,
                'breakdown': {
                    'lob_fill': Decimal('0'),
                    'amm_fill': size,
                    'total_fee': fee_fallback,
                    'effective_price': effective_price
                },
                'fallback': True
            }
        except Exception as fallback_error:
            return {
                'estimated_slippage': Decimal('0'),
                'would_reject': True,
                'est_cost': Decimal('0'),
                'breakdown': {
                    'lob_fill': Decimal('0'),
                    'amm_fill': Decimal('0'),
                    'total_fee': Decimal('0'),
                    'effective_price': current_p
                },
                'error': f'Estimation failed: {str(fallback_error)}'
            }