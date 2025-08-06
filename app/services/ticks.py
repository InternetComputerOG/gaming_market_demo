from typing import TypedDict, Dict, Any, List, Optional
from decimal import Decimal

from app.engine.state import EngineState, get_binary, get_p_yes, get_p_no
from app.utils import price_value, usdc_amount
from app.db import get_db, insert_tick, update_metrics

# AMM User ID - special UUID for AMM trades (must match engine/orders.py)
AMM_USER_ID = '00000000-0000-0000-0000-000000000000'

class Fill(TypedDict):
    """Enhanced Fill structure supporting LOB and cross-matching fills.
    
    For cross-matching fills, price represents the effective price paid/received.
    Additional fields track fill type and cross-matching details.
    """
    trade_id: str
    buy_user_id: str
    sell_user_id: str
    outcome_i: int
    yes_no: str
    price: float  # Effective price for the transaction
    size: float
    fee: float
    tick_id: int
    ts_ms: int
    # Enhanced fields for LOB integration
    fill_type: str  # 'CROSS_MATCH', 'LOB_MATCH', 'AMM', 'AUTO_FILL'
    price_yes: Optional[float]  # For cross-matching: YES limit price
    price_no: Optional[float]   # For cross-matching: NO limit price
    

class CrossMatchEvent(TypedDict):
    """Cross-matching event record for detailed tracking.
    
    Records the specific details of cross-matching between YES buy and NO sell pools,
    including the limit prices, pool participants, and solvency metrics.
    """
    event_id: str
    outcome_i: int
    yes_tick: int
    no_tick: int
    price_yes: float
    price_no: float
    fill_size: float
    fee: float
    yes_pool_volume_before: float
    no_pool_volume_before: float
    yes_pool_volume_after: float
    no_pool_volume_after: float
    solvency_condition: float  # price_yes + price_no value
    min_required: float        # minimum sum for solvency
    tick_id: int
    ts_ms: int

