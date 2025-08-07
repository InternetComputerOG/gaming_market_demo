from typing_extensions import TypedDict
from typing import List, Dict, Any
from decimal import Decimal

class BinaryState(TypedDict):
    outcome_i: int
    V: float
    subsidy: float
    L: float
    q_yes: float
    q_no: float
    virtual_yes: float
    seigniorage: float
    active: bool
    lob_pools: Dict[str, Dict[str, Dict[int, Dict[str, Any]]]]  # 'YES'/'NO' -> 'buy'/'sell' -> tick: {'volume': float, 'shares': Dict[str, float]}

class EngineState(TypedDict):
    binaries: List[BinaryState]
    pre_sum_yes: float

def init_state(params: Dict[str, Any]) -> EngineState:
    """
    Initialize the engine state based on parameters.
    """
    n_outcomes = params['n_outcomes']
    z = params['z']
    gamma = params['gamma']
    q0 = params['q0']
    # Per TDD: p_yes = p_no = q0 / L_i = 0.5
    # Therefore: L_i = 2 * q0
    # Since V_i = 0 initially: subsidy_i = L_i - V_i = 2 * q0
    subsidy_init = 2 * q0
    binaries = []
    for i in range(n_outcomes):
        binaries.append({
            'outcome_i': i,
            'V': 0.0,
            'subsidy': subsidy_init,
            'L': subsidy_init,
            'q_yes': q0,
            'q_no': q0,
            'virtual_yes': 0.0,
            'seigniorage': 0.0,
            'active': True,
            'lob_pools': {
                'YES': {'buy': {}, 'sell': {}},
                'NO': {'buy': {}, 'sell': {}}
            }
        })
    pre_sum_yes = n_outcomes * (q0 / subsidy_init)
    return {'binaries': binaries, 'pre_sum_yes': pre_sum_yes}

def serialize_state(state: EngineState) -> Dict[str, Any]:
    """
    Serialize state to JSON-compatible dict, converting int keys to str.
    """
    serialized = state.copy()
    for bin_ in serialized['binaries']:
        for token in bin_['lob_pools']:
            for side in bin_['lob_pools'][token]:
                pool_dict = bin_['lob_pools'][token][side]
                str_key_dict = {str(k): v for k, v in pool_dict.items()}
                bin_['lob_pools'][token][side] = str_key_dict
    return serialized

def deserialize_state(json_dict: Dict[str, Any]) -> EngineState:
    """
    Deserialize from JSON dict, converting str keys to int.
    """
    state = json_dict.copy()
    for bin_ in state['binaries']:
        for token in bin_['lob_pools']:
            for side in bin_['lob_pools'][token]:
                str_dict = bin_['lob_pools'][token][side]
                int_key_dict = {int(k): v for k, v in str_dict.items()}
                bin_['lob_pools'][token][side] = int_key_dict
    return state

def get_binary(state: EngineState, outcome_i: int) -> BinaryState:
    """
    Get binary state for a specific outcome.
    """
    for bin_ in state['binaries']:
        if bin_['outcome_i'] == outcome_i:
            return bin_
    raise ValueError(f"Binary not found for outcome {outcome_i}")

def get_p_yes(binary: BinaryState) -> float:
    """
    Compute p_yes for a binary with price clamping to prevent p>1 violations.
    """
    L = Decimal(str(binary['L']))
    if L <= 0:
        return 0.0  # Handle division by zero case
    
    q_yes = Decimal(str(binary['q_yes']))
    virtual_yes = Decimal(str(binary.get('virtual_yes', 0.0)))  # Default to 0 if missing
    
    p_yes = (q_yes + virtual_yes) / L
    # Clamp to prevent p>1 violations per audit findings
    return float(min(p_yes, Decimal('0.99')))

def get_p_no(binary: BinaryState) -> float:
    """
    Compute p_no for a binary with price clamping.
    """
    L = Decimal(str(binary['L']))
    if L <= 0:
        return 0.0  # Handle division by zero case
    
    q_no = Decimal(str(binary['q_no']))
    p_no = q_no / L
    # Clamp to prevent price violations per audit findings
    return float(min(p_no, Decimal('0.99')))

def update_subsidies(state: EngineState, params: Dict[str, Any]) -> None:
    """
    Update subsidies and L for all binaries.
    """
    z = params['z']
    gamma = params['gamma']
    n_outcomes = params['n_outcomes']
    for bin_ in state['binaries']:
        bin_['subsidy'] = float(max(Decimal('0.0'), Decimal(str(z)) / Decimal(str(n_outcomes)) - Decimal(str(gamma)) * Decimal(str(bin_['V']))))
        bin_['L'] = float(Decimal(str(bin_['V'])) + Decimal(str(bin_['subsidy'])))