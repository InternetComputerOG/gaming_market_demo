from decimal import Decimal
from typing import List, Dict, Any
from typing_extensions import TypedDict

from .state import EngineState, BinaryState, get_binary, update_subsidies
from .params import EngineParams
from app.utils import usdc_amount, price_value, validate_price, validate_size, safe_divide, validate_lob_pool_volume_semantics
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
    tick_size: Decimal = None,
) -> None:
    validate_size(amount)
    binary = get_binary(state, i)
    
    # Check if binary is active
    if not binary['active']:
        raise ValueError(f"Binary {i} is not active")
    
    # Validate tick bounds per TDD: prices must be in [p_min, p_max]
    # Only validate if params are available in state (for backward compatibility)
    if 'params' in state:
        params = state['params']
        min_tick = int(params['p_min'] / params['tick_size'])
        max_tick = int(params['p_max'] / params['tick_size'])
        if tick < min_tick or tick > max_tick:
            price = Decimal(tick) * params['tick_size']
            raise ValueError(f"Invalid tick {tick} (price {price}), must be in range [{min_tick}, {max_tick}] for prices [{params['p_min']}, {params['p_max']}]")
    else:
        # Fallback validation: tick must be positive for valid prices
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
    
    # Calculate volume per TDD: buy pools store USDC volume, sell pools store token volume
    if tick_size is None:
        # Fallback: try to get tick_size from state params, otherwise use default
        tick_size = state.get('params', {}).get('tick_size', Decimal('0.01'))
    
    price = Decimal(tick) * tick_size
    
    if is_buy:
        # Buy pools: volume = USDC amount (amount * price)
        volume_to_add = amount * price
    else:
        # Sell pools: volume = token amount
        volume_to_add = amount
    
    pool['volume'] += volume_to_add
    if user_id not in pool['shares']:
        pool['shares'][user_id] = Decimal('0')
    pool['shares'][user_id] += amount  # User shares always track token amount
    
    # Note: We don't validate pool consistency here because buy pools store USDC volume
    # while shares store token amounts, so volume != sum(shares) for buy pools.
    # The proper validation is done by validate_lob_pool_volume_semantics in validate_binary_state.
    
    # Validate pool volume semantics
    try:
        validate_lob_pool_volume_semantics(pool, is_buy, tick, tick_size)
    except ValueError as e:
        # Rollback the pool update
        pool['volume'] -= volume_to_add
        pool['shares'][user_id] -= amount
        if pool['shares'][user_id] == Decimal('0'):
            del pool['shares'][user_id]
        raise ValueError(f"LOB pool volume semantics validation failed: {e}")