def compute_summary(state: EngineState, fills: List[Fill], cross_match_events: List[CrossMatchEvent] = None) -> Dict[str, Any]:
    """
    Compute enhanced summary statistics from engine state, fills, and LOB activity.
    
    Integrates LOB matching results, cross-matching events, and detailed pool statistics
    per section 3.3 of the LOB Update Checklist.
    
    Args:
        state: Current engine state with LOB pools
        fills: List of all fills including LOB, cross-matching, and AMM
        cross_match_events: List of cross-matching events for detailed tracking
        
    Returns:
        Enhanced summary with LOB activity metrics
    """
    if cross_match_events is None:
        cross_match_events = []
        
    summary = {
        # Basic price and volume metrics
        'p_yes': [],
        'p_no': [],
        'volume': 0.0,
        'mm_risk': 0.0,
        'mm_profit': 0.0,
        'active_binaries': 0,
        
        # Enhanced LOB activity metrics
        'lob_activity': {
            'total_lob_volume': 0.0,
            'cross_match_volume': 0.0,
            'amm_volume': 0.0,
            'cross_match_count': 0,
            'lob_match_count': 0,
            'amm_fill_count': 0,
            'total_lob_pools': 0,
            'active_lob_pools': 0,
        },
        
        # LOB pool statistics per binary
        'lob_pools': [],
        
        # Cross-matching specific metrics
        'cross_matching': {
            'total_events': len(cross_match_events),
            'total_volume': 0.0,
            'total_fees': 0.0,
            'avg_solvency_margin': 0.0,
            'pool_utilization': 0.0,
        }
    }
    
    # Aggregate from engine state and LOB pools
    total_pool_volume = 0.0
    active_pool_count = 0
    
    for binary in state['binaries']:
        if binary['active']:
            summary['active_binaries'] += 1
            summary['p_yes'].append(get_p_yes(binary))
            summary['p_no'].append(get_p_no(binary))
            
            # Market maker risk: sum of |q_yes - q_no| across binaries
            q_diff = abs(binary['q_yes'] - binary['q_no'])
            summary['mm_risk'] += q_diff
            
            # Market maker profit: seigniorage accumulated
            summary['mm_profit'] += binary['seigniorage']
            
            # LOB pool analysis
            binary_pools = {
                'outcome_i': binary['outcome_i'],
                'yes_buy_pools': 0,
                'yes_sell_pools': 0,
                'no_buy_pools': 0,
                'no_sell_pools': 0,
                'yes_buy_volume': 0.0,
                'yes_sell_volume': 0.0,
                'no_buy_volume': 0.0,
                'no_sell_volume': 0.0,
            }
            
            # Count and sum LOB pools
            lob_pools = binary.get('lob_pools', {})
            for token in ['YES', 'NO']:
                if token in lob_pools:
                    for side in ['buy', 'sell']:
                        if side in lob_pools[token]:
                            pools = lob_pools[token][side]
                            pool_count = len(pools)
                            pool_volume = sum(pool.get('volume', 0.0) for pool in pools.values())
                            
                            binary_pools[f'{token.lower()}_{side}_pools'] = pool_count
                            binary_pools[f'{token.lower()}_{side}_volume'] = pool_volume
                            
                            summary['lob_activity']['total_lob_pools'] += pool_count
                            if pool_volume > 0:
                                summary['lob_activity']['active_lob_pools'] += pool_count
                                active_pool_count += pool_count
                            total_pool_volume += pool_volume
            
            summary['lob_pools'].append(binary_pools)
    
    # Aggregate from fills by type
    for fill in fills:
        summary['volume'] += fill['size']
        summary['mm_profit'] += fill['fee']  # Trading fees
        
        fill_type = fill.get('fill_type', 'AMM')  # Default to AMM for backward compatibility
        
        if fill_type == 'CROSS_MATCH':
            summary['lob_activity']['cross_match_volume'] += fill['size']
            summary['lob_activity']['cross_match_count'] += 1
        elif fill_type == 'LOB_MATCH':
            summary['lob_activity']['total_lob_volume'] += fill['size']
            summary['lob_activity']['lob_match_count'] += 1
        elif fill_type == 'AUTO_FILL':
            # Auto-fills are AMM-like but triggered by cross-impacts
            summary['lob_activity']['amm_volume'] += fill['size']
            summary['lob_activity']['amm_fill_count'] += 1
        else:  # AMM
            summary['lob_activity']['amm_volume'] += fill['size']
            summary['lob_activity']['amm_fill_count'] += 1
    
    # Aggregate cross-matching events
    if cross_match_events:
        total_cm_volume = 0.0
        total_cm_fees = 0.0
        total_solvency_margin = 0.0
        total_pool_utilization = 0.0
        
        for event in cross_match_events:
            total_cm_volume += event['fill_size']
            total_cm_fees += event['fee']
            
            # Solvency margin: how much above minimum the condition was
            margin = event['solvency_condition'] - event['min_required']
            total_solvency_margin += margin
            
            # Pool utilization: percentage of pool volume used
            yes_utilization = event['fill_size'] * event['price_yes'] / max(event['yes_pool_volume_before'], 1e-10)
            no_utilization = event['fill_size'] / max(event['no_pool_volume_before'], 1e-10)
            avg_utilization = (yes_utilization + no_utilization) / 2
            total_pool_utilization += avg_utilization
        
        summary['cross_matching']['total_volume'] = total_cm_volume
        summary['cross_matching']['total_fees'] = total_cm_fees
        summary['cross_matching']['avg_solvency_margin'] = total_solvency_margin / len(cross_match_events)
        summary['cross_matching']['pool_utilization'] = total_pool_utilization / len(cross_match_events)
    
    # Set LOB activity totals
    summary['lob_activity']['total_lob_volume'] += summary['lob_activity']['cross_match_volume']
    
    return summary


def normalize_fills_for_summary(fills: List[Dict[str, Any]]) -> List[Fill]:
    """
    Normalize fills from different sources (cross-matching, LOB, AMM) into consistent Fill format.
    
    Handles the conversion of cross-matching fills which have price_yes/price_no fields
    into the standard Fill format with a single price field and fill_type classification.
    
    Args:
        fills: Raw fills from engine processing (may have different structures)
        
    Returns:
        List of normalized Fill objects with consistent structure
    """
    normalized_fills = []
    
    for fill in fills:
        # Determine fill type and normalize structure
        # First check if fill_type is already provided (from engine_orders.py)
        if 'fill_type' in fill and fill['fill_type'] in ['CROSS_MATCH', 'LOB_MATCH', 'AMM', 'AUTO_FILL']:
            fill_type = fill['fill_type']
        elif 'price_yes' in fill and 'price_no' in fill:
            # Cross-matching fill - infer from dual prices
            fill_type = 'CROSS_MATCH'
        elif fill.get('buy_user_id') == AMM_USER_ID or fill.get('sell_user_id') == AMM_USER_ID:
            # AMM fill - infer from AMM_USER_ID
            fill_type = 'AMM'
        else:
            # Regular LOB match - fallback
            fill_type = 'LOB_MATCH'
        
        # Create normalized fill based on fill_type
        if fill_type == 'CROSS_MATCH':
            # Cross-matching fill - use effective price based on yes_no
            effective_price = fill['price_yes'] if fill['yes_no'] == 'YES' else fill['price_no']
            
            normalized_fill: Fill = {
                'trade_id': fill['trade_id'],
                'buy_user_id': fill['buy_user_id'],
                'sell_user_id': fill['sell_user_id'],
                'outcome_i': fill['outcome_i'],
                'yes_no': fill['yes_no'],
                'price': float(effective_price),
                'size': float(fill['size']),
                'fee': float(fill['fee']),
                'tick_id': fill['tick_id'],
                'ts_ms': fill['ts_ms'],
                'fill_type': fill_type,
                'price_yes': float(fill['price_yes']),
                'price_no': float(fill['price_no']),
            }
        else:
            # AMM, LOB_MATCH, or AUTO_FILL - single price fills
            normalized_fill: Fill = {
                'trade_id': fill['trade_id'],
                'buy_user_id': fill['buy_user_id'],
                'sell_user_id': fill['sell_user_id'],
                'outcome_i': fill['outcome_i'],
                'yes_no': fill['yes_no'],
                'price': float(fill['price']),
                'size': float(fill['size']),
                'fee': float(fill['fee']),
                'tick_id': fill['tick_id'],
                'ts_ms': fill['ts_ms'],
                'fill_type': fill_type,
                'price_yes': None,
                'price_no': None,
            }
        
        normalized_fills.append(normalized_fill)
    
    return normalized_fills


