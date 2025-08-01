from decimal import Decimal
from typing import Dict, List, Tuple

from app.utils import safe_divide, validate_size, price_value, usdc_amount
from .amm_math import buy_cost_yes, buy_cost_no, get_effective_p_yes, get_effective_p_no, get_new_p_yes_after_buy, get_new_p_no_after_buy, sell_received_yes, sell_received_no, get_new_p_yes_after_sell, get_new_p_no_after_sell
from .state import BinaryState, EngineState, get_p_yes, get_p_no, update_subsidies
from .params import EngineParams
from .impact_functions import get_new_prices_after_impact

AutoFillEvent = Dict[str, any]  # {'type': 'auto_fill_buy' or 'auto_fill_sell', 'binary_id': int, 'is_yes': bool, 'tick': int, 'delta': Decimal, 'surplus': Decimal, 'user_position_deltas': Dict[str, Decimal], 'user_balance_deltas': Dict[str, Decimal]}

def binary_search_max_delta(pool_tick: Decimal, is_buy: bool, is_yes: bool, binary: BinaryState, params: EngineParams, f_i: Decimal, max_high: Decimal) -> Decimal:
    low = Decimal('0')
    high = max_high
    for _ in range(20):
        mid = (low + high) / Decimal('2')
        if mid <= Decimal('0'):
            return Decimal('0')
        if is_buy:
            X_mid = buy_cost_yes(binary, mid, params, f_i) if is_yes else buy_cost_no(binary, mid, params, f_i)
            p_mid = get_new_p_yes_after_buy(binary, mid, X_mid, f_i) if is_yes else get_new_p_no_after_buy(binary, mid, X_mid, f_i)
            if p_mid <= pool_tick:
                low = mid
            else:
                high = mid
        else:
            X_mid = sell_received_yes(binary, mid, params, f_i) if is_yes else sell_received_no(binary, mid, params, f_i)
            p_mid = get_new_p_yes_after_sell(binary, mid, X_mid, f_i) if is_yes else get_new_p_no_after_sell(binary, mid, X_mid, f_i)
            if p_mid >= pool_tick:
                low = mid
            else:
                high = mid
    return low

def update_pool_and_get_deltas(pool: Dict[str, any], delta: Decimal, charge: Decimal, is_buy: bool) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    original_volume = Decimal(str(pool['volume']))
    position_deltas = {}
    balance_deltas = {}  # For sells: + charge pro-rata; for buys: 0 here, rebates separate
    if original_volume <= Decimal('0'):
        return position_deltas, balance_deltas
    for user_id, share in list(pool['shares'].items()):
        pro_rata = safe_divide(Decimal(str(share)), original_volume) * (charge if is_buy else delta)
        if is_buy:
            position_deltas[user_id] = pro_rata  # Tokens received
        else:
            position_deltas[user_id] = -pro_rata  # Tokens sold
            balance_deltas[user_id] = pro_rata  # USDC received at tick * pro_rata_delta
        pool['shares'][user_id] = Decimal(str(pool['shares'][user_id])) - pro_rata if is_buy else Decimal(str(pool['shares'][user_id])) - (safe_divide(Decimal(str(share)), original_volume) * delta)
        if pool['shares'][user_id] <= Decimal('0'):
            del pool['shares'][user_id]
    pool['volume'] = Decimal(str(pool['volume'])) - charge if is_buy else Decimal(str(pool['volume'])) - delta
    return position_deltas, balance_deltas

def apply_rebates(surplus: Decimal, sigma: Decimal, original_volume: Decimal, shares: Dict[str, Decimal], balance_deltas: Dict[str, Decimal]) -> None:
    rebate_share = (Decimal('1') - sigma) * surplus
    if rebate_share <= Decimal('0'):
        return
    for user_id, share in shares.items():
        pro_rata_rebate = safe_divide(Decimal(str(share)), original_volume) * rebate_share
        if user_id in balance_deltas:
            balance_deltas[user_id] += pro_rata_rebate
        else:
            balance_deltas[user_id] = pro_rata_rebate

