from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from decimal import Decimal

from app.db.queries import fetch_positions, update_position, update_metrics, get_db
from app.engine.state import EngineState, BinaryState, get_binary
from app.utils import usdc_amount, validate_balance_buy, validate_balance_sell, validate_size, safe_divide

class Position(TypedDict):
    position_id: str
    user_id: str
    outcome_i: int
    yes_no: str
    tokens: Decimal

def fetch_user_positions(user_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all positions for a given user from the DB.
    Ties to TDD: Retrieves actual q_yes/q_no per binary for the user.
    """
    positions = fetch_positions(user_id=user_id)
    return [
        {
            'position_id': pos['position_id'],
            'user_id': pos['user_id'],
            'outcome_i': pos['outcome_i'],
            'yes_no': pos['yes_no'],
            'tokens': usdc_amount(pos['tokens'])
        } for pos in positions
    ]

def update_position_from_fill(fill: Dict[str, Any], state: EngineState) -> None:
    """
    Update user position and engine state based on a fill.
    Ties to TDD: Adjusts actual q_yes/q_no in state and DB post-fill; preserves q < L_i via engine invariants.
    Handles both buy (increase tokens) and sell (decrease tokens).
    """
    user_id = fill['buy_user_id'] if fill['yes_no'] == 'YES' else fill['sell_user_id']  # Simplified; adjust per fill type
    outcome_i = fill['outcome_i']
    yes_no = fill['yes_no']
    size = usdc_amount(fill['size'])
    is_buy = 'buy_user_id' in fill  # Detect based on fill keys; assume buy for buyer

    binary = get_binary(state, outcome_i)
    if yes_no == 'YES':
        current_tokens = binary['q_yes']
    else:
        current_tokens = binary['q_no']

    if is_buy:
        new_tokens = current_tokens + size
        validate_size(size)  # Ensure positive size
    else:
        new_tokens = current_tokens - size
        if new_tokens < Decimal('0'):
            raise ValueError("Insufficient tokens for sell")

    # Update engine state (actual q, not virtual)
    if yes_no == 'YES':
        binary['q_yes'] = new_tokens
    else:
        binary['q_no'] = new_tokens

    # DB update
    update_position(user_id, outcome_i, float(binary['q_yes']), float(binary['q_no']))

    # Update user metrics (trade_count increment)
    db = get_db()
    user_data = db.table('users').select('*').eq('user_id', user_id).execute().data[0]
    new_trade_count = user_data['trade_count'] + 1
    db.table('users').update({'trade_count': new_trade_count}).eq('user_id', user_id).execute()

def apply_payouts(resolution_data: Dict[str, Any], state: EngineState) -> None:
    """
    Apply payouts from resolution, updating balances and zeroing positions.
    Ties to TDD: Payouts based on actual q_yes/q_no (excluding virtual); handles multi-res eliminations by burning positions for eliminated outcomes.
    For final: Distribute unfilled limits pro-rata.
    """
    payouts = resolution_data.get('payouts', {})  # {user_id: amount}
    is_final = resolution_data.get('is_final', False)
    elim_outcomes = resolution_data.get('elim_outcomes', [])

    db = get_db()

    for user_id, payout_amount in payouts.items():
        payout = usdc_amount(payout_amount)
        update_balance(user_id, payout)

        # Update net_pnl
        user_data = db.table('users').select('*').eq('user_id', user_id).execute().data[0]
        new_net_pnl = usdc_amount(user_data['net_pnl']) + payout
        db.table('users').update({'net_pnl': float(new_net_pnl)}).eq('user_id', user_id).execute()

    # Zero positions for eliminated outcomes
    for outcome_i in elim_outcomes:
        binary = get_binary(state, outcome_i)
        binary['q_yes'] = Decimal('0')
        binary['q_no'] = Decimal('0')
        binary['active'] = False

        # DB: Zero all positions for this outcome
        db.table('positions').update({'tokens': 0}).eq('outcome_i', outcome_i).execute()

    if is_final:
        # Distribute unfilled limits pro-rata (simplified: assume from lob_pools, add to balances)
        # Fetch lob_pools, compute pro-rata returns, update balances
        pass  # Implement based on lob_matching integration

    # Update metrics if needed
    update_metrics({'mm_profit': float(sum(binary['seigniorage'] for binary in state['binaries']))})

def deduct_gas(user_id: str, gas_fee: Decimal) -> None:
    """
    Deduct flat gas fee from user balance on order submission (even if rejected).
    Ties to impl plan: Gas deducted regardless of success; track in metrics.
    """
    gas_fee = usdc_amount(gas_fee)
    if gas_fee <= Decimal('0'):
        return

    db = get_db()
    user_data = db.table('users').select('balance').eq('user_id', user_id).execute().data[0]
    current_balance = usdc_amount(user_data['balance'])
    if current_balance < gas_fee:
        raise ValueError("Insufficient balance for gas fee")

    new_balance = current_balance - gas_fee
    db.table('users').update({'balance': float(new_balance)}).eq('user_id', user_id).execute()

    # Track gas in metrics (e.g., add to total_gas)
    metrics = db.table('metrics').select('*').execute().data[-1] if db.table('metrics').select('*').execute().data else {'total_gas': 0}
    new_total_gas = usdc_amount(metrics.get('total_gas', 0)) + gas_fee
    update_metrics({'total_gas': float(new_total_gas)})

def update_balance(user_id: str, delta: Decimal) -> None:
    """
    Update user balance by delta (positive or negative).
    Ties to TDD: Used for proceeds/costs/payouts; validates non-negative post-update.
    """
    delta = usdc_amount(delta)
    db = get_db()
    user_data = db.table('users').select('balance').eq('user_id', user_id).execute().data[0]
    current_balance = usdc_amount(user_data['balance'])
    new_balance = current_balance + delta
    if new_balance < Decimal('0'):
        raise ValueError("Balance cannot go negative")

    db.table('users').update({'balance': float(new_balance)}).eq('user_id', user_id).execute()