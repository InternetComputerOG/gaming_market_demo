from decimal import Decimal
from typing import Dict, Any

import mpmath as mp

from app.utils import decimal_sqrt, solve_quadratic, safe_divide, validate_size, validate_price, price_value
from .state import BinaryState
from .params import EngineParams  # Assuming EngineParams has mu, nu, kappa, p_max, p_min, eta


def get_effective_p_yes(binary: BinaryState) -> Decimal:
    """Computes effective p_yes = (q_yes + virtual_yes) / L."""
    L = Decimal(binary['L'])
    q_yes_eff = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])
    return safe_divide(q_yes_eff, L)


def get_effective_p_no(binary: BinaryState) -> Decimal:
    """Computes p_no = q_no / L."""
    L = Decimal(binary['L'])
    q_no = Decimal(binary['q_no'])
    return safe_divide(q_no, L)


def get_new_p_yes_after_buy(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal:
    """Helper to compute new p_yes after buy, without updating state."""
    L = Decimal(binary['L'])
    q_yes_eff = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])
    return safe_divide(q_yes_eff + delta, L + f_i * X)


def get_new_p_yes_after_sell(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal:
    """Helper to compute new p_yes after sell, without updating state."""
    L = Decimal(binary['L'])
    q_yes_eff = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])
    return safe_divide(q_yes_eff - delta, L - f_i * X)


def get_new_p_no_after_buy(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal:
    """Helper to compute new p_no after buy, without updating state."""
    L = Decimal(binary['L'])
    q_no = Decimal(binary['q_no'])
    return safe_divide(q_no, L + f_i * X)


def get_new_p_no_after_sell(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal) -> Decimal:
    """Helper to compute new p_no after sell, without updating state."""
    L = Decimal(binary['L'])
    q_no = Decimal(binary['q_no'])
    return safe_divide(q_no - delta, L - f_i * X)


def buy_cost_yes(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal:
    """
    Computes cost X for buying delta YES tokens in the binary, using quadratic solve and penalty.
    Per TDD derivations: X = delta * (mu * p + nu * p') / (mu + nu) + kappa * delta^2, with p' = (q_yes_eff + delta) / (L + f_i * X).
    Returns quantized Decimal.
    """
    if delta == Decimal('0'):
        return Decimal('0')
    validate_size(delta)

    mu = Decimal(params['mu_start'])
    nu = Decimal(params['nu_start'])
    kappa = Decimal(params['kappa_start'])
    p_max = Decimal(params['p_max'])
    eta = Decimal(params['eta'])

    L = Decimal(binary['L'])
    q = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])  # q_yes_eff
    p = safe_divide(q, L)

    a = mu / (mu + nu)
    b = nu / (mu + nu)
    k = delta * a * p + kappa * delta**2
    m = delta * b * (q + delta)
    coeff_a = f_i
    coeff_b = L - f_i * k
    coeff_c = -k * L - m

    X = solve_quadratic(coeff_a, coeff_b, coeff_c)

    p_prime = get_new_p_yes_after_buy(binary, delta, X, f_i)
    if p_prime > p_max:
        X *= (p_prime / p_max)**eta

    return price_value(X)  # Quantize to USDC_DECIMALS? Wait, cost in USDC, so usdc_amount(X) but context uses PRICE_DECIMALS for prices, but costs are amounts.


def sell_received_yes(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal:
    """
    Computes received X for selling delta YES tokens in the binary, using quadratic solve and penalty.
    Per TDD: X = delta * (mu * p' + nu * p) / (mu + nu) - kappa * delta^2, with p' = (q_yes_eff - delta) / (L - f_i * X).
    Returns quantized Decimal.
    """
    if delta == Decimal('0'):
        return Decimal('0')
    validate_size(delta)

    mu = Decimal(params['mu_start'])
    nu = Decimal(params['nu_start'])
    kappa = Decimal(params['kappa_start'])
    p_min = Decimal(params['p_min'])
    eta = Decimal(params['eta'])

    L = Decimal(binary['L'])
    q = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes'])  # q_yes_eff
    p = safe_divide(q, L)

    # Correct coefficients derived from TDD formula:
    # X = Δ * (μp' + νp) / (μ + ν) - κΔ²
    # p' = (q_yes - Δ) / (L - f_i * X)
    # Results in: f_i * X² - X(L + Δνpf_i/(μ+ν) - κΔ²f_i) + (Δμ(q_yes-Δ)/(μ+ν) + ΔνpL/(μ+ν) - κΔ²L) = 0
    
    coeff_a = f_i
    coeff_b = -(L + delta * nu * p * f_i / (mu + nu) - kappa * delta**2 * f_i)
    coeff_c = (delta * mu * (q - delta) / (mu + nu) + 
               delta * nu * p * L / (mu + nu) - 
               kappa * delta**2 * L)

    X = solve_quadratic(coeff_a, coeff_b, coeff_c)

    p_prime = get_new_p_yes_after_sell(binary, delta, X, f_i)
    if p_prime < p_min:
        X *= (p_min / p_prime)**eta

    return price_value(X)


def buy_cost_no(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal:
    """Symmetric to buy_cost_yes but for NO, no virtual."""
    if delta == Decimal('0'):
        return Decimal('0')
    validate_size(delta)

    mu = Decimal(params['mu_start'])
    nu = Decimal(params['nu_start'])
    kappa = Decimal(params['kappa_start'])
    p_max = Decimal(params['p_max'])
    eta = Decimal(params['eta'])

    L = Decimal(binary['L'])
    q = Decimal(binary['q_no'])
    p = safe_divide(q, L)

    a = mu / (mu + nu)
    b = nu / (mu + nu)
    k = delta * a * p + kappa * delta**2
    m = delta * b * (q + delta)
    coeff_a = f_i
    coeff_b = L - f_i * k
    coeff_c = -k * L - m

    X = solve_quadratic(coeff_a, coeff_b, coeff_c)

    p_prime = (q + delta) / (L + f_i * X)
    if p_prime > p_max:
        X *= (p_prime / p_max)**eta

    return price_value(X)


def sell_received_no(binary: BinaryState, delta: Decimal, params: EngineParams, f_i: Decimal) -> Decimal:
    """Symmetric to sell_received_yes but for NO, no virtual."""
    if delta == Decimal('0'):
        return Decimal('0')
    validate_size(delta)

    mu = Decimal(params['mu_start'])
    nu = Decimal(params['nu_start'])
    kappa = Decimal(params['kappa_start'])
    p_min = Decimal(params['p_min'])
    eta = Decimal(params['eta'])

    L = Decimal(binary['L'])
    q = Decimal(binary['q_no'])
    p = safe_divide(q, L)

    # Correct coefficients derived from TDD formula:
    # X = Δ * (μp' + νp) / (μ + ν) - κΔ²
    # p' = (q_no - Δ) / (L - f_i * X)
    # Results in: f_i * X² - X(L + Δνpf_i/(μ+ν) - κΔ²f_i) + (Δμ(q_no-Δ)/(μ+ν) + ΔνpL/(μ+ν) - κΔ²L) = 0
    
    coeff_a = f_i
    coeff_b = -(L + delta * nu * p * f_i / (mu + nu) - kappa * delta**2 * f_i)
    coeff_c = (delta * mu * (q - delta) / (mu + nu) + 
               delta * nu * p * L / (mu + nu) - 
               kappa * delta**2 * L)

    X = solve_quadratic(coeff_a, coeff_b, coeff_c)

    p_prime = (q - delta) / (L - f_i * X)
    if p_prime < p_min:
        X *= (p_min / p_prime)**eta

    return price_value(X)