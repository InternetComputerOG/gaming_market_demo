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
    result = db.table('config').select('*').eq('id', 1).execute()
    if result.data:
        config = result.data[0]
        config['params'] = config.get('params', {})  # JSONB
        return config
    return {}

def update_config(params: Dict[str, Any]) -> None:
    db = get_db()
    db.table('config').update({'params': params}).eq('id', 1).execute()

# Users queries
def insert_user(user_id: str, username: str, balance: float) -> None:
    db = get_db()
    db.table('users').insert({
        'user_id': user_id,
        'username': username,
        'balance': balance
    }).execute()

def fetch_users() -> List[Dict[str, Any]]:
    db = get_db()
    result = db.table('users').select('*').execute()
    return result.data

# Positions queries
def update_position(user_id: str, binary_id: int, q_yes: float, q_no: float) -> None:
    db = get_db()
    db.table('positions').upsert({
        'user_id': user_id,
        'binary_id': binary_id,
        'q_yes': q_yes,
        'q_no': q_no
    }).execute()

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
    return db.table('orders').select('*').eq('binary_id', binary_id).eq('status', 'open').order('ts_ms').execute().data

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
    return db.table('lob_pools').select('*').eq('binary_id', binary_id).execute().data

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
    result = db.table('config').select('state').eq('id', 1).execute()  # Assuming state in config
    if result.data:
        return result.data[0]['state']  # JSONB to dict
    return {'params': {}, 'binaries': [], 'total_collateral': 0.0}  # Default

def save_engine_state(state: EngineState) -> None:
    db = get_db()
    db.table('config').update({'state': state}).eq('id', 1).execute()

# Transaction wrapper example for atomic ops
def atomic_transaction(queries: List[str]) -> None:
    db = get_db()
    # For simplicity, execute raw SQL with BEGIN/COMMIT
    sql = 'BEGIN;\n' + ';\n'.join(queries) + ';\nCOMMIT;'
    db.sql(sql).execute()