def cancel_from_pool(
    state: EngineState,
    i: int,
    yes_no: str,
    is_buy: bool,
    tick: int,
    user_id: str,
    af_opt_in: bool,
    tick_size: Decimal = None,
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
    
    # Calculate volume reduction per TDD: buy pools store USDC, sell pools store tokens
    if tick_size is None:
        # Fallback: try to get tick_size from state params, otherwise use default
        tick_size = state.get('params', {}).get('tick_size', Decimal('0.01'))
    
    price = Decimal(tick) * tick_size
    
    if is_buy:
        # Buy pools: reduce USDC volume (share * price)
        volume_to_reduce = share * price
    else:
        # Sell pools: reduce token volume (share)
        volume_to_reduce = share
    
    pool['volume'] -= volume_to_reduce
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
            
            # Check cross-matching condition per TDD: T + S ≥ 1 + f_match * (T + S) / 2
            # This ensures net collateral ≥ fill for solvency preservation
            min_sum = Decimal('1') + params['f_match'] * (price_yes + price_no) / Decimal('2')
            if price_yes + price_no < min_sum:
                continue
                
            pool_yes = binary['lob_pools']['YES']['buy'][k_yes]
            pool_no = binary['lob_pools']['NO']['sell'][k_no]
            
            # Calculate max fill based on pool volumes
            # YES buy pool stores USDC volume, NO sell pool stores token volume
            max_fill_yes = pool_yes['volume'] / price_yes  # Convert USDC to tokens
            max_fill_no = pool_no['volume']    # NO tokens available
            fill = min(max_fill_yes, max_fill_no)
            
            if fill <= Decimal('0'):
                continue
                
            # Calculate fee (TDD: f_match * (T + S) * Δ / 2 split between maker/taker)
            fee = params['f_match'] * fill * (price_yes + price_no) / Decimal('2')
            
            # Update V with net collateral per TDD: V_i += (T + S) * Δ - fee
            # This implements true limit price enforcement where:
            # - YES buyers pay exactly price_yes (their limit price T)
            # - NO sellers receive exactly price_no (their limit price S) 
            # - Trading fees are applied separately and transparently
            binary['V'] = float(Decimal(binary['V']) + (price_yes + price_no) * fill - fee)
            update_subsidies(state, params)
            
            # Update token supplies
            binary['q_yes'] = float(Decimal(binary['q_yes']) + fill)
            binary['q_no'] = float(Decimal(binary['q_no']) + fill)
            
            # Reduce pool volumes with correct semantics and update shares proportionally
            # Store original volumes for proportional share reduction
            original_volume_yes = pool_yes['volume']
            original_volume_no = pool_no['volume']
            
            pool_yes['volume'] -= fill * price_yes  # Reduce USDC volume
            pool_no['volume'] -= fill   # Reduce NO tokens available
            
            # Update shares proportionally to maintain volume semantics
            if original_volume_yes > Decimal('0'):
                ratio_yes = pool_yes['volume'] / original_volume_yes
                for user in list(pool_yes['shares'].keys()):
                    pool_yes['shares'][user] *= ratio_yes
                    if pool_yes['shares'][user] <= Decimal('0'):
                        del pool_yes['shares'][user]
            
            if original_volume_no > Decimal('0'):
                ratio_no = pool_no['volume'] / original_volume_no
                for user in list(pool_no['shares'].keys()):
                    pool_no['shares'][user] *= ratio_no
                    if pool_no['shares'][user] <= Decimal('0'):
                        del pool_no['shares'][user]
            
            # Validate pool consistency after volume reduction
            pools_to_validate = []
            if pool_yes['volume'] > Decimal('0'):
                pools_to_validate.append((pool_yes, True, tick_yes, params['tick_size']))
            if pool_no['volume'] > Decimal('0'):
                pools_to_validate.append((pool_no, False, tick_no, params['tick_size']))
            
            for pool, is_buy_pool, tick, tick_size in pools_to_validate:
                try:
                    validate_lob_pool_volume_semantics(pool, is_buy_pool, tick, tick_size)
                except ValueError as e:
                    # Critical error - rollback the entire cross-match operation
                    pool_yes['volume'] += fill * price_yes
                    pool_no['volume'] += fill
                    binary['V'] = float(Decimal(binary['V']) - (price_yes + price_no) * fill + fee)
                    binary['q_yes'] = float(Decimal(binary['q_yes']) - fill)
                    binary['q_no'] = float(Decimal(binary['q_no']) - fill)
                    update_subsidies(state, params)  # Restore subsidies
                    raise ValueError(f"LOB pool validation failed during cross-matching: {e}")
            
            # Clean up pools if completely consumed
            if pool_yes['volume'] <= Decimal('0'):
                del binary['lob_pools']['YES']['buy'][k_yes]
            else:
                # Reduce all shares proportionally
                original_volume = pool_yes['volume'] + fill * price_yes
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
    """
    Match a market order against LOB pools, respecting true limit price enforcement.
    
    Per TDD: Limit orders in pools execute at exactly their specified prices,
    with trading fees applied separately and transparently. Market orders get
    filled at the limit prices of the opposing pools they match against.
    
    This ensures traditional limit order book behavior where:
    - Limit order makers get exactly their requested price
    - Market order takers pay the limit prices plus transparent fees
    - No surprise pricing due to pooled collateral effects
    """
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
            # Calculate transparent trading fee per TDD
            # Market orders pay fees on top of limit prices, not embedded in them
            fee_rate = params.get('f', params.get('fee_rate', Decimal('0.01')))
            fee = fee_rate * fill * price
            
            # Create aggregated fill (single fill per pool)
            # Limit order makers get exactly their limit price (price)
            # Market order takers pay limit price + transparent fee
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
            
            # Store original volume for proportional share reduction
            original_volume = pool['volume']
            
            # Update pool volume
            if is_buy:
                pool['volume'] -= fill
            else:
                pool['volume'] -= fill * price
            
            # Update shares proportionally to maintain volume semantics
            if original_volume > Decimal('0'):
                ratio = pool['volume'] / original_volume
                for user in list(pool['shares'].keys()):
                    pool['shares'][user] *= ratio
                    if pool['shares'][user] <= Decimal('0'):
                        del pool['shares'][user]
            
            # Clean up empty pools
            if pool['volume'] <= Decimal('0'):
                del pools[k]
                    
            remaining -= fill
            
    return fills, remaining