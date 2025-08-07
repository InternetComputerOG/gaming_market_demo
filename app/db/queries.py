from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from supabase import Client
from app.config import get_supabase_client

# Assuming EngineState and EngineParams TypedDicts based on TDD/impl
class EngineParams(TypedDict):
    num_binaries: int
    fee_rate: float
    # Add other params as per TDD

class EngineState(TypedDict):
    params: EngineParams
    binaries: List[Dict[str, Any]]  # e.g., {'v': float, 'l': float, 'q_yes': float, ...}
    total_collateral: float
    # Add other state fields as per TDD

def get_db() -> Client:
    return get_supabase_client()

# Config queries
def load_config() -> Dict[str, Any]:
    db = get_db()
    result = db.table('config').select('*').limit(1).execute()
    if result.data:
        config = result.data[0]
        config['params'] = config.get('params', {})  # JSONB
        return config
    return {}

def update_config(config_data: Dict[str, Any]) -> None:
    db = get_db()
    # Try to update existing config, or insert if none exists
    existing = db.table('config').select('config_id').limit(1).execute()
    
    # Handle special timestamp conversion and store individual fields
    update_data = {}
    
    # Define fields that exist in the config table schema
    # Only store fields that actually exist in the database
    # Based on errors: start_ts_ms, current_round don't exist as columns
    supported_config_fields = {'status', 'params', 'start_ts', 'engine_state'}
    
    # Store individual config fields at the top level (only supported ones)
    for key, value in config_data.items():
        if key == 'start_ts_ms':
            # Convert milliseconds to timestamp for database (start_ts column exists)
            # But store raw milliseconds in params since start_ts_ms column doesn't exist
            from datetime import datetime
            update_data['start_ts'] = datetime.fromtimestamp(value / 1000).isoformat()
            # Don't store start_ts_ms at top level - it will be stored in params below
        elif key == 'params':
            # Store params as JSONB, but merge with existing params to preserve values
            if 'params' not in update_data:
                # Load existing params from database to merge
                try:
                    existing_config = load_config()
                    existing_params = existing_config.get('params', {})
                    # Merge existing params with new params (new params override existing)
                    merged_params = {**existing_params, **value}
                    update_data['params'] = merged_params
                except:
                    # If loading fails, just use the new params
                    update_data['params'] = value
            else:
                # Merge with params already in update_data
                existing_params = update_data['params'] if isinstance(update_data['params'], dict) else {}
                merged_params = {**existing_params, **value}
                update_data['params'] = merged_params
        elif key in supported_config_fields:
            # Store other supported fields directly (status, etc.)
            update_data[key] = value
        else:
            # Store unsupported fields in params instead
            if 'params' not in update_data:
                update_data['params'] = {}
            if isinstance(update_data['params'], dict):
                update_data['params'][key] = value
            else:
                # If params is not a dict, create a new dict with the existing params and new field
                existing_params = update_data['params'] if update_data['params'] else {}
                update_data['params'] = {**existing_params, key: value}
    
    # Debug: Print what we're storing
    print(f"update_config storing: {update_data}")
    
    if existing.data:
        # Update existing config
        config_id = existing.data[0]['config_id']
        db.table('config').update(update_data).eq('config_id', config_id).execute()
    else:
        # Insert new config
        db.table('config').insert(update_data).execute()

def get_current_config() -> Dict[str, Any]:
    """Alias for load_config for compatibility"""
    return load_config()

# Users queries
def insert_user(user_id: str, display_name: str, balance: float) -> None:
    db = get_db()
    db.table('users').insert({
        'user_id': user_id,
        'display_name': display_name,
        'balance': balance
    }).execute()

def fetch_user_balance(user_id: str) -> float:
    """Fetch the current balance for a user"""
    db = get_db()
    result = db.table('users').select('balance').eq('user_id', user_id).execute()
    if result.data:
        return float(result.data[0]['balance'])
    return 0.0

