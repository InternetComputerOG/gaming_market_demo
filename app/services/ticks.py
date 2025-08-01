from typing import List, Dict, Any
from typing_extensions import TypedDict
from app.utils import get_current_ms
from app.db.queries import insert_tick, update_metrics
from app.engine.state import EngineState, BinaryState, get_p_yes, get_p_no

class Fill(TypedDict):
    trade_id: str
    buy_user_id: str
    sell_user_id: str
    outcome_i: int
    yes_no: str
    price: float
    size: float
    fee: float
    tick_id: int
    ts_ms: int

def compute_summary(state: EngineState, fills: List[Fill]) -> Dict[str, Any]:
    """
    Computes the tick summary from the engine state and fills.
    """
    prices: Dict[int, Dict[str, Any]] = {}
    binaries = sorted(state['binaries'], key=lambda b: b['outcome_i'])
    for binary in binaries:
        i = binary['outcome_i']
        prices[i] = {
            'p_yes': float(get_p_yes(binary)),
            'p_no': float(get_p_no(binary)),
            'active': binary['active']
        }

    volume = sum(float(f['size']) for f in fills)
    mm_risk = sum(float(b['subsidy']) for b in binaries)
    mm_profit = sum(float(b['seigniorage']) for b in binaries) + sum(float(f['fee']) for f in fills)
    n_active = sum(1 for b in binaries if b['active'])

    return {
        'prices': prices,
        'volume': volume,
        'mm_risk': mm_risk,
        'mm_profit': mm_profit,
        'n_active': n_active
    }

def create_tick(state: EngineState, fills: List[Fill], tick_id: int) -> None:
    """
    Creates a new tick entry with summary and updates metrics.
    """
    summary = compute_summary(state, fills)
    ts_ms = get_current_ms()
    tick_data: Dict[str, Any] = {
        'tick_id': tick_id,
        'ts_ms': ts_ms,
        'summary': summary
    }
    insert_tick(tick_data)

    metrics: Dict[str, Any] = {
        'tick_id': tick_id,
        'volume': summary['volume'],
        'mm_risk': summary['mm_risk'],
        'mm_profit': summary['mm_profit']
    }
    update_metrics(metrics)