import logging
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

logger = logging.getLogger(__name__)

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
            # CRITICAL FIX: For limit orders, commit collateral (size * limit_price) + gas fee per TDD Section 4.1
            # This replaces the previous estimation-based validation with actual collateral commitment
            commit_amount = size * limit_price
            total_required = commit_amount + gas_fee
            
            if user_balance < total_required:
                raise ValueError(f"Insufficient balance for limit order commitment. Required: {total_required:.4f} USDC (collateral + gas), Available: {user_balance:.4f} USDC")
            
            # Deduct committed amount + gas fee immediately
            final_balance = float(user_balance - total_required)
            update_user_balance(user_id, final_balance)
            logger.info(f"Committed {commit_amount:.4f} USDC collateral + {gas_fee:.4f} USDC gas fee for limit buy order")
        else:
            # CRITICAL FIX: For market buy orders, validate and deduct gas fee immediately
            current_p = Decimal(get_p_yes(binary) if yes_no == 'YES' else get_p_no(binary))
            
            # Compute dynamic parameters for proper AMM integration
            from app.engine.impact_functions import compute_dynamic_params
            current_time = get_current_ms()
            start_ts_ms = params.get('start_ts_ms', 0)
            current_time_sec = int((current_time - start_ts_ms) / 1000)
            dyn_params = compute_dynamic_params(params, current_time_sec)
            
            try:
                if yes_no == 'YES':
                    est_cost = buy_cost_yes(binary, size, params, Decimal('1.0'), dyn_params)  # f_i=1.0 for estimation
                else:
                    est_cost = buy_cost_no(binary, size, params, Decimal('1.0'), dyn_params)  # f_i=1.0 for estimation
                # Add conservative slippage buffer and gas fee
                total_cost = est_cost * Decimal('1.1') + gas_fee  # 10% slippage buffer
                
                if user_balance < total_cost:
                    raise ValueError(f"Insufficient balance for market order. Estimated cost: {total_cost:.4f} USDC, Available: {user_balance:.4f} USDC")
            except Exception as e:
                # Fallback to simple validation if AMM math fails
                validate_balance_buy(user_balance, size, current_p, gas_fee)
            
            # Deduct gas fee immediately (actual trading cost deducted later by batch runner)
            if user_balance < gas_fee:
                raise ValueError(f"Insufficient balance for gas fee. Required: {gas_fee:.4f} USDC")
            new_balance = float(user_balance - gas_fee)
            update_user_balance(user_id, new_balance)
            logger.info(f"Deducted {gas_fee:.4f} USDC gas fee for market buy order")
    else:
        # For sell orders, validate token holdings and handle collateral commitment
        user_tokens = Decimal(fetch_user_position(user_id, outcome_i, yes_no))
        validate_balance_sell(user_tokens, size)
        
        if order_type == 'LIMIT':
            # CRITICAL FIX: For limit sell orders, validate tokens but DON'T deduct them yet
            # Tokens will be deducted during actual execution in update_position_from_fill()
            # This eliminates the double deduction bug that was preventing position updates
            if user_tokens < size:
                raise ValueError(f"Insufficient tokens for limit sell order. Required: {size} tokens, Available: {user_tokens} tokens")
            if user_balance < gas_fee:
                raise ValueError(f"Insufficient balance for gas fee. Required: {gas_fee:.4f} USDC")
            
            # Only deduct gas fee from balance (tokens deducted at execution time)
            new_balance = float(user_balance - gas_fee)
            update_user_balance(user_id, new_balance)
            logger.info(f"Validated {size} {yes_no} tokens available + deducted {gas_fee:.4f} USDC gas fee for limit sell order")
        else:
            # For market sell orders: only deduct gas fee
            if user_balance < gas_fee:
                raise ValueError(f"Insufficient balance for gas fee. Required: {gas_fee:.4f} USDC")
            new_balance = float(user_balance - gas_fee)
            update_user_balance(user_id, new_balance)
            logger.info(f"Deducted {gas_fee:.4f} USDC gas fee for market sell order")

    # Create order dict for database insertion (order_id auto-generated by DB)
    order_dict = {
        'user_id': user_id,
        'outcome_i': outcome_i,
        'yes_no': yes_no,
        'type': order_type,
        'is_buy': is_buy,  # CRITICAL FIX: Store is_buy field for engine compatibility
        'size': float(size),  # Convert to float for database storage
        'limit_price': float(limit_price) if limit_price is not None else None,
        'max_slippage': float(max_slippage) if max_slippage is not None else None,
        'af_opt_in': af_opt_in,
        'status': 'OPEN',  # CRITICAL FIX: Set status to OPEN so fetch_open_orders() can find it
        'remaining': float(size),  # Initially set to full size; updated by batch runner
        'ts_ms': ts_ms
    }

    try:
        order_id = insert_order(order_dict)
        if not order_id:
            raise ValueError("Failed to insert order: No order ID returned")
        
        # Only publish event if insertion was successful
        publish_event('demo', 'ORDER_SUBMITTED', {'order_id': order_id, 'user_id': user_id})
        
        logger.info(f"Order {order_id} successfully inserted with status OPEN for user {user_id}")
        return order_id
        
    except Exception as e:
        logger.error(f"Order insertion failed for user {user_id}: {e}")
        raise ValueError(f"Failed to submit order: {str(e)}")

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
    orders = fetch_user_orders(user_id, 'OPEN')
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
        save_engine_state(state)
        
        # Refund the unfilled portion to user
        if refund_amount > 0:
            current_balance = Decimal(fetch_user_balance(user_id))
            new_balance = float(current_balance + refund_amount)
            update_user_balance(user_id, new_balance)
        
        # Update order status
        update_order_status(order_id, 'CANCELED')
        
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
    
    # Compute dynamic parameters for proper AMM integration
    from app.engine.impact_functions import compute_dynamic_params
    start_ts_ms = params.get('start_ts_ms', 0)
    current_time_sec = int((current_time - start_ts_ms) / 1000)  # Convert to seconds
    dyn_params = compute_dynamic_params(params, current_time_sec)
    
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
            # CRITICAL FIX: No fills possible - provide proper fallback estimation
            # Per TDD "no rejections" principle, estimate using pure AMM cost
            try:
                from app.engine.amm_math import buy_cost_yes, buy_cost_no, sell_received_yes, sell_received_no
                # Use f_i=1.0 for fallback estimation and compute dynamic parameters
                f_i_fallback = Decimal('1.0')
                if is_buy:
                    if yes_no == 'YES':
                        fallback_cost = buy_cost_yes(binary, size, params, f_i_fallback, dyn_params)
                    else:
                        fallback_cost = buy_cost_no(binary, size, params, f_i_fallback, dyn_params)
                else:
                    if yes_no == 'YES':
                        fallback_cost = sell_received_yes(binary, size, params, f_i_fallback, dyn_params)
                    else:
                        fallback_cost = sell_received_no(binary, size, params, f_i_fallback, dyn_params)
                
                # Add gas fee and calculate slippage from AMM price
                gas_fee = Decimal(str(params.get('gas_fee', 0)))
                total_cost = fallback_cost + gas_fee
                fallback_price = safe_divide(fallback_cost, size) if size > 0 else current_p
                fallback_slippage = safe_divide(abs(fallback_price - current_p), current_p)
                
                return {
                    'estimated_slippage': float(fallback_slippage), 
                    'would_reject': max_slippage is not None and fallback_slippage > Decimal(str(max_slippage)), 
                    'est_cost': float(fallback_cost),
                    'total_est_cost': float(total_cost),
                    'gas_fee': float(gas_fee),
                    'breakdown': {
                        'lob_fill': Decimal('0'),
                        'amm_fill': size,
                        'total_fee': Decimal('0'),
                        'effective_price': fallback_price,
                        'filled_amount': size
                    },
                    'fallback_mode': True
                }
            except Exception:
                # Ultimate fallback - return safe defaults
                return {
                    'estimated_slippage': float(Decimal('0.1')),  # 10% conservative estimate
                    'would_reject': True, 
                    'est_cost': float(size * current_p),
                    'total_est_cost': float(size * current_p + Decimal(str(params.get('gas_fee', 0)))),
                    'gas_fee': float(params.get('gas_fee', 0)),
                    'breakdown': {
                        'lob_fill': Decimal('0'),
                        'amm_fill': Decimal('0'),
                        'total_fee': Decimal('0'),
                        'effective_price': current_p,
                        'filled_amount': Decimal('0')
                    },
                    'error': 'Estimation failed - using conservative fallback'
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
        
        # CRITICAL FIX: Check if order would be rejected due to slippage
        # Per TDD Section 4.2: Use strict inequality (>) for rejection, not (>=)
        # This prevents rejection at exactly max_slippage boundary
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
            # Use f_i=1.0 for estimation since we don't have full engine context
            f_i_est = Decimal('1.0')
            if is_buy:
                if yes_no == 'YES':
                    est_cost = buy_cost_yes(binary, size, params, f_i_est, dyn_params)
                else:
                    est_cost = buy_cost_no(binary, size, params, f_i_est, dyn_params)
                effective_price = est_cost / size
                slippage = safe_divide(effective_price - current_p, current_p)
            else:
                if yes_no == 'YES':
                    est_received = sell_received_yes(binary, size, params, f_i_est, dyn_params)
                else:
                    est_received = sell_received_no(binary, size, params, f_i_est, dyn_params)
                effective_price = est_received / size
                slippage = safe_divide(current_p - effective_price, current_p)
            
            # Use consistent TDD-compliant slippage rejection (same as line 412)
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
            # Final fallback: provide asymptotic approximation per TDD requirements
            # Use conservative estimate based on current price and size impact
            conservative_slippage = min(Decimal('0.05'), size / Decimal('1000'))  # Max 5% or size-based
            conservative_price = current_p * (Decimal('1') + conservative_slippage) if is_buy else current_p * (Decimal('1') - conservative_slippage)
            conservative_cost = size * conservative_price
            
            # Include AMM fee in conservative estimate (fixes audit issue #1)
            conservative_fee = Decimal(params.get('f', 0.01)) * size * conservative_price
            conservative_total = conservative_cost + conservative_fee
            
            return {
                'estimated_slippage': float(conservative_slippage),
                'would_reject': False,  # TDD: no rejections, always provide estimate
                'est_cost': float(conservative_total),
                'breakdown': {
                    'lob_fill': Decimal('0'),
                    'amm_fill': size,
                    'total_fee': conservative_fee,
                    'effective_price': conservative_price
                },
                'error': f'Using conservative estimate: {str(fallback_error)}'
            }