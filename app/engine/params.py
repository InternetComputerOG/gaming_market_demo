from typing import TypedDict

import numpy as np

# Import the complete EngineParams from config which includes all LOB parameters
from app.config import EngineParams

# Legacy basic parameters for backward compatibility
class Params(TypedDict):
    """Legacy parameter structure for basic AMM math functions.
    
    Note: For comprehensive engine parameters including LOB functionality,
    use EngineParams (imported from app.config) which includes all TDD parameters.
    """
    alpha: float  # Base liquidity parameter from TDD Section 3.2
    beta: float   # Scaling factor for imbalance from TDD Section 3.2
    trade_fee: float  # Fee rate for trades, e.g., 0.01 for 1%
    liquidity_initial: float  # Initial liquidity for new markets
    min_liquidity: float  # Minimum liquidity threshold
    max_imbalance_ratio: float  # Maximum allowed imbalance ratio
    min_auto_fill: float  # Minimum amount for auto-fill logic
    resolution_prob: float  # Demo resolution probability for multi-resolution

def get_default_params() -> Params:
    return {
        'alpha': 1.0,
        'beta': 1.0,  # Fixed: Test expects beta=1.0
        'trade_fee': 0.01,
        'liquidity_initial': 10000.0 / 3,  # Align with TDD Z/N example, assuming N=3 default
        'min_liquidity': 0.0,  # Fixed: Test expects min_liquidity=0.0
        'max_imbalance_ratio': 0.99,  # Fixed: Tied to p_max, should be <1
        'min_auto_fill': 0.1,
        'resolution_prob': 0.5,
    }

def validate_params(params: Params) -> None:
    if params['alpha'] <= 0:
        raise ValueError("alpha must be >0")
    if params['beta'] <= 0:  # Fixed: Test expects beta must be >0
        raise ValueError("beta must be >0")
    if not (0 <= params['trade_fee'] < 1):
        raise ValueError("trade_fee must be in [0,1)")
    if params['liquidity_initial'] <= 0:
        raise ValueError("liquidity_initial must be >0")
    if params['min_liquidity'] < 0:  # Fixed: Allow min_liquidity=0.0
        raise ValueError("Minimum liquidity must be non-negative")
    if params['max_imbalance_ratio'] >= 1:  # Fixed: Should be <1, not >1
        raise ValueError("max_imbalance_ratio must be <1")
    if params['min_auto_fill'] <= 0:
        raise ValueError("Min auto fill must be positive")
    if not (0 <= params['resolution_prob'] <= 1):
        raise ValueError("Resolution probability must be between 0 and 1")

def solve_quadratic(a: float, b: float, c: float) -> float:
    # Helper for quadratic solutions in AMM pricing, using numpy for stability
    # From TDD pseudocode: select positive root ensuring non-negative reserves
    
    # Check for degenerate case
    if a <= 0:
        raise ValueError("a must be >0")
    
    # Check discriminant for real roots
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        raise ValueError("No real roots")
    
    roots = np.roots([a, b, c])
    positive_roots = [r for r in roots if r > 0]
    if not positive_roots:
        raise ValueError("No positive root found")
    return min(positive_roots)  # Select smallest positive for min delta


# LOB Parameter Documentation and Relationships with Limit Order Pricing
# ======================================================================

def get_lob_parameter_documentation() -> dict[str, str]:
    """Returns comprehensive documentation for LOB-related parameters and their 
    relationships with limit order pricing per TDD specifications.
    
    This function documents how each parameter affects limit order behavior,
    cross-matching mechanics, and true limit price enforcement.
    
    Returns:
        Dictionary mapping parameter names to detailed descriptions including
        their role in limit order pricing and TDD compliance.
    """
    return {
        'f_match': (
            "Match fee fraction for cross-matched limit orders (TDD Section 4.2). "
            "Applied as: fee = f_match * (price_yes + price_no) * fill / 2. "
            "This fee is split between maker and taker, charged separately from limit prices. "
            "Users pay/receive exactly their limit prices; fees are additional costs. "
            "Cross-matching condition: price_yes + price_no >= 1 + f_match * (price_yes + price_no) / 2 "
            "ensures solvency preservation with net collateral >= fill."
        ),
        'tick_size': (
            "Price granularity for limit order book (TDD Section 4.1). "
            "Defines discrete price levels: $0.01, $0.02, ..., $0.99. "
            "All limit prices must be multiples of tick_size within [p_min, p_max]. "
            "Affects order matching precision and pool organization."
        ),
        'p_min': (
            "Minimum allowed limit price bound (TDD Section 3.3). "
            "Enforces lower bound: limit_price >= p_min for all orders. "
            "Prevents extreme pricing that could destabilize the market. "
            "Used in limit price validation before order placement."
        ),
        'p_max': (
            "Maximum allowed limit price bound (TDD Section 3.3). "
            "Enforces upper bound: limit_price <= p_max for all orders. "
            "Prevents extreme pricing that could destabilize the market. "
            "Used in limit price validation before order placement."
        ),
        'cm_enabled': (
            "Cross-matching enabled flag (TDD Section 4.2). "
            "When True: YES buy orders can match with NO sell orders at complementary prices. "
            "Enables true limit price enforcement where users pay exactly their limit prices. "
            "When False: reverts to siloed pools without cross-matching benefits."
        ),
        'af_enabled': (
            "Auto-fill enabled flag (TDD Section 5). "
            "When True: allows limit orders to be auto-filled when cross-impacts occur. "
            "Provides price improvement opportunities for limit order holders. "
            "Opt-in per order via auto-fill flag in order submission."
        ),
        'sigma': (
            "Seigniorage share fraction (TDD Section 5.2). "
            "Controls allocation of auto-fill surplus: sigma to system, (1-sigma) to users. "
            "Affects rebate amounts for auto-filled limit orders. "
            "Range [0,1]: 0 = full price improvement to users, 1 = all surplus to system."
        ),
        'af_cap_frac': (
            "Auto-fill volume cap fraction (TDD Section 5.3). "
            "Limits max filled volume per pool: cap = af_cap_frac * diverted_collateral. "
            "Prevents excessive auto-fill cascades that could destabilize pricing. "
            "Typical range (0, 0.2) to balance liquidity provision with stability."
        ),
        'af_max_pools': (
            "Maximum pools per auto-fill event (TDD Section 5.3). "
            "Caps number of LOB pools that can be auto-filled in single cross-impact. "
            "Prevents cascade effects and limits computational complexity. "
            "Typical range 1-5 pools to balance efficiency with risk control."
        ),
        'af_max_surplus': (
            "Maximum surplus per trade as fraction of trade size (TDD Section 5.3). "
            "Caps total seigniorage: max_surplus = af_max_surplus * trade_size. "
            "Prevents excessive value extraction from single large trades. "
            "Ensures auto-fill benefits remain proportional to market activity."
        )
    }


# Note: Runtime validation of LOB parameters and state invariants is handled
# by the comprehensive validation functions in app/utils.py (created in Phase 1.3):
# - validate_limit_price_bounds() for price bound checks
# - validate_binary_state() for binary invariant validation  
# - validate_engine_state() for full engine state validation
# - validate_lob_pool_consistency() for pool state validation
# These functions are integrated into the runtime application flow per Phase 1.5.