from decimal import Decimal
from typing import List, Dict, Any, Union
from typing_extensions import TypedDict

from .state import EngineState, BinaryState, get_binary, update_subsidies, get_p_yes
from .params import EngineParams
from app.utils import safe_divide, usdc_amount
from app.db.queries import fetch_positions

def trigger_resolution(
    state: EngineState,
    params: EngineParams,
    is_final: bool,
    elim_outcomes: Union[List[int], int]
) -> tuple[Dict[str, Decimal], EngineState, List[Dict[str, Any]]]:
    if not params.get('mr_enabled', False) and not is_final:
        raise ValueError("Intermediate resolutions require mr_enabled")
    if is_final and not isinstance(elim_outcomes, int):
        raise ValueError("Final resolution requires winner as int")
    if not is_final and not isinstance(elim_outcomes, list):
        raise ValueError("Intermediate resolution requires list of outcomes")

    if is_final:
        winner = elim_outcomes
        active_outcomes = [b['outcome_i'] for b in state['binaries'] if b['active']]
        elim_outcomes = [o for o in active_outcomes if o != winner]
    else:
        elim_outcomes = sorted(elim_outcomes)  # Determinism

    active_binaries = [b for b in state['binaries'] if b['active']]
    pre_sum_yes = sum(Decimal(str(get_p_yes(b))) for b in active_binaries)

    payouts: Dict[str, Decimal] = {}
    events: List[Dict[str, Any]] = []

    freed_total = Decimal('0')
    for outcome_i in elim_outcomes:
        binary = get_binary(state, outcome_i)
        if not binary['active']:
            continue

        all_positions = fetch_positions()
        pos_i = [p for p in all_positions if p['binary_id'] == outcome_i]

        total_q_no = Decimal('0')
        for pos in pos_i:
            q_no = Decimal(str(pos['q_no']))
            total_q_no += q_no
            user_id = pos['user_id']
            payouts[user_id] = payouts.get(user_id, Decimal('0')) + q_no

        V = Decimal(str(binary['V']))
        subsidy = Decimal(str(binary['subsidy']))
        L = Decimal(str(binary['L']))

        # Preserve solvency: total_q_no < L per invariants
        if total_q_no > L:
            raise ValueError("Solvency violation in resolution")

        V -= total_q_no
        binary['V'] = float(V)
        update_subsidies(state, params)

        freed = L - total_q_no
        freed_total += freed

        binary['active'] = False
        events.append({
            'type': 'ELIMINATION',
            'outcome_i': outcome_i,
            'payout_total': float(total_q_no),
            'freed': float(freed)
        })

    remaining_active = [b for b in state['binaries'] if b['active']]
    num_remaining = len(remaining_active)

    if num_remaining > 0 and freed_total > Decimal('0'):
        added = safe_divide(freed_total, Decimal(str(num_remaining)))
        for b in remaining_active:
            V_b = Decimal(str(b['V']))
            V_b += added
            b['V'] = float(V_b)
        update_subsidies(state, params)

    post_redist_sum = sum(Decimal(str(get_p_yes(b))) for b in remaining_active)
    if post_redist_sum > Decimal('0'):
        for b in remaining_active:
            old_p = Decimal(str(get_p_yes(b)))
            target_p = safe_divide(old_p, post_redist_sum) * pre_sum_yes
            L_b = Decimal(str(b['L']))
            q_yes_b = Decimal(str(b['q_yes']))
            virtual = target_p * L_b - q_yes_b
            if params.get('vc_enabled', True) and virtual < Decimal('0'):
                virtual = Decimal('0')
            b['virtual_yes'] = float(virtual)

    if is_final:
        winner_binary = get_binary(state, winner)
        all_positions = fetch_positions()
        pos_w = [p for p in all_positions if p['binary_id'] == winner]

        total_q_yes = Decimal('0')
        for pos in pos_w:
            q_yes = Decimal(str(pos['q_yes']))
            total_q_yes += q_yes
            user_id = pos['user_id']
            payouts[user_id] = payouts.get(user_id, Decimal('0')) + q_yes

        V_w = Decimal(str(winner_binary['V']))
        if total_q_yes > Decimal(str(winner_binary['L'])):
            raise ValueError("Solvency violation in final payout")
        V_w -= total_q_yes
        winner_binary['V'] = float(V_w)
        update_subsidies(state, params)

        events.append({
            'type': 'FINAL_PAYOUT',
            'winner': winner,
            'payout_total': float(total_q_yes)
        })

    # Quantize payouts
    quantized_payouts = {k: usdc_amount(v) for k, v in payouts.items()}

    return quantized_payouts, state, events