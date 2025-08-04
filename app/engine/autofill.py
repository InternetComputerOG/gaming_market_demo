from decimal import Decimal
from typing import Dict, List, Tuple

from app.utils import safe_divide, validate_size, price_value, usdc_amount, validate_binary_state, validate_solvency_invariant
from .amm_math import buy_cost_yes, buy_cost_no, get_effective_p_yes, get_effective_p_no, get_new_p_yes_after_buy, get_new_p_no_after_buy, sell_received_yes, sell_received_no, get_new_p_yes_after_sell, get_new_p_no_after_sell
from .state import BinaryState, EngineState, get_p_yes, get_p_no, update_subsidies
from .params import EngineParams
from .impact_functions import get_new_prices_after_impact

AutoFillEvent = Dict[str, any]  # {'type': 'auto_fill_buy' or 'auto_fill_sell', 'binary_id': int, 'is_yes': bool, 'tick': int, 'delta': Decimal, 'surplus': Decimal, 'user_position_deltas': Dict[str, Decimal], 'user_balance_deltas': Dict[str, Decimal]}

def trigger_auto_fills(state: EngineState, i: int, X: Decimal, is_buy: bool, params: EngineParams, current_time: int) -> List[AutoFillEvent]:
    """
    Trigger auto-fills on cross-impacts after an order execution.
    
    Args:
        state: Current engine state
        i: Binary index where the order was executed
        X: Amount of the order (USDC cost/received)
        is_buy: Whether the order was a buy
        params: Engine parameters
        current_time: Current timestamp
        
    Returns:
        List of auto-fill events
    """
    if not params.get('af_enabled', False):
        return []
    
    all_events = []
    
    # Calculate diversions for other active binaries due to cross-impacts
    # This is a simplified implementation - in practice, this would use
    # the impact functions to calculate proper diversions
    active_binaries = [j for j, binary in enumerate(state['binaries']) if binary.get('active', True)]
    
    for j in active_binaries:
        if j == i:  # Skip the binary where the order was executed
            continue
            
        # Calculate diversion based on cross-impact
        # This is a simplified calculation - the actual implementation would
        # use the impact functions to determine the proper diversion amount
        zeta = params.get('zeta', Decimal('0.1'))
        n_active = len(active_binaries)
        
        if n_active > 1:
            # Simple cross-impact calculation
            diversion = X * zeta / (n_active - 1)
            if not is_buy:
                diversion = -diversion
                
            # Trigger auto-fill for this binary
            surplus, events = auto_fill(state, j, diversion, params)
            all_events.extend(events)
    
    return all_events

def binary_search_max_delta(pool_tick: Decimal, is_buy: bool, is_yes: bool, binary: BinaryState, params: EngineParams, f_i: Decimal, max_high: Decimal) -> Decimal:
    low = Decimal('0')
    high = max_high
    

    
    # Handle edge cases
    if max_high <= Decimal('0'):
        return Decimal('0')
    
    best_delta = Decimal('0')
    
    for iteration in range(20):
        mid = (low + high) / Decimal('2')
        if mid <= Decimal('0'):
            break
        
        try:
            if is_buy:
                X_mid = buy_cost_yes(binary, mid, params, f_i) if is_yes else buy_cost_no(binary, mid, params, f_i)
                p_mid = get_new_p_yes_after_buy(binary, mid, X_mid, f_i) if is_yes else get_new_p_no_after_buy(binary, mid, X_mid, f_i)
                charge_mid = pool_tick * mid
                surplus_mid = charge_mid - X_mid
                
                # Check both constraints: price and profitability
                price_ok = p_mid <= pool_tick
                profit_ok = surplus_mid >= Decimal('0')
                
                if price_ok and profit_ok:
                    best_delta = mid
                    low = mid
                    print(f"DEBUG: Both constraints satisfied, setting low = {low}, best_delta = {best_delta}")
                else:
                    high = mid

            else:
                X_mid = sell_received_yes(binary, mid, params, f_i) if is_yes else sell_received_no(binary, mid, params, f_i)
                p_mid = get_new_p_yes_after_sell(binary, mid, X_mid, f_i) if is_yes else get_new_p_no_after_sell(binary, mid, X_mid, f_i)
                charge_mid = pool_tick * mid
                surplus_mid = X_mid - charge_mid  # For sells, we receive X_mid and pay charge_mid
                
                print(f"DEBUG: Iteration {iteration}: mid={mid}, X_mid={X_mid}, p_mid={p_mid}, charge={charge_mid}, surplus={surplus_mid}")
                
                # Check both constraints: price and profitability
                price_ok = p_mid >= pool_tick
                profit_ok = surplus_mid >= Decimal('0')
                
                if price_ok and profit_ok:
                    best_delta = mid
                    low = mid
                    print(f"DEBUG: Both constraints satisfied, setting low = {low}, best_delta = {best_delta}")
                else:
                    high = mid

        except (ValueError, ZeroDivisionError):
            # If we hit numerical issues, reduce the search space
            high = mid

            

    return best_delta