def auto_fill(state: EngineState, j: int, diversion: Decimal, params: EngineParams) -> Tuple[Decimal, List[AutoFillEvent]]:
    binary = state['binaries'][j]
    if not binary['active'] or not params['af_enabled'] or diversion == Decimal('0'):
        return Decimal('0'), []
    f_j = Decimal('1') - (len([b for b in state['binaries'] if b['active']]) - 1) * params['zeta']
    total_surplus = Decimal('0')
    events = []
    is_increase = diversion > Decimal('0')
    direction = 'buy' if is_increase else 'sell'
    yes_no_list = ['YES', 'NO']
    pools_filled = 0
    for yes_no in yes_no_list:
        pools = binary['lob_pools'][yes_no][direction]
        sorted_ticks = sorted(pools.keys(), reverse=is_increase)  # Desc for buy (high tick first), asc for sell (low first)
        for tick_int in sorted_ticks:
            if pools_filled >= params['af_max_pools']:
                break
            pool = pools[tick_int]
            if pool['volume'] <= 0:
                continue
            pool_tick = price_value(Decimal(tick_int) * params['tick_size'])
            current_p = get_p_yes(binary) if yes_no == 'YES' else get_p_no(binary)
            if (is_increase and pool_tick <= current_p) or (not is_increase and pool_tick >= current_p):
                continue
            max_high = usdc_amount(Decimal(str(pool['volume'])) / pool_tick) if is_increase else Decimal(str(pool['volume']))
            delta = binary_search_max_delta(pool_tick, is_increase, yes_no == 'YES', binary, params, f_j, max_high)
            validate_size(delta)
            if delta <= Decimal('0'):
                continue
            if is_increase:
                X = buy_cost_yes(binary, delta, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, delta, params, f_j)
                charge = pool_tick * delta
                surplus = charge - X
            else:
                X = sell_received_yes(binary, delta, params, f_j) if yes_no == 'YES' else sell_received_no(binary, delta, params, f_j)
                charge = pool_tick * delta
                surplus = X - charge
            if surplus <= Decimal('0'):
                continue
            cap_delta = (params['af_cap_frac'] * abs(diversion)) / pool_tick
            if delta > cap_delta:
                delta = cap_delta
                if is_increase:
                    X = buy_cost_yes(binary, delta, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, delta, params, f_j)
                    surplus = pool_tick * delta - X
                else:
                    X = sell_received_yes(binary, delta, params, f_j) if yes_no == 'YES' else sell_received_no(binary, delta, params, f_j)
                    surplus = X - pool_tick * delta
            if surplus <= Decimal('0'):
                continue
            original_volume = Decimal(str(pool['volume']))
            original_shares = dict(pool['shares'])  # Copy for rebates
            position_deltas, balance_deltas = update_pool_and_get_deltas(pool, delta, charge if is_increase else pool_tick * delta, is_increase)
            if is_increase:
                binary['q_yes' if yes_no == 'YES' else 'q_no'] += delta
            else:
                binary['q_yes' if yes_no == 'YES' else 'q_no'] -= delta
            system_surplus = params['sigma'] * surplus
            binary['V'] += system_surplus
            update_subsidies(state, params)
            apply_rebates(surplus, params['sigma'], original_volume, original_shares, balance_deltas)
            total_surplus += surplus
            events.append({
                'type': 'auto_fill_buy' if is_increase else 'auto_fill_sell',
                'binary_id': j,
                'is_yes': yes_no == 'YES',
                'tick': tick_int,
                'delta': delta,
                'surplus': surplus,
                'user_position_deltas': position_deltas,
                'user_balance_deltas': balance_deltas
            })
            pools_filled += 1
    if total_surplus > params['af_max_surplus'] * (abs(diversion) / params['zeta']):
        total_surplus = params['af_max_surplus'] * (abs(diversion) / params['zeta'])
    return total_surplus, events