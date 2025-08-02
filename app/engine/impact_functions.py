from decimal import Decimal
from typing import Dict, Optional
from typing_extensions import TypedDict

import numpy as np

from app.utils import safe_divide, solve_quadratic, price_value
from app.engine.state import EngineState, BinaryState, get_binary, get_p_yes, get_p_no, update_subsidies
from app.engine.params import EngineParams
from app.engine.amm_math import get_effective_p_yes, get_effective_p_no

def compute_dynamic_params(params: EngineParams, current_time: int, round_num: Optional[int] = None) -> Dict[str, Decimal]:
    """
    Computes interpolated values for dynamic parameters (mu, nu, kappa, zeta) based on current_time.
    Linear interpolation from start to end values over total_duration.
    If mr_enabled and interpolation_mode == 'reset', reset t=0 per round (using round_num and res_offsets).
    """
    total_duration = params['total_duration']
    interpolation_mode = params['interpolation_mode']
    mr_enabled = params['mr_enabled']

    t = Decimal(current_time) / Decimal(total_duration)
    if mr_enabled and interpolation_mode == 'reset' and round_num is not None:
        # Compute round start time from res_offsets and freeze_durs
        if round_num > 0 and len(params['res_offsets']) > round_num:
            round_start = sum(params['res_offsets'][:round_num]) + sum(params['freeze_durs'][:round_num])
            round_duration = params['res_offsets'][round_num]
            t = Decimal(current_time - round_start) / Decimal(round_duration)
    t = max(min(t, Decimal(1)), Decimal(0))

    mu = Decimal(params['mu_start']) + t * (Decimal(params['mu_end']) - Decimal(params['mu_start']))
    nu = Decimal(params['nu_start']) + t * (Decimal(params['nu_end']) - Decimal(params['nu_start']))
    kappa = Decimal(params['kappa_start']) + t * (Decimal(params['kappa_end']) - Decimal(params['kappa_start']))
    zeta = Decimal(params['zeta_start']) + t * (Decimal(params['zeta_end']) - Decimal(params['zeta_start']))

    # Clamp zeta to safe range
    max_zeta = safe_divide(Decimal(1), Decimal(params['n_outcomes'] - 1))
    zeta = min(max(zeta, Decimal(0)), max_zeta)

    return {'mu': mu, 'nu': nu, 'kappa': kappa, 'zeta': zeta}

def compute_f_i(params: EngineParams, zeta: Decimal, state: EngineState) -> Decimal:
    """
    Computes f_i = 1 - (N_active - 1) * zeta, where N_active is count of active binaries.
    """
    n_active = sum(1 for binary in state['binaries'] if binary['active'])
    return Decimal(1) - Decimal(n_active - 1) * zeta

def apply_own_impact(state: EngineState, i: int, X: Decimal, is_buy: bool, is_yes: bool, f_i: Decimal, params: EngineParams) -> None:
    """
    Applies own impact: Updates V_i +=/- f_i * X (after fee), recomputes subsidy_i and L_i.
    Fee deducted from X before update (f * delta * p' approximated, but per TDD, fee separate).
    Assumes X is net of fee; caller handles fee collection.
    """
    binary = get_binary(state, i)
    sign = Decimal(1) if is_buy else Decimal(-1)
    delta_v = sign * f_i * X
    binary['V'] = float(Decimal(binary['V']) + delta_v)
    # Update subsidy and L
    update_subsidies(state, params)

def apply_cross_impacts(state: EngineState, i: int, X: Decimal, is_buy: bool, zeta: Decimal, params: EngineParams) -> None:
    """
    Applies cross impacts via diversion: For each other active j != i, V_j +=/- zeta * X.
    Recomputes subsidy_j and L_j for affected binaries.
    Sorts binaries by outcome_i for determinism.
    """
    sign = Decimal(1) if is_buy else Decimal(-1)
    delta_v_cross = sign * zeta * X
    active_binaries = sorted([b for b in state['binaries'] if b['active'] and b['outcome_i'] != i],
                             key=lambda b: b['outcome_i'])
    for binary in active_binaries:
        binary['V'] = float(Decimal(binary['V']) + delta_v_cross)
    # Update subsidies for all (since cross affects multiple)
    update_subsidies(state, params)

def get_new_prices_after_impact(binary: BinaryState, delta: Decimal, X: Decimal, f_i: Decimal, is_buy: bool, is_yes: bool) -> tuple[Decimal, Decimal]:
    """
    Computes new p_yes and p_no after own impact (diversion applied separately).
    Uses effective supplies; assumes V/L updated post-impact.
    """
    sign = 1 if is_buy else -1
    # Update liquidity with impact
    new_l = Decimal(binary['L']) + sign * f_i * X
    
    if is_yes:
        new_q_yes_eff = Decimal(binary['q_yes']) + Decimal(binary['virtual_yes']) + sign * delta
        new_p_yes = safe_divide(new_q_yes_eff, new_l)
        new_p_no = safe_divide(Decimal(binary['q_no']), new_l)
    else:
        new_q_no = Decimal(binary['q_no']) + sign * delta
        new_p_no = safe_divide(new_q_no, new_l)
        new_p_yes = safe_divide(Decimal(binary['q_yes']) + Decimal(binary['virtual_yes']), new_l)
    return new_p_yes, new_p_no

def apply_asymptotic_penalty(X: Decimal, p_prime: Decimal, p_base: Decimal, is_buy: bool, params: EngineParams) -> Decimal:
    """
    Applies penalty if p' > p_max (buy) or p' < p_min (sell): X *= (p'/p_max)^eta or (p'/p_min)^eta.
    """
    eta = Decimal(params['eta'])
    if is_buy and p_prime > Decimal(params['p_max']):
        ratio = safe_divide(p_prime, Decimal(params['p_max']))
        X *= ratio ** eta
    elif not is_buy and p_prime < Decimal(params['p_min']):
        ratio = safe_divide(p_prime, Decimal(params['p_min']))
        X *= ratio ** eta
    return X