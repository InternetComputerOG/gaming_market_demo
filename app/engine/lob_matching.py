from decimal import Decimal
from typing import List, Dict, Any
from typing_extensions import TypedDict

from .state import EngineState, BinaryState, get_binary, update_subsidies
from .params import EngineParams
from app.utils import usdc_amount, price_value, validate_price, validate_size, safe_divide
from .amm_math import get_effective_p_yes, get_effective_p_no


def get_pool_key(tick: int, af_opt_in: bool) -> int:
    return tick if af_opt_in else -tick


def get_tick_from_key(key: int) -> int:
    return abs(key)


def is_opt_in_from_key(key: int) -> bool:
    return key > 0


def add_to_lob_pool(
    state: EngineState,
    i: int,
    yes_no: str,
    is_buy: bool,
    tick: int,
    user_id: str,
    amount: Decimal,
    af_opt_in: bool,
) -> None:
    validate_size(amount)
    binary = get_binary(state, i)
    is_buy_str = 'buy' if is_buy else 'sell'
    if yes_no not in binary['lob_pools']:
        binary['lob_pools'][yes_no] = {'buy': {}, 'sell': {}}
    if is_buy_str not in binary['lob_pools'][yes_no]:
        binary['lob_pools'][yes_no][is_buy_str] = {}
    key = get_pool_key(tick, af_opt_in)
    if key not in binary['lob_pools'][yes_no][is_buy_str]:
        binary['lob_pools'][yes_no][is_buy_str][key] = {'volume': Decimal('0'), 'shares': {}}
    pool = binary['lob_pools'][yes_no][is_buy_str][key]
    pool['volume'] += amount
    if user_id not in pool['shares']:
        pool['shares'][user_id] = Decimal('0')
    pool['shares'][user_id] += amount


def cancel_from_pool(
    state: EngineState,
    i: int,
    yes_no: str,
    is_buy: bool,
    tick: int,
    user_id: str,
    af_opt_in: bool,
) -> Decimal:
    binary = get_binary(state, i)
    is_buy_str = 'buy' if is_buy else 'sell'
    if yes_no not in binary['lob_pools'] or is_buy_str not in binary['lob_pools'][yes_no]:
        return Decimal('0')
    key = get_pool_key(tick, af_opt_in)
    if key not in binary['lob_pools'][yes_no][is_buy_str]:
        return Decimal('0')
    pool = binary['lob_pools'][yes_no][is_buy_str][key]
    if user_id not in pool['shares']:
        return Decimal('0')
    share = pool['shares'][user_id]
    pool['volume'] -= share
    del pool['shares'][user_id]
    if pool['volume'] <= Decimal('0'):
        del binary['lob_pools'][yes_no][is_buy_str][key]
    return share


