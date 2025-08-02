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
    return key >= 0


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
    
    # Check if binary is active
    if not binary['active']:
        raise ValueError(f"Binary {i} is not active")
    
    # Validate tick (must be > 0 for valid prices)
    if tick <= 0:
        raise ValueError(f"Invalid tick {tick}, must be > 0")
    
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
        raise ValueError(f"Pool not found for {yes_no} {is_buy_str}")
    key = get_pool_key(tick, af_opt_in)
    if key not in binary['lob_pools'][yes_no][is_buy_str]:
        raise ValueError(f"Pool not found for tick {tick}")
    pool = binary['lob_pools'][yes_no][is_buy_str][key]
    if user_id not in pool['shares']:
        raise ValueError(f"User {user_id} not found in pool")
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
    
    # Check if binary is active
    if not binary['active']:
        raise ValueError(f"Binary {i} is not active")
    
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
            
            # Check if prices sum to >= 1 for valid cross-match
            if price_yes + price_no < Decimal('1'):
                continue
                
            pool_yes = binary['lob_pools']['YES']['buy'][k_yes]
            pool_no = binary['lob_pools']['NO']['sell'][k_no]
            
            # Calculate max fill based on pool volumes
            # Both pools store volume as token quantities
            max_fill_yes = pool_yes['volume']  # YES tokens wanted
            max_fill_no = pool_no['volume']    # NO tokens available
            fill = min(max_fill_yes, max_fill_no)
            
            if fill <= Decimal('0'):
                continue
                
            # Calculate fee (TDD: f_match * (T + S) * Δ / 2 to maker)
            fee = params['f_match'] * fill * (price_yes + price_no) / Decimal('2')
            
            # Update V with net collateral added (price_yes + price_no - fee)
            binary['V'] += (price_yes + price_no - fee / fill) * fill
            update_subsidies(state, params)
            
            # Update token supplies
            binary['q_yes'] += fill
            binary['q_no'] += fill
            
            # Reduce pool volumes (both are in tokens)
            pool_yes['volume'] -= fill  # Reduce YES tokens wanted
            pool_no['volume'] -= fill   # Reduce NO tokens available
            
            # Clean up pools if completely consumed
            if pool_yes['volume'] <= Decimal('0'):
                del binary['lob_pools']['YES']['buy'][k_yes]
            else:
                # Reduce all shares proportionally
                original_volume = pool_yes['volume'] + fill
                ratio = pool_yes['volume'] / original_volume
                for user in pool_yes['shares']:
                    pool_yes['shares'][user] *= ratio
                    
            if pool_no['volume'] <= Decimal('0'):
                del binary['lob_pools']['NO']['sell'][k_no]
            else:
                # Reduce all shares proportionally  
                original_volume = pool_no['volume'] + fill
                ratio = pool_no['volume'] / original_volume
                for user in pool_no['shares']:
                    pool_no['shares'][user] *= ratio
            
            # Add fill record
            fills.append({
                'trade_id': str(hash(current_ts)),
                'buy_user_id': 'limit_yes_pool',
                'sell_user_id': 'limit_no_pool',
                'outcome_i': i,
                'yes_no': 'YES',
                'price_yes': price_yes,
                'price_no': price_no,
                'size': fill,
                'fee': fee,
                'tick_id': tick_id,
                'ts_ms': current_ts,
            })
            
            # Only process one match per YES pool for simplicity
            break
            
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
    # Validate size
    if size <= Decimal('0'):
        raise ValueError("Size must be positive")
        
    fills = []
    remaining = size
    binary = get_binary(state, i)
    
    # Check if binary is active
    if not binary['active']:
        raise ValueError(f"Binary {i} is not active")
    
    p = get_effective_p_yes(binary) if is_yes else get_effective_p_no(binary)
    yes_no = 'YES' if is_yes else 'NO'
    is_buy_str = 'buy' if is_buy else 'sell'
    opposing_str = 'sell' if is_buy else 'buy'
    
    # Get sorted ticks for opposing pools
    if yes_no not in binary['lob_pools'] or opposing_str not in binary['lob_pools'][yes_no]:
        return fills, remaining
        
    pools = binary['lob_pools'][yes_no][opposing_str]
    
    if is_buy:
        # Lowest price first (ascending) - buy from cheapest sellers
        sorted_keys = sorted([k for k in pools.keys()], key=lambda k: get_tick_from_key(k))
    else:
        # Highest price first (descending) - sell to highest bidders
        sorted_keys = sorted([k for k in pools.keys()], key=lambda k: get_tick_from_key(k), reverse=True)
    
    for k in sorted_keys:
        if remaining <= Decimal('0'):
            break
            
        pool = pools[k]
        if pool['volume'] <= Decimal('0'):
            continue
            
        price = price_value(Decimal(get_tick_from_key(k)) * params['tick_size'])
        
        if is_buy:
            # Buying from sell pool - pool volume is in tokens
            fill = min(remaining, pool['volume'])
        else:
            # Selling to buy pool - pool volume is in USDC, convert to tokens
            max_fill = pool['volume'] / price
            fill = min(remaining, max_fill)
        
        if fill > Decimal('0'):
            fee = params['f'] * fill * price
            
            # Create aggregated fill (single fill per pool)
            fills.append({
                'trade_id': str(hash(current_ts + len(fills))),
                'buy_user_id': 'market_user' if is_buy else 'limit_pool',
                'sell_user_id': 'limit_pool' if is_buy else 'market_user',
                'outcome_i': i,
                'yes_no': yes_no,
                'price': price,
                'size': fill,
                'fee': fee,
                'tick_id': tick_id,
                'ts_ms': current_ts,
            })
            
            # Update pool volume
            if is_buy:
                pool['volume'] -= fill
            else:
                pool['volume'] -= fill * price
                
            # Clean up empty pools
            if pool['volume'] <= Decimal('0'):
                del pools[k]
            else:
                # Update shares proportionally
                if is_buy:
                    ratio = pool['volume'] / (pool['volume'] + fill)
                else:
                    ratio = pool['volume'] / (pool['volume'] + fill * price)
                for user in pool['shares']:
                    pool['shares'][user] *= ratio
                    
            remaining -= fill
            
    return fills, remaining