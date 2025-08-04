import json
import time
from decimal import Decimal, getcontext
from typing import Any, Dict

import mpmath as mp
import numpy as np

getcontext().prec = 28
mp.mp.dps = 30

USDC_DECIMALS = 6
PRICE_DECIMALS = 4

def get_current_ms() -> int:
    return int(time.time() * 1000)

def to_ms(ts: float) -> int:
    return int(ts * 1000)

def from_ms(ms: int) -> float:
    return ms / 1000.0

def usdc_amount(amount: float | str | Decimal) -> Decimal:
    return Decimal(amount).quantize(Decimal(f'1e-{USDC_DECIMALS}'))

def price_value(p: float | str | Decimal) -> Decimal:
    return Decimal(p).quantize(Decimal(f'1e-{PRICE_DECIMALS}'))

def validate_price(p: Decimal) -> None:
    if not (Decimal(0) <= p <= Decimal(1)):
        raise ValueError(f"Invalid price: {p}. Must be between 0 and 1.")

def validate_size(s: Decimal) -> None:
    if s <= Decimal(0):
        raise ValueError(f"Invalid size: {s}. Must be positive.")

def validate_balance_buy(balance: Decimal, size: Decimal, est_price: Decimal, gas_fee: Decimal) -> None:
    required = size * est_price + gas_fee
    if balance < required:
        raise ValueError(f"Insufficient balance for buy: have {balance}, need {required}.")

def validate_balance_sell(tokens: Decimal, size: Decimal) -> None:
    if tokens < size:
        raise ValueError(f"Insufficient tokens for sell: have {tokens}, need {size}.")

def serialize_state(state: Dict[str, Any]) -> str:
    def default_handler(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (np.float64, np.float32)):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    return json.dumps(state, default=default_handler)

def deserialize_state(json_str: str) -> Dict[str, Any]:
    return json.loads(json_str)

def decimal_sqrt(d: Decimal) -> Decimal:
    if d < Decimal(0):
        raise ValueError("Cannot take square root of negative value.")
    return Decimal(str(mp.sqrt(mp.mpf(str(d)))))

def solve_quadratic(a: Decimal, b: Decimal, c: Decimal) -> Decimal:
    disc = b**2 - 4 * a * c
    if disc < Decimal(0):
        raise ValueError("Negative discriminant in quadratic equation.")
    sqrt_disc = decimal_sqrt(disc)
    
    # Calculate both roots
    root1 = (-b + sqrt_disc) / (2 * a)
    root2 = (-b - sqrt_disc) / (2 * a)
    
    # Return minimum positive root as per TDD requirement
    positive_roots = [r for r in [root1, root2] if r > Decimal(0)]
    if not positive_roots:
        raise ValueError("No positive roots found in quadratic equation.")
    
    return min(positive_roots)

def safe_divide(num: Decimal, den: Decimal) -> Decimal:
    if den == Decimal(0):
        raise ValueError("Division by zero.")
    return num / den

# State validation functions for limit order invariants (Phase 1.3)

def validate_limit_price_bounds(price: Decimal, p_min: Decimal, p_max: Decimal) -> None:
    """
    Validate that limit order price is within TDD bounds [p_min, p_max].
    
    Args:
        price: Limit order price to validate
        p_min: Minimum allowed price from TDD parameters
        p_max: Maximum allowed price from TDD parameters
        
    Raises:
        ValueError: If price is outside bounds
    """
    if not (p_min <= price <= p_max):
        raise ValueError(f"Limit price {price} outside bounds [{p_min}, {p_max}]")

def validate_solvency_invariant(binary: Dict[str, Any]) -> None:
    """
    Validate TDD solvency invariant: q_yes + q_no < 2 * L.
    
    Args:
        binary: BinaryState dictionary to validate
        
    Raises:
        ValueError: If solvency invariant is violated
    """
    q_yes = Decimal(str(binary['q_yes']))
    q_no = Decimal(str(binary['q_no']))
    L = Decimal(str(binary['L']))
    
    if q_yes + q_no >= Decimal('2') * L:
        raise ValueError(f"Solvency violation: q_yes({q_yes}) + q_no({q_no}) >= 2*L({L})")