def update_pool_and_get_deltas(pool: Dict[str, any], delta: Decimal, charge: Decimal, is_buy: bool) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    original_volume = Decimal(str(pool['volume']))
    position_deltas = {}
    balance_deltas = {}  # For sells: + charge pro-rata; for buys: 0 here, rebates separate
    if original_volume <= Decimal('0'):
        return position_deltas, balance_deltas
    
    for user_id, share in list(pool['shares'].items()):
        user_share = Decimal(str(share))
        pro_rata_fraction = safe_divide(user_share, original_volume)
        
        if is_buy:
            # For buys: users get tokens (delta) pro-rata, pay USDC (charge) pro-rata
            position_deltas[user_id] = pro_rata_fraction * delta  # Tokens received
            balance_deltas[user_id] = -(pro_rata_fraction * charge)  # USDC paid (negative)
            # For buy pools, reduce user's share by their pro-rata portion of the USDC charge
            # since buy pool shares represent USDC amounts
            pool['shares'][user_id] = user_share - (pro_rata_fraction * charge)
        else:
            # For sells: users provide tokens (delta), get USDC (charge)
            position_deltas[user_id] = -(pro_rata_fraction * delta)  # Tokens sold (negative)
            balance_deltas[user_id] = pro_rata_fraction * charge  # USDC received (positive)
            # For sell pools, reduce user's share by their pro-rata portion of the token delta
            # since sell pool shares represent token amounts
            pool['shares'][user_id] = user_share - (pro_rata_fraction * delta)
        
        if pool['shares'][user_id] <= Decimal('0'):
            del pool['shares'][user_id]
    
    # Update pool volume according to LOB semantics:
    # - Buy pools store USDC volume: reduce by charge (USDC amount)
    # - Sell pools store token volume: reduce by delta (token amount)
    if is_buy:
        pool['volume'] = original_volume - charge  # USDC amount for buy pools
    else:
        pool['volume'] = original_volume - delta   # Token amount for sell pools
    
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
    
    # Apply diversion to binary state first (this changes V, L, and prices)
    if diversion != Decimal('0'):
        binary['V'] = float(Decimal(str(binary['V'])) + diversion)
        update_subsidies(state, params)
        print(f"DEBUG: After diversion - V={binary['V']}, L={binary['L']}, p_yes={get_p_yes(binary)}, p_no={get_p_no(binary)}")
    
    f_j = Decimal('1') - (len([b for b in state['binaries'] if b['active']]) - 1) * Decimal(str(params['zeta_start']))
    total_surplus = Decimal('0')
    events = []
    is_increase = diversion > Decimal('0')
    direction = 'buy' if is_increase else 'sell'
    yes_no_list = ['YES', 'NO']
    pools_filled = 0
    
    print(f"DEBUG: Auto-fill starting - diversion={diversion}, is_increase={is_increase}, direction={direction}")
    print(f"DEBUG: Binary {j} lob_pools structure: {binary['lob_pools']}")
    for yes_no in yes_no_list:
        pools = binary['lob_pools'][yes_no][direction]
        sorted_ticks = sorted(pools.keys(), reverse=is_increase)  # Desc for buy (high tick first), asc for sell (low first)
        print(f"DEBUG: Checking {yes_no} {direction} pools: {sorted_ticks}")
        for tick_int in sorted_ticks:
            if pools_filled >= params['af_max_pools']:
                break
            pool = pools[tick_int]
            if pool['volume'] <= 0:
                continue
            pool_tick = price_value(Decimal(tick_int) * params['tick_size'])
            current_p = get_p_yes(binary) if yes_no == 'YES' else get_p_no(binary)
            print(f"DEBUG: tick_int={tick_int}, pool_tick={pool_tick}, current_p={current_p}, is_increase={is_increase}")
            if (is_increase and pool_tick <= current_p) or (not is_increase and pool_tick >= current_p):
                print(f"DEBUG: Skipping pool - condition failed")
                continue
            print(f"DEBUG: Pool should be filled!")
            # For buys, find max delta such that cost <= pool volume
            # For sells, max delta is limited by pool volume directly
            if is_increase:
                # Binary search to find max delta where cost <= pool volume
                pool_volume = Decimal(str(pool['volume']))
                low_search, high_search = Decimal('0'), pool_volume  # Start with reasonable bounds
                for _ in range(10):
                    mid_search = (low_search + high_search) / Decimal('2')
                    try:
                        cost_mid = buy_cost_yes(binary, mid_search, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, mid_search, params, f_j)
                        if cost_mid <= pool_volume:
                            low_search = mid_search
                        else:
                            high_search = mid_search
                    except:
                        high_search = mid_search
                max_high = low_search
            else:
                max_high = Decimal(str(pool['volume']))
            print(f"DEBUG: max_high = {max_high}")
            delta = binary_search_max_delta(pool_tick, is_increase, yes_no == 'YES', binary, params, f_j, max_high)
            print(f"DEBUG: binary_search_max_delta returned delta = {delta}")
            
            # Debug: check if smaller deltas would be profitable
            for test_delta in [Decimal('10'), Decimal('50'), Decimal('100')]:
                if test_delta <= max_high:
                    test_cost = buy_cost_yes(binary, test_delta, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, test_delta, params, f_j)
                    test_charge = pool_tick * test_delta
                    test_surplus = test_charge - test_cost
                    print(f"DEBUG: test_delta={test_delta}, cost={test_cost}, charge={test_charge}, surplus={test_surplus}")
            
            if delta <= Decimal('0'):
                print(f"DEBUG: Delta <= 0, skipping")
                continue
            if is_increase:
                X = buy_cost_yes(binary, delta, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, delta, params, f_j)
                charge = usdc_amount(pool_tick * delta)
                surplus = charge - X  # For buys: what we charge minus what it costs
                print(f"DEBUG: Buy - X={X}, charge={charge}, surplus={surplus}")
            else:
                X = sell_received_yes(binary, delta, params, f_j) if yes_no == 'YES' else sell_received_no(binary, delta, params, f_j)
                charge = usdc_amount(pool_tick * delta)  # What we pay to pool holders
                surplus = X - charge  # For sells: what we receive minus what we pay
                print(f"DEBUG: Sell - X={X}, charge={charge}, surplus={surplus}")
            print(f"DEBUG: surplus = {surplus}")
            if surplus <= Decimal('0'):
                continue
            
            # Apply caps
            cap_delta = (params['af_cap_frac'] * abs(diversion)) / pool_tick
            print(f"DEBUG: cap_delta = {cap_delta}, delta = {delta}, af_cap_frac = {params['af_cap_frac']}, diversion = {diversion}")
            if delta > cap_delta:
                delta = cap_delta
                # Recalculate with capped delta
                if is_increase:
                    X = buy_cost_yes(binary, delta, params, f_j) if yes_no == 'YES' else buy_cost_no(binary, delta, params, f_j)
                    charge = pool_tick * delta
                    surplus = charge - X
                else:
                    X = sell_received_yes(binary, delta, params, f_j) if yes_no == 'YES' else sell_received_no(binary, delta, params, f_j)
                    charge = pool_tick * delta
                    surplus = X - charge
            
            print(f"DEBUG: After caps - delta = {delta}, surplus = {surplus}")
            if surplus <= Decimal('0'):
                print(f"DEBUG: Surplus <= 0 after caps, skipping")
                continue
            print(f"DEBUG: pools_filled = {pools_filled}, af_max_pools = {params['af_max_pools']}")
            if pools_filled >= params['af_max_pools']:
                print(f"DEBUG: Max pools reached, breaking")
                break
            original_volume = Decimal(str(pool['volume']))
            original_shares = dict(pool['shares'])  # Copy for rebates
            position_deltas, balance_deltas = update_pool_and_get_deltas(pool, delta, charge, is_increase)
            token_field = 'q_yes' if yes_no == 'YES' else 'q_no'
            if is_increase:
                binary[token_field] = float(Decimal(str(binary[token_field])) + delta)
            else:
                binary[token_field] = float(Decimal(str(binary[token_field])) - delta)
            system_surplus = params['sigma'] * surplus
            binary['V'] += float(system_surplus)
            update_subsidies(state, params)
            
            # Validate binary state after autofill mutations
            try:
                validate_binary_state(binary, params)
                validate_solvency_invariant(binary)
            except ValueError as e:
                # Rollback the autofill operation
                if is_increase:
                    binary[token_field] = float(Decimal(str(binary[token_field])) - delta)
                else:
                    binary[token_field] = float(Decimal(str(binary[token_field])) + delta)
                binary['V'] -= float(system_surplus)
                update_subsidies(state, params)  # Restore subsidies
                # Rollback pool changes
                pool['volume'] = original_volume
                pool['shares'] = original_shares
                raise ValueError(f"Autofill validation failed: {e}")
            apply_rebates(surplus, params['sigma'], original_volume, original_shares, balance_deltas)
            total_surplus += surplus
            print(f"DEBUG: Creating AUTO_FILL event for binary {j}, tick {tick_int}, delta {delta}")
            events.append({
                'type': 'AUTO_FILL',
                'binary_id': j,
                'is_yes': yes_no == 'YES',
                'tick': tick_int,
                'delta': delta,
                'surplus': surplus,
                'user_position_deltas': position_deltas,
                'user_balance_deltas': balance_deltas
            })
            pools_filled += 1
            print(f"DEBUG: Event created, pools_filled now = {pools_filled}")
    if total_surplus > Decimal(str(params['af_max_surplus'])) * (abs(diversion) / Decimal(str(params['zeta_start']))):
        total_surplus = Decimal(str(params['af_max_surplus'])) * (abs(diversion) / Decimal(str(params['zeta_start'])))
    return total_surplus, events