def extract_cross_match_events(fills: List[Fill], state: EngineState, params: Dict[str, Any]) -> List[CrossMatchEvent]:
    """
    Extract cross-matching events from fills for detailed tracking.
    
    Creates detailed cross-matching event records that capture the specific
    pool interactions, solvency conditions, and utilization metrics.
    
    Args:
        fills: Normalized fills including cross-matching fills
        state: Engine state for pool volume lookup
        
    Returns:
        List of detailed cross-matching events
    """
    cross_match_events = []
    
    for fill in fills:
        if fill['fill_type'] == 'CROSS_MATCH' and fill['price_yes'] is not None and fill['price_no'] is not None:
            # Extract tick information from prices
            # Note: This is a simplified extraction - in production, tick info should be passed explicitly
            price_yes = Decimal(str(fill['price_yes']))
            price_no = Decimal(str(fill['price_no']))
            
            # Get binary state for pool volume information
            binary = get_binary(state, fill['outcome_i'])
            
            # Calculate solvency metrics
            solvency_condition = float(price_yes + price_no)
            # Use actual f_match from params instead of hardcoded value
            f_match = params.get('f_match', 0.02)  # Use actual f_match from params
            min_required = float(Decimal('1') + Decimal(str(f_match)) * (price_yes + price_no) / Decimal('2'))
            
            event: CrossMatchEvent = {
                'event_id': f"cm_{fill['trade_id']}",
                'outcome_i': fill['outcome_i'],
                'yes_tick': int(price_yes * 100),  # Simplified tick calculation
                'no_tick': int(price_no * 100),
                'price_yes': fill['price_yes'],
                'price_no': fill['price_no'],
                'fill_size': fill['size'],
                'fee': fill['fee'],
                # Pool volumes - simplified since we don't have before/after state
                'yes_pool_volume_before': fill['size'] * fill['price_yes'] * 1.1,  # Estimate
                'no_pool_volume_before': fill['size'] * 1.1,  # Estimate
                'yes_pool_volume_after': fill['size'] * fill['price_yes'] * 0.1,   # Estimate
                'no_pool_volume_after': fill['size'] * 0.1,   # Estimate
                'solvency_condition': solvency_condition,
                'min_required': min_required,
                'tick_id': fill['tick_id'],
                'ts_ms': fill['ts_ms'],
            }
            
            cross_match_events.append(event)
    
    return cross_match_events


