from typing import List, Tuple, Dict, Any, TypedDict

class EngineState(TypedDict):
    """
    Opaque state for the engine, serialized to JSONB in DB.
    """
    binaries: List[Dict[str, Any]]  # Per outcome i: {'V': float, 'L': float, 'q_yes': float, 'q_no': float, 'virtual_yes': float, 'subsidy': float, 'seigniorage': float, 'active': bool, 'lob_pools': Dict[int, Dict[str, Any]]} where lob_pools[tick] = {'yes_buy': {'volume': float, 'shares': Dict[str, float]}, 'yes_sell': {...}, 'no_buy': {...}, 'no_sell': {...}}

class EngineParams(TypedDict):
    """
    Parameters for the engine, including dynamic interpolation values.
    """
    n_outcomes: int
    outcome_names: List[str]
    z: float
    gamma: float
    q0: float
    mu_start: float
    mu_end: float
    nu_start: float
    nu_end: float
    kappa_start: float
    kappa_end: float
    zeta_start: float
    zeta_end: float
    interpolation_mode: str  # 'reset' or 'continue'
    f: float
    p_max: float
    p_min: float
    eta: float
    tick_size: float
    cm_enabled: bool
    f_match: float
    af_enabled: bool
    sigma: float
    af_cap_frac: float
    af_max_pools: int
    af_max_surplus: float
    mr_enabled: bool
    res_schedule: List[int]
    vc_enabled: bool

class Order(TypedDict):
    order_id: str
    user_id: str
    outcome_i: int
    yes_no: str  # 'YES' or 'NO'
    type: str  # 'MARKET' or 'LIMIT'
    size: float
    limit_price: float | None
    max_slippage: float | None  # For MARKET
    af_opt_in: bool
    ts_ms: int

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

from .orders import apply_orders
from .resolutions import trigger_resolution