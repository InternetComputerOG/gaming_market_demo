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
    return Decimal(mp.sqrt(mp.mpf(str(d))))

def solve_quadratic(a: Decimal, b: Decimal, c: Decimal) -> Decimal:
    disc = b**2 - 4 * a * c
    if disc < Decimal(0):
        raise ValueError("Negative discriminant in quadratic equation.")
    sqrt_disc = decimal_sqrt(disc)
    # Assume positive root as per TDD usage
    return (-b + sqrt_disc) / (2 * a)

def safe_divide(num: Decimal, den: Decimal) -> Decimal:
    if den == Decimal(0):
        raise ValueError("Division by zero.")
    return num / den