def update_user_balance(user_id: str, new_balance: float) -> None:
    """Update a user's balance"""
    db = get_db()
    db.table('users').update({'balance': new_balance}).eq('user_id', user_id).execute()

def fetch_users() -> List[Dict[str, Any]]:
    db = get_db()
    result = db.table('users').select('*').execute()
    return result.data

# Positions queries
def update_position(user_id: str, outcome_i: int, yes_no: str, tokens: float, trade_count: int) -> None:
    """Legacy function for updating positions with trade count - uses same upsert approach as update_user_position"""
    db = get_db()
    
    try:
        # Use same upsert approach as update_user_position for consistency
        db.table('positions').upsert({
            'user_id': user_id,
            'outcome_i': outcome_i,
            'yes_no': yes_no,
            'tokens': tokens,
            'trade_count': trade_count,
            'updated_at': 'now()'
        }, on_conflict='user_id,outcome_i,yes_no').execute()
        
    except Exception as e:
        print(f"Error in update_position: {e}")
        raise e

def update_user_position(user_id: str, outcome_i: int, yes_no: str, tokens: float) -> None:
    """Update a single position entry for a user, ensuring only one record per (user_id, outcome_i, yes_no)"""
    db = get_db()
    
    # Now that the unique constraint has been applied to the database,
    # we can use proper upsert with conflict resolution
    try:
        # Use upsert with the unique constraint columns as conflict target
        # This ensures atomic operation and prevents duplicate records
        db.table('positions').upsert({
            'user_id': user_id,
            'outcome_i': outcome_i,
            'yes_no': yes_no,
            'tokens': tokens,
            'updated_at': 'now()'
        }, on_conflict='user_id,outcome_i,yes_no').execute()
        
    except Exception as e:
        print(f"Error in update_user_position: {e}")
        raise e

def fetch_user_position(user_id: str, outcome_i: int, yes_no: str) -> float:
    """Fetch current token amount for a specific user position"""
    db = get_db()
    result = db.table('positions').select('tokens').eq('user_id', user_id).eq('outcome_i', outcome_i).eq('yes_no', yes_no).execute()
    if result.data:
        return float(result.data[0]['tokens'])
    return 0.0

def fetch_positions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    query = db.table('positions').select('*')
    if user_id:
        query = query.eq('user_id', user_id)
    return query.execute().data

# Orders queries
def insert_order(order: Dict[str, Any]) -> str:
    db = get_db()
    result = db.table('orders').insert(order).execute()
    return result.data[0]['order_id'] if result.data else ''

def fetch_open_orders(binary_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch open orders. If binary_id is None, fetch all open orders globally.
    Orders are sorted by ts_ms for deterministic processing as required by the engine."""
    db = get_db()
    query = db.table('orders').select('*').eq('status', 'OPEN')
    
    # If binary_id is specified, filter by outcome
    if binary_id is not None:
        query = query.eq('outcome_i', binary_id)
    
    # Sort by timestamp for deterministic processing (required by engine)
    query = query.order('ts_ms')
    
    orders = query.execute().data
    
    # Log for debugging
    if orders:
        print(f"fetch_open_orders: Found {len(orders)} open orders")
        for order in orders[:3]:  # Log first 3 orders for debugging
            print(f"  Order {order['order_id']}: {order['type']} {order['yes_no']} size={order['size']} user={order['user_id']}")
    else:
        print("fetch_open_orders: No open orders found")
    
    return orders

def fetch_user_orders(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch orders for a specific user, optionally filtered by status"""
    db = get_db()
    query = db.table('orders').select('*').eq('user_id', user_id)
    if status:
        query = query.eq('status', status)
    return query.execute().data

def fetch_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single order by order_id for refund processing"""
    db = get_db()
    result = db.table('orders').select('*').eq('order_id', order_id).execute()
    return result.data[0] if result.data else None

def update_order_status(order_id: str, status: str, filled_qty: Optional[float] = None, rejection_reason: Optional[str] = None) -> None:
    db = get_db()
    update_data = {'status': status}
    if filled_qty is not None:
        update_data['filled_qty'] = filled_qty
    if rejection_reason is not None:
        update_data['rejection_reason'] = rejection_reason
    db.table('orders').update(update_data).eq('order_id', order_id).execute()

# LOB pools queries
def insert_or_update_pool(pool: Dict[str, Any]) -> None:
    db = get_db()
    db.table('lob_pools').upsert(pool).execute()

def fetch_pools(binary_id: int) -> List[Dict[str, Any]]:
    db = get_db()
    return db.table('lob_pools').select('*').eq('outcome_i', binary_id).execute().data

# Trades queries
def insert_trades_batch(trades: List[Dict[str, Any]]) -> None:
    db = get_db()
    db.table('trades').insert(trades).execute()

# Ticks queries
def insert_tick(tick_data: Dict[str, Any]) -> int:
    db = get_db()
    result = db.table('ticks').insert(tick_data).execute()
    return result.data[0]['tick_id'] if result.data else 0

def get_current_tick() -> Dict[str, Any]:
    db = get_db()
    result = db.table('ticks').select('*').order('tick_id', desc=True).limit(1).execute()
    return result.data[0] if result.data else {}

# Events queries
def insert_events(events: List[Dict[str, Any]]) -> None:
    """Insert events into the database, filtering out unsupported fields."""
    db = get_db()
    
    # Define the supported fields for the events table schema
    # Based on schema.sql lines 134-141: event_id, type, payload, ts_ms are all supported
    # Fixed: Added 'payload' and 'ts_ms' which are required NOT NULL fields in schema
    supported_fields = {'type', 'outcome_i', 'event_id', 'payload', 'ts_ms'}
    
    # Filter events to only include supported fields
    filtered_events = []
    for event in events:
        filtered_event = {k: v for k, v in event.items() if k in supported_fields}
        # Ensure required fields are present
        if 'type' not in filtered_event:
            print(f"Warning: Event missing required 'type' field: {event}")
            continue
        if 'payload' not in filtered_event:
            # Provide default empty payload if missing
            filtered_event['payload'] = {}
        if 'ts_ms' not in filtered_event:
            # Provide current timestamp if missing
            from app.utils import get_current_ms
            filtered_event['ts_ms'] = get_current_ms()
        filtered_events.append(filtered_event)
    
    if filtered_events:
        try:
            db.table('events').insert(filtered_events).execute()
        except Exception as e:
            # Log the error but don't crash the resolution process
            print(f"Warning: Failed to insert events: {e}")
            print(f"Events data: {filtered_events}")

# Metrics queries
def update_metrics(metrics: Dict[str, Any]) -> None:
    db = get_db()
    db.table('metrics').upsert(metrics).execute()

# State queries
def fetch_engine_state() -> EngineState:
    db = get_db()
    result = db.table('config').select('engine_state').limit(1).execute()  # Get first config record
    if result.data and result.data[0].get('engine_state'):
        return result.data[0]['engine_state']  # JSONB to dict
    return {'params': {}, 'binaries': [], 'total_collateral': 0.0}  # Default

def save_engine_state(state: EngineState) -> None:
    db = get_db()
    # Get the first config record and update it
    config_result = db.table('config').select('config_id').limit(1).execute()
    if config_result.data:
        config_id = config_result.data[0]['config_id']
        db.table('config').update({'engine_state': state}).eq('config_id', config_id).execute()

# Transaction wrapper example for atomic ops
def atomic_transaction(queries: List[str]) -> None:
    db = get_db()
    # For simplicity, execute raw SQL with BEGIN/COMMIT
    sql = 'BEGIN;\n' + ';\n'.join(queries) + ';\nCOMMIT;'
    db.sql(sql).execute()