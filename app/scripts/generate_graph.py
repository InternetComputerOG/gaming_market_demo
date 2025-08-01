import matplotlib.pyplot as plt
import numpy as np
from typing import List, Dict, Any
from supabase import Client
from app.config import get_supabase_client
from app.db.queries import load_config
from app.utils import from_ms, safe_divide

def generate_graph(output_path: str = None) -> None:
    """
    Generates a Matplotlib graph of cumulative volume, MM risk, and MM profit over time.
    Fetches data from 'ticks' and 'metrics' tables, computes relative time in seconds.
    """
    client: Client = get_supabase_client()
    
    # Fetch config to get start_ts if needed, but use min ts_ms for relative time
    config: Dict[str, Any] = load_config()
    
    # Fetch all ticks sorted by tick_id
    ticks_response = client.table('ticks').select('tick_id, ts_ms').order('tick_id', desc=False).execute()
    ticks_data: List[Dict[str, Any]] = ticks_response.data if ticks_response.data else []
    
    # Fetch all metrics sorted by tick_id
    metrics_response = client.table('metrics').select('tick_id, volume, mm_risk, mm_profit').order('tick_id', desc=False).execute()
    metrics_data: List[Dict[str, Any]] = metrics_response.data if metrics_response.data else []
    
    if not ticks_data or not metrics_data:
        print("No data available for graphing.")
        return
    
    # Assume tick_ids match between tables; filter to common tick_ids for safety
    tick_ids = [t['tick_id'] for t in ticks_data]
    metrics_dict = {m['tick_id']: m for m in metrics_data}
    filtered_metrics = [metrics_dict[tid] for tid in tick_ids if tid in metrics_dict]
    
    # Extract data
    ts_ms_list = [t['ts_ms'] for t in ticks_data]
    min_ts = min(ts_ms_list)
    times = [(from_ms(ts) - from_ms(min_ts)) for ts in ts_ms_list]  # Relative time in seconds
    
    volumes_inc = [float(m['volume']) for m in filtered_metrics]
    volumes_cum = np.cumsum(volumes_inc)
    
    mm_risks = [float(m['mm_risk']) for m in filtered_metrics]
    mm_profits = [float(m['mm_profit']) for m in filtered_metrics]
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, volumes_cum, label='Cumulative Volume (USDC)', color='blue')
    ax.plot(times, mm_risks, label='MM Risk (sum subsidy_i, USDC)', color='red')
    ax.plot(times, mm_profits, label='MM Profit (fees + seigniorage, USDC)', color='green')
    
    ax.set_xlabel('Time (seconds since first tick)')
    ax.set_ylabel('USDC Amount')
    ax.set_title('Gaming Market Metrics Over Time')
    ax.legend()
    ax.grid(True)
    
    if output_path:
        plt.savefig(output_path)
    else:
        plt.show()

if __name__ == '__main__':
    generate_graph()