import time
import threading
from decimal import Decimal, getcontext
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from app.config import get_supabase_client
from app.utils import get_current_ms, safe_divide
from app.db.queries import (
    fetch_engine_state,
    save_engine_state,
    insert_trades_batch,
    update_order_status,
    fetch_open_orders,
    insert_events,
    get_current_tick,
    load_config,
    insert_tick as db_insert_tick,
    update_metrics,
)
from app.engine.orders import apply_orders, Fill, Order
from app.engine.state import EngineState
from app.engine.params import EngineParams
from app.services.ticks import compute_summary, create_tick
from app.services.realtime import publish_tick_update
from app.services.positions import update_position_from_fill

# Global thread management
_batch_runner_thread: Optional[threading.Thread] = None
_batch_runner_active = False
_batch_runner_stats = {
    'last_tick_time': None,
    'total_ticks': 0,
    'total_orders_processed': 0,
    'total_fills_generated': 0,
    'last_error': None,
    'error_count': 0,
    'thread_restarts': 0
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_decimals_to_floats(obj):
    """Recursively convert Decimal objects to floats for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals_to_floats(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_floats(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_decimals_to_floats(item) for item in obj)
    else:
        return obj

def get_status_and_config() -> Dict[str, Any]:
    config = load_config()
    return config

def run_tick():
    """Execute a single tick of order processing with comprehensive error handling and logging."""
    global _batch_runner_stats
    
    try:
        client = get_supabase_client()
        config = get_status_and_config()
        
        # Check if trading is active
        if config['status'] not in ['RUNNING'] or config.get('frozen', False):
            logger.debug(f"Skipping tick - status: {config['status']}, frozen: {config.get('frozen', False)}")
            return

        # Get start_ts_ms from params (where it's actually stored)
        params = config.get('params', {})
        start_ts_ms = params.get('start_ts_ms', 0)
        current_ms = get_current_ms()
        current_time_sec = safe_divide(Decimal(current_ms - start_ts_ms), Decimal(1000))  # seconds for interpolation

        # Fetch next tick_id (max +1)
        current_tick_data = get_current_tick()
        tick_id = (current_tick_data.get('tick_id', 0) if current_tick_data else 0) + 1

        # Fetch all open orders, sorted by ts_ms
        db_orders = fetch_open_orders(None)  # Fetch from database
        logger.info(f"Tick {tick_id}: Processing {len(db_orders)} open orders")
        
        # CRITICAL FIX: Transform database orders to engine-compatible format
        new_orders: List[Order] = []
        for db_order in db_orders:
            try:
                # Convert database order to engine Order format
                engine_order: Order = {
                    'order_id': db_order['order_id'],
                    'user_id': db_order['user_id'],
                    'outcome_i': db_order['outcome_i'],
                    'yes_no': db_order['yes_no'],
                    'type': db_order['type'],
                    'is_buy': db_order['is_buy'],  # Use actual stored is_buy value from database
                    'size': Decimal(str(db_order['size'])),
                    'limit_price': Decimal(str(db_order['limit_price'])) if db_order.get('limit_price') else None,
                    'max_slippage': Decimal(str(db_order['max_slippage'])) if db_order.get('max_slippage') else None,
                    'af_opt_in': db_order.get('af_opt_in', False),
                    'ts_ms': db_order['ts_ms']
                }
                
                new_orders.append(engine_order)
                logger.debug(f"Transformed order {db_order['order_id']}: {db_order['type']} {db_order['yes_no']} size={db_order['size']} -> is_buy={engine_order['is_buy']}")
                
            except Exception as e:
                logger.error(f"Error transforming order {db_order.get('order_id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Tick {tick_id}: Transformed {len(new_orders)} orders for engine processing")
        
        # Update stats
        _batch_runner_stats['total_orders_processed'] += len(new_orders)

        state: EngineState = fetch_engine_state()
        params: EngineParams = config['params']  # TypedDict

        fills: List[Fill]
        new_state: EngineState
        events: List[Dict[str, Any]]
        
        # Apply orders through engine
        if new_orders:  # Only process if we have valid orders
            fills, new_state, events = apply_orders(state, new_orders, params, int(current_time_sec))
        else:
            # No valid orders to process
            fills, new_state, events = [], state, []
        logger.info(f"Tick {tick_id}: Generated {len(fills)} fills from {len(new_orders)} orders")
        
        # Update stats
        _batch_runner_stats['total_fills_generated'] += len(fills)

        # Process DB updates - Convert Decimal types to floats for JSON serialization
        if fills:
            # Convert fills to JSON-serializable format using utility function
            serializable_fills = convert_decimals_to_floats(fills)
            insert_trades_batch(serializable_fills)
            logger.info(f"Tick {tick_id}: Inserted {len(fills)} trades to database")

        # Update orders from events (e.g., ACCEPTED/REJECTED/FILLED)
        orders_updated = 0
        for event in events:
            if event['type'] in ['ORDER_ACCEPTED', 'ORDER_FILLED', 'ORDER_PARTIAL', 'ORDER_REJECTED']:
                # Engine events have order_id inside payload
                payload = event.get('payload', {})
                order_id = payload.get('order_id')
                if not order_id:
                    logger.warning(f"Event {event['type']} missing order_id in payload: {event}")
                    continue
                    
                # Map event type to order status
                status_mapping = {
                    'ORDER_ACCEPTED': 'OPEN',
                    'ORDER_FILLED': 'FILLED', 
                    'ORDER_PARTIAL': 'PARTIAL',
                    'ORDER_REJECTED': 'REJECTED'
                }
                status = status_mapping.get(event['type'], 'OPEN')
                
                filled_qty = payload.get('filled_qty')
                # Convert Decimal to float if needed
                filled_qty = convert_decimals_to_floats(filled_qty)
                update_order_status(order_id, status, filled_qty)
                orders_updated += 1
        
        if orders_updated > 0:
            logger.info(f"Tick {tick_id}: Updated {orders_updated} order statuses")

        # Update positions and balances from fills using the centralized service function
        # This ensures both user positions AND engine state are updated consistently per TDD Phase 3.2
        positions_updated = 0
        for fill in fills:
            try:
                # Use the properly implemented service function that handles:
                # - Both buyer and seller position updates
                # - Engine state token quantity updates (q_yes, q_no)
                # - Proper fee handling per TDD specifications
                # - Balance consistency and validation
                # Convert fill to JSON-serializable format before position update
                serializable_fill = convert_decimals_to_floats(fill)
                update_position_from_fill(serializable_fill, new_state)
                positions_updated += 1
            except Exception as e:
                logger.error(f"Error updating position from fill {fill['trade_id']}: {e}")
                _batch_runner_stats['error_count'] += 1
                # Continue processing other fills rather than failing the entire batch
        
        if positions_updated > 0:
            logger.info(f"Tick {tick_id}: Updated {positions_updated} user positions")

        # lob_pools updated in state, saved below - Convert Decimals for JSON serialization
        serializable_state = convert_decimals_to_floats(new_state)
        save_engine_state(serializable_state)

        # Compute summary and create tick
        summary = compute_summary(new_state, fills)
        create_tick(new_state, fills, tick_id)  # Inserts tick and updates metrics

        insert_events(events)

        # Publish realtime updates
        publish_tick_update(tick_id)
        
        # Update stats
        _batch_runner_stats['last_tick_time'] = datetime.now()
        _batch_runner_stats['total_ticks'] += 1
        _batch_runner_stats['last_error'] = None  # Clear last error on successful tick
        
        logger.info(f"Tick {tick_id} completed successfully - Orders: {len(new_orders)}, Fills: {len(fills)}, Events: {len(events)}")
        
    except Exception as e:
        logger.error(f"Error in run_tick: {e}")
        _batch_runner_stats['last_error'] = str(e)
        _batch_runner_stats['error_count'] += 1
        # Don't re-raise - let the batch runner continue

def get_batch_runner_stats() -> Dict[str, Any]:
    """Get current batch runner statistics and health status."""
    global _batch_runner_stats, _batch_runner_active, _batch_runner_thread
    
    stats = _batch_runner_stats.copy()
    stats['is_active'] = _batch_runner_active
    stats['thread_alive'] = _batch_runner_thread.is_alive() if _batch_runner_thread else False
    stats['thread_id'] = _batch_runner_thread.ident if _batch_runner_thread else None
    
    return stats

def stop_batch_runner():
    """Stop the batch runner thread."""
    global _batch_runner_active
    logger.info("Stopping batch runner...")
    _batch_runner_active = False

def is_batch_runner_healthy() -> bool:
    """Check if batch runner is healthy and processing orders."""
    global _batch_runner_stats, _batch_runner_active, _batch_runner_thread
    
    if not _batch_runner_active:
        return False
        
    if not _batch_runner_thread or not _batch_runner_thread.is_alive():
        return False
        
    # Check if we've had a tick in the last 30 seconds
    if _batch_runner_stats['last_tick_time']:
        time_since_last_tick = (datetime.now() - _batch_runner_stats['last_tick_time']).total_seconds()
        if time_since_last_tick > 30:
            logger.warning(f"Batch runner unhealthy: {time_since_last_tick:.1f}s since last tick")
            return False
    
    return True

def restart_batch_runner_if_needed():
    """Restart batch runner if it's not healthy."""
    if not is_batch_runner_healthy():
        logger.warning("Batch runner is unhealthy, restarting...")
        stop_batch_runner()
        start_batch_runner()
        return True
    return False

def start_batch_runner():
    """Start the batch runner with robust thread management and health monitoring."""
    global _batch_runner_thread, _batch_runner_active, _batch_runner_stats
    
    # Stop existing runner if running
    if _batch_runner_active:
        logger.info("Stopping existing batch runner before starting new one")
        stop_batch_runner()
        time.sleep(1)  # Give it time to stop
    
    config = get_status_and_config()
    interval_ms = config['params'].get('batch_interval_ms', 1000)
    interval_sec = interval_ms / 1000.0
    
    logger.info(f"Starting batch runner with {interval_ms}ms interval")
    
    def runner_loop():
        """Main batch runner loop with error recovery."""
        global _batch_runner_active
        
        _batch_runner_active = True
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        logger.info("Batch runner thread started")
        
        while _batch_runner_active:
            try:
                # Check if we should still be running
                current_config = get_status_and_config()
                if current_config['status'] not in ['RUNNING', 'FROZEN']:
                    logger.info(f"Stopping batch runner - demo status: {current_config['status']}")
                    break
                
                # Run a tick
                run_tick()
                consecutive_errors = 0  # Reset error counter on success
                
                # Sleep for the configured interval
                time.sleep(interval_sec)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Batch runner error #{consecutive_errors}: {e}")
                _batch_runner_stats['error_count'] += 1
                _batch_runner_stats['last_error'] = str(e)
                
                # If too many consecutive errors, stop the runner
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping batch runner")
                    break
                
                # Exponential backoff for errors
                error_sleep = min(30, 2 ** consecutive_errors)
                logger.info(f"Sleeping {error_sleep}s before retry")
                time.sleep(error_sleep)
        
        _batch_runner_active = False
        logger.info("Batch runner thread stopped")
    
    # Create and start the thread
    _batch_runner_thread = threading.Thread(
        target=runner_loop, 
        daemon=True,
        name="BatchRunner"
    )
    
    _batch_runner_thread.start()
    _batch_runner_stats['thread_restarts'] += 1
    
    logger.info(f"Batch runner started successfully (thread ID: {_batch_runner_thread.ident})")
    
    # Verify thread started
    time.sleep(0.1)
    if not _batch_runner_thread.is_alive():
        logger.error("Failed to start batch runner thread!")
        raise RuntimeError("Batch runner thread failed to start")