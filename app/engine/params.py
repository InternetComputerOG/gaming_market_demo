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

def get_default_params() -> Params:
    return {
        'alpha': 1.0,
        'beta': 0.5,
        'trade_fee': 0.01,
        'liquidity_initial': 1000.0,
        'min_liquidity': 10.0,
        'max_imbalance_ratio': 5.0,
        'min_auto_fill': 0.1,
        'resolution_prob': 0.5,
    }

def validate_params(params: Params) -> None:
    if params['alpha'] <= 0:
        raise ValueError("Alpha must be positive")
    if params['beta'] < 0:
        raise ValueError("Beta must be non-negative")
    if not (0 <= params['trade_fee'] < 1):
        raise ValueError("Trade fee must be between 0 and 1")
    if params['liquidity_initial'] <= 0:
        raise ValueError("Initial liquidity must be positive")
    if params['min_liquidity'] <= 0:
        raise ValueError("Minimum liquidity must be positive")
    if params['max_imbalance_ratio'] <= 1:
        raise ValueError("Max imbalance ratio must be greater than 1")
    if params['min_auto_fill'] <= 0:
        raise ValueError("Min auto fill must be positive")
    if not (0 <= params['resolution_prob'] <= 1):
        raise ValueError("Resolution probability must be between 0 and 1")

def solve_quadratic(a: float, b: float, c: float) -> float:
    # Helper for quadratic solutions in AMM pricing, using numpy for stability
    # From TDD pseudocode: select positive root ensuring non-negative reserves
    roots = np.roots([a, b, c])
    positive_roots = [r for r in roots if r > 0]
    if not positive_roots:
        raise ValueError("No positive root found for quadratic")
    return min(positive_roots)  # Select smallest positive for min delta