def cross_match_binary(
    state: EngineState,
    i: int,
    params: EngineParams,
    current_ts: int,
    tick_id: int,
) -> List[Dict[str, Any]]:
    fills = []
    if not params['cm_enabled']:
        return fills
    binary = get_binary(state, i)
    if 'buy' not in binary['lob_pools']['YES'] or 'sell' not in binary['lob_pools']['NO']:
        return fills
    # Get all YES buy pools, sorted descending by price (highest first)
    yes_buy_pools = sorted(binary['lob_pools']['YES']['buy'].keys(), key=lambda k: get_tick_from_key(k), reverse=True)
    for k_yes in yes_buy_pools:
        tick_yes = get_tick_from_key(k_yes)
        price_yes = price_value(Decimal(tick_yes) * params['tick_size'])
        comp_tick_no = int((Decimal('1') / params['tick_size'] - Decimal(tick_yes)))
        # For exact complement, but to loosen for overround, scan for tick_no >= comp_tick_no
        no_sell_pools = sorted([k for k in binary['lob_pools']['NO']['sell'].keys() if get_tick_from_key(k) >= comp_tick_no], key=lambda k: get_tick_from_key(k))
        for k_no in no_sell_pools:
            tick_no = get_tick_from_key(k_no)
            price_no = price_value(Decimal(tick_no) * params['tick_size'])
            if price_yes + price_no < Decimal('1') or price_yes <= price_no:
                continue
            pool_yes = binary['lob_pools']['YES']['buy'][k_yes]
            pool_no = binary['lob_pools']['NO']['sell'][k_no]
            max_fill_yes = pool_yes['volume'] / price_yes
            max_fill_no = pool_no['volume']
            max_fill = min(max_fill_yes, max_fill_no)
            # Cap to preserve invariant
            added_per_unit = price_yes - price_no
            if added_per_unit >= Decimal('1'):
                cap = max_fill
            elif added_per_unit > Decimal('0'):
                den = Decimal('1') - added_per_unit
                cap = safe_divide((Decimal(binary['l']) - Decimal(binary['q_yes'])), den)
                cap = min(max_fill, cap)
            else:
                continue
            fill = min(max_fill, cap)
            if fill <= Decimal('0'):
                continue
            fee = params['f_match'] * (price_yes + price_no) * fill / Decimal('2')
            # Update V
            binary['v'] += (price_yes - price_no) * fill
            update_subsidies(state, params)
            # Mint YES for yes pool users, burn NO for no pool users (but since q down when placed, no burn here)
            # Update q_yes += fill
            binary['q_yes'] += fill
            # No change to q_no, as per earlier plan
            # Pro-rata for yes pool (buyers get YES)
            for user, share in pool_yes['shares'].items():
                user_fill = fill * (share / pool_yes['volume'])
                # Assume update_position(user, i, 'YES', user_fill) in orders.py
            # Pro-rata for no pool (sellers get USDC)
            for user, share in pool_no['shares'].items():
                user_fill = fill * (share / pool_no['volume'])
                # Update balance user + user_fill * price_no - fee portion
            # Reduce pools
            pool_yes['volume'] -= fill * price_yes
            pool_no['volume'] -= fill
            if pool_yes['volume'] <= Decimal('0'):
                del binary['lob_pools']['YES']['buy'][k_yes]
            else:
                for user in pool_yes['shares']:
                    pool['shares'][user] = pool_yes['shares'][user] * (pool_yes['volume'] / (pool_yes['volume'] + fill * price_yes))
            if pool_no['volume'] <= Decimal('0'):
                del binary['lob_pools']['NO']['sell'][k_no]
            else:
                for user in pool_no['shares']:
                    pool_no['shares'][user] *= (pool_no['volume'] / (pool_no['volume'] + fill))
            # Add aggregated fill
            fills.append({
                'trade_id': str(hash(current_ts)),  # Deterministic proxy
                'buy_user_id': 'limit_yes_pool',
                'sell_user_id': 'limit_no_pool',
                'outcome_i': i,
                'yes_no': 'YES',
                'price': price_yes,
                'size': fill,
                'fee': fee,
                'tick_id': tick_id,
                'ts_ms': current_ts,
            })
    return fills


def match_market_order(
    state: EngineState,
    i: int,
    is_buy: bool,
    is_yes: bool,
    size: Decimal,
    params: EngineParams,
    current_ts: int,
    tick_id: int,
) -> tuple[List[Dict[str, Any]], Decimal]:
    fills = []
    remaining = size
    binary = get_binary(state, i)
    p = get_effective_p_yes(binary) if is_yes else get_effective_p_no(binary)
    yes_no = 'YES' if is_yes else 'NO'
    is_buy_str = 'buy' if is_buy else 'sell'
    opposing_str = 'sell' if is_buy else 'buy'
    # Get sorted ticks for opposing pools
    pools = binary['lob_pools'][yes_no][opposing_str]
    if is_buy:
        # Lowest price first (ascending)
        sorted_keys = sorted([k for k in pools if get_tick_from_key(k) * params['tick_size'] > p])
    else:
        # Highest price first (descending)
        sorted_keys = sorted([k for k in pools if get_tick_from_key(k) * params['tick_size'] < p], reverse=True)
    for k in sorted_keys:
        if remaining <= Decimal('0'):
            break
        pool = pools[k]
        price = price_value(Decimal(get_tick_from_key(k)) * params['tick_size'])
        if is_buy:
            # Pool volume in tokens (sell pool)
            fill = min(remaining, pool['volume'])
            cost = fill * price
            fee = params['f'] * cost
        else:
            # Pool volume in USDC (buy pool)
            max_fill = pool['volume'] / price
            fill = min(remaining, max_fill)
            received = fill * price
            fee = params['f'] * received
        if fill > Decimal('0'):
            # Create fills for pro-rata sellers/buyers in pool
            for user, share in pool['shares'].items():
                user_fill = fill * (share / pool['volume'] if is_buy else share / pool['volume'] * price)
                fills.append({
                    'trade_id': str(hash(current_ts + len(fills))),
                    'buy_user_id': user if not is_buy else 'market_user',  # Place holder, actual in orders.py
                    'sell_user_id': user if is_buy else 'market_user',
                    'outcome_i': i,
                    'yes_no': yes_no,
                    'price': price,
                    'size': user_fill,
                    'fee': fee * (user_fill / fill),
                    'tick_id': tick_id,
                    'ts_ms': current_ts,
                })
            # Update pool
            if is_buy:
                pool['volume'] -= fill
            else:
                pool['volume'] -= fill * price
            if pool['volume'] <= Decimal('0'):
                del pools[k]
            else:
                ratio = pool['volume'] / (pool['volume'] + (fill if is_buy else fill * price))
                for user in pool['shares']:
                    pool['shares'][user] *= ratio
            remaining -= fill
    return fills, remaining