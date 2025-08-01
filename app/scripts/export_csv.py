import pandas as pd
from typing import List, Dict
from decimal import Decimal
from supabase import Client
from app.config import get_supabase_client
from app.utils import safe_divide
from app.db.queries import load_config, fetch_users

def fetch_trades(client: Client) -> List[Dict[str, any]]:
    return client.table('trades').select('*').order('ts_ms').execute().data

def fetch_metrics(client: Client) -> List[Dict[str, any]]:
    return client.table('metrics').select('*').order('tick_id').execute().data

def export_trades_csv(filename: str) -> None:
    client = get_supabase_client()
    trades = fetch_trades(client)
    df = pd.DataFrame(trades)
    df.to_csv(filename, index=False, float_format='%.6f')

def export_config_csv(filename: str) -> None:
    config = load_config()
    params = config.get('params', {})
    df = pd.DataFrame([params])
    df.to_csv(filename, index=False, float_format='%.6f')

def export_metrics_csv(filename: str) -> None:
    client = get_supabase_client()
    metrics = fetch_metrics(client)
    df = pd.DataFrame(metrics)
    df.to_csv(filename, index=False, float_format='%.6f')

def export_rankings_csv(filename: str) -> None:
    client = get_supabase_client()
    config = load_config()
    params = config.get('params', {})
    starting_balance = Decimal(params.get('starting_balance', '0'))
    gas_fee = Decimal(params.get('gas_fee', '0'))
    users = fetch_users()
    rows = []
    for user in users:
        balance = Decimal(user.get('balance', '0'))
        trade_count = user.get('trade_count', 0)
        gas_cost = gas_fee * Decimal(trade_count)
        pnl = balance - starting_balance
        pct_gain_loss = safe_divide(pnl, starting_balance) * Decimal('100')
        rows.append({
            'display_name': user.get('display_name'),
            'final_usdc': float(balance),
            'pnl': float(pnl),
            'pct_gain_loss': float(pct_gain_loss),
            'trade_count': trade_count,
            'gas_costs': float(gas_cost)
        })
    df = pd.DataFrame(rows).sort_values('pct_gain_loss', ascending=False)
    df.to_csv(filename, index=False, float_format='%.6f')