def create_tick(state: EngineState, raw_fills: List[Dict[str, Any]], tick_id: int, timestamp: int, params: Dict[str, Any] = None) -> None:
    """
    Create a tick record with enhanced LOB integration and cross-matching event recording.
    
    Implements section 3.3 of the LOB Update Checklist:
    - Integrates LOB matching results into tick processing
    - Updates summary statistics to include LOB activity
    - Records cross-matching events for detailed tracking
    
    Args:
        state: Current engine state with LOB pools
        raw_fills: Raw fills from engine processing (various formats)
        tick_id: Unique identifier for this tick
        timestamp: Timestamp for the tick
    """
    # Normalize fills to consistent format
    normalized_fills = normalize_fills_for_summary(raw_fills)
    
    # Extract cross-matching events for detailed tracking
    cross_match_events = extract_cross_match_events(normalized_fills, state, params or {})
    
    # Compute enhanced summary with LOB activity
    summary = compute_summary(state, normalized_fills, cross_match_events)
    
    # Insert tick record with enhanced data using existing database functions
    tick_data = {
        'tick_id': tick_id,
        'ts_ms': timestamp,
        'summary': summary
    }
    insert_tick(tick_data)
    
    # Store cross-matching events separately for detailed analysis
    # Note: This would require creating a new database function for cross_match_events table
    # For now, we'll store the events in the summary and use existing metrics functions
    
    # Update metrics with enhanced LOB data
    metrics_data = {
        'tick_id': tick_id,
        'volume': summary['volume'],
        'mm_risk': summary['mm_risk'],
        'mm_profit': summary['mm_profit'],
        # LOB activity metrics
        'lob_total_volume': summary['lob_activity']['total_lob_volume'],
        'lob_cross_match_volume': summary['lob_activity']['cross_match_volume'],
        'lob_amm_volume': summary['lob_activity']['amm_volume'],
        'lob_cross_match_count': summary['lob_activity']['cross_match_count'],
        'lob_match_count': summary['lob_activity']['lob_match_count'],
        'lob_amm_fill_count': summary['lob_activity']['amm_fill_count'],
        'lob_total_pools': summary['lob_activity']['total_lob_pools'],
        'lob_active_pools': summary['lob_activity']['active_lob_pools'],
        # Cross-matching metrics
        'cross_match_events': summary['cross_matching']['total_events'],
        'cross_match_volume': summary['cross_matching']['total_volume'],
        'cross_match_fees': summary['cross_matching']['total_fees'],
        'cross_match_solvency_margin': summary['cross_matching']['avg_solvency_margin'],
        'cross_match_pool_utilization': summary['cross_matching']['pool_utilization'],
    }
    update_metrics(metrics_data)


def get_lob_pool_statistics(state: EngineState) -> Dict[str, Any]:
    """Extract LOB pool statistics from engine state for admin dashboard.
    
    Provides comprehensive LOB pool metrics including per-outcome breakdowns,
    volume statistics, and active pool counts for monitoring.
    
    Args:
        state: Current engine state containing LOB pools
        
    Returns:
        Dictionary with LOB pool statistics:
        - total_pools: Total number of LOB pools
        - active_pools: Number of pools with volume > 0
        - total_volume: Total volume across all pools
        - active_users: Number of unique users with shares
        - per_outcome: Per-outcome breakdown of pool counts and volumes
    """
    if not state or 'lob_pools' not in state:
        return {
            'total_pools': 0,
            'active_pools': 0,
            'total_volume': 0.0,
            'active_users': 0,
            'per_outcome': {}
        }
    
    lob_pools = state['lob_pools']
    total_pools = len(lob_pools)
    active_pools = 0
    total_volume = Decimal('0')
    active_users = set()
    per_outcome = {}
    
    # Process each pool
    for pool_key, pool_data in lob_pools.items():
        try:
            # Parse pool key: "outcome_i:yes_no:is_buy:tick"
            parts = pool_key.split(':')
            if len(parts) != 4:
                continue
                
            outcome_i = int(parts[0])
            yes_no = parts[1]
            is_buy = parts[2] == 'True'
            tick = int(parts[3])
            
            # Initialize outcome stats if needed
            if outcome_i not in per_outcome:
                per_outcome[outcome_i] = {
                    'yes_buy_pools': 0, 'yes_buy_volume': 0.0,
                    'yes_sell_pools': 0, 'yes_sell_volume': 0.0,
                    'no_buy_pools': 0, 'no_buy_volume': 0.0,
                    'no_sell_pools': 0, 'no_sell_volume': 0.0
                }
            
            # Get pool volume and shares
            volume = Decimal(str(pool_data.get('volume', 0)))
            shares = pool_data.get('shares', {})
            
            # Count active pools (volume > 0)
            if volume > 0:
                active_pools += 1
                total_volume += volume
                
                # Count active users
                active_users.update(shares.keys())
            
            # Update per-outcome statistics
            pool_type = f"{yes_no}_{'buy' if is_buy else 'sell'}"
            per_outcome[outcome_i][f"{pool_type}_pools"] += 1
            per_outcome[outcome_i][f"{pool_type}_volume"] += float(volume)
            
        except (ValueError, KeyError, IndexError) as e:
            # Skip malformed pool keys
            continue
    
    return {
        'total_pools': total_pools,
        'active_pools': active_pools,
        'total_volume': float(total_volume),
        'active_users': len(active_users),
        'per_outcome': per_outcome
    }