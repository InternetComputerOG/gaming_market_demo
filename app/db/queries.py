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
    
    # Handle special timestamp conversion and wrap params in JSONB
    update_data = {}
    if 'start_ts_ms' in config_data:
        # Convert milliseconds to timestamp for database
        from datetime import datetime
        start_ts_ms = config_data['start_ts_ms']
        update_data['start_ts'] = datetime.fromtimestamp(start_ts_ms / 1000).isoformat()
    
    # Store the entire config_data as params JSONB
    update_data['params'] = config_data
    
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
def update_position(user_id: str, binary_id: int, q_yes: float, q_no: float) -> None:
    """Legacy function - updates both YES and NO positions for a user"""
    db = get_db()
    # Update YES position
    db.table('positions').upsert({
        'user_id': user_id,
        'outcome_i': binary_id,
        'yes_no': 'YES',
        'tokens': q_yes
    }).execute()
    # Update NO position
    db.table('positions').upsert({
        'user_id': user_id,
        'outcome_i': binary_id,
        'yes_no': 'NO', 
        'tokens': q_no
    }).execute()

def update_user_position(user_id: str, outcome_i: int, yes_no: str, tokens: float) -> None:
    """Update a single position entry for a user"""
    db = get_db()
    db.table('positions').upsert({
        'user_id': user_id,
        'outcome_i': outcome_i,
        'yes_no': yes_no,
        'tokens': tokens
    }).execute()

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

def fetch_open_orders(binary_id: int) -> List[Dict[str, Any]]:
    db = get_db()
    return db.table('orders').select('*').eq('outcome_i', binary_id).eq('status', 'OPEN').execute().data

def fetch_user_orders(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch orders for a specific user, optionally filtered by status"""
    db = get_db()
    query = db.table('orders').select('*').eq('user_id', user_id)
    if status:
        query = query.eq('status', status)
    return query.execute().data

def update_order_status(order_id: str, status: str, filled_qty: Optional[float] = None) -> None:
    db = get_db()
    update_data = {'status': status}
    if filled_qty is not None:
        update_data['filled_qty'] = filled_qty
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
    db = get_db()
    db.table('events').insert(events).execute()

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