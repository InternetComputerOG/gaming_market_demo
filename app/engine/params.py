from typing import TypedDict

import numpy as np

class Params(TypedDict):
    alpha: float  # Base liquidity parameter from TDD Section 3.2
    beta: float   # Scaling factor for imbalance from TDD Section 3.2
    trade_fee: float  # Fee rate for trades, e.g., 0.01 for 1%
    liquidity_initial: float  # Initial liquidity for new markets
    min_liquidity: float  # Minimum liquidity threshold
    max_imbalance_ratio: float  # Maximum allowed imbalance ratio
    min_auto_fill: float  # Minimum amount for auto-fill logic
    resolution_prob: float  # Demo resolution probability for multi-resolution

# Alias for compatibility
EngineParams = Params

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