def validate_lob_pool_consistency(pool: Dict[str, Any]) -> None:
    """
    Validate LOB pool internal consistency: volume matches sum of user shares.
    
    Note: This function validates basic consistency (volume = sum of shares).
    For semantic validation (buy vs sell pool semantics), use validate_lob_pool_volume_semantics.
    
    Args:
        pool: LOB pool dictionary with 'volume' and 'shares' keys
        
    Raises:
        ValueError: If pool volume doesn't match user shares
    """
    if 'volume' not in pool or 'shares' not in pool:
        return  # Empty pool is valid
    
    pool_volume = Decimal(str(pool['volume']))
    total_shares = sum(Decimal(str(share)) for share in pool['shares'].values())
    
    # Allow small precision differences due to float arithmetic
    tolerance = Decimal('1e-10')
    if abs(pool_volume - total_shares) > tolerance:
        raise ValueError(f"Pool volume {pool_volume} doesn't match total shares {total_shares}")

def validate_lob_pool_volume_semantics(pool: Dict[str, Any], is_buy: bool, tick: int, tick_size: Decimal) -> None:
    """
    Validate LOB pool volume semantics per TDD:
    - Buy pools: volume = USDC amount (shares * price)
    - Sell pools: volume = token amount (shares)
    
    Args:
        pool: LOB pool dictionary
        is_buy: True for buy pools, False for sell pools
        tick: Price tick for the pool
        tick_size: Tick size parameter
        
    Raises:
        ValueError: If volume semantics are incorrect
    """
    if 'volume' not in pool or 'shares' not in pool:
        return  # Empty pool is valid
    
    pool_volume = Decimal(str(pool['volume']))
    total_shares = sum(Decimal(str(share)) for share in pool['shares'].values())
    # Use absolute value of tick since pool keys can be negative for non-opt-in orders
    price = Decimal(abs(tick)) * tick_size
    
    if is_buy:
        # Buy pools: volume should be USDC amount (shares * price)
        expected_volume = total_shares * price
    else:
        # Sell pools: volume should be token amount (shares)
        expected_volume = total_shares
    
    # Allow small precision differences
    tolerance = Decimal('1e-10')
    if abs(pool_volume - expected_volume) > tolerance:
        raise ValueError(f"Pool volume semantics violation: expected {expected_volume}, got {pool_volume}")

def validate_binary_state(binary: Dict[str, Any], params: Dict[str, Any] = None) -> None:
    """
    Comprehensive validation of binary state invariants.
    
    Args:
        binary: BinaryState dictionary to validate
        params: Optional engine parameters for price bounds validation
        
    Raises:
        ValueError: If any invariant is violated
    """
    # Basic state invariants
    if binary['subsidy'] < 0:
        raise ValueError(f"Negative subsidy: {binary['subsidy']}")
    
    if binary['L'] <= 0:
        raise ValueError(f"Non-positive liquidity: {binary['L']}")
    
    expected_L = Decimal(str(binary['V'])) + Decimal(str(binary['subsidy']))
    actual_L = Decimal(str(binary['L']))
    if abs(actual_L - expected_L) > Decimal('1e-10'):
        raise ValueError(f"L invariant violation: L={actual_L}, V+subsidy={expected_L}")
    
    # Solvency invariant
    validate_solvency_invariant(binary)
    
    # LOB pool consistency
    if 'lob_pools' in binary:
        tick_size = Decimal(str(params.get('tick_size', '0.01'))) if params else Decimal('0.01')
        
        for token in ['YES', 'NO']:
            for side in ['buy', 'sell']:
                pools = binary['lob_pools'][token][side]
                for tick, pool in pools.items():
                    validate_lob_pool_volume_semantics(pool, side == 'buy', int(tick), tick_size)

def validate_engine_state(state: Dict[str, Any], params: Dict[str, Any] = None) -> None:
    """
    Comprehensive validation of entire engine state.
    
    Args:
        state: EngineState dictionary to validate
        params: Optional engine parameters for validation
        
    Raises:
        ValueError: If any state invariant is violated
    """
    if 'binaries' not in state:
        raise ValueError("Missing binaries in engine state")
    
    for binary in state['binaries']:
        validate_binary_state(binary, params)
    
    # Validate pre_sum_yes if present
    if 'pre_sum_yes' in state:
        # This is used for multi-resolution renormalization
        if state['pre_sum_yes'] <= 0:
            raise ValueError(f"Invalid pre_sum_yes: {state['pre_sum_yes']}")