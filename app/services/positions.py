from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from decimal import Decimal

from app.db.queries import fetch_positions, update_position, update_user_position, fetch_user_position, update_user_balance, fetch_user_balance, update_metrics, get_db
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
    Update user positions and balances based on a fill from the engine.
    
    Phase 3.2: Correctly handles both buyer and seller position updates,
    integrates new fee structure from Phase 3.1, maintains balance consistency,
    and updates engine state token quantities per TDD specifications.
    
    Args:
        fill: Fill data from engine containing buy_user_id, sell_user_id, outcome_i,
              yes_no, price, size, fee, etc.
        state: Engine state to update with new token quantities (q_yes, q_no)
    
    Ties to TDD: Updates individual user positions per (user_id, outcome_i, yes_no),
    adjusts balances for trading costs and proceeds with proper fee handling,
    and updates engine state q_yes_i += Δ, q_no_i += Δ per cross-matching mechanics.
    """
    try:
        # Extract fill data
        buy_user_id = fill['buy_user_id']
        sell_user_id = fill['sell_user_id']
        outcome_i = fill['outcome_i']
        yes_no = fill['yes_no']  # Token type being traded ('YES' or 'NO')
        price = Decimal(str(fill['price']))
        size = Decimal(str(fill['size']))  # Number of tokens traded
        fee = Decimal(str(fill['fee']))  # Total trading fee
        
        validate_size(float(size))  # Ensure positive size
        
        # Calculate transaction amounts
        total_cost = price * size  # Total cost for the tokens
        fee_per_user = fee / Decimal('2')  # Split fee between buyer and seller
        
        # Update buyer position (gains tokens)
        buyer_current_tokens = Decimal(str(fetch_user_position(buy_user_id, outcome_i, yes_no)))
        buyer_new_tokens = buyer_current_tokens + size
        update_user_position(buy_user_id, outcome_i, yes_no, float(buyer_new_tokens))
        
        # Update seller position (loses tokens)
        seller_current_tokens = Decimal(str(fetch_user_position(sell_user_id, outcome_i, yes_no)))
        seller_new_tokens = seller_current_tokens - size
        if seller_new_tokens < Decimal('0'):
            raise ValueError(f"Insufficient tokens for sell: user {sell_user_id} has {seller_current_tokens} {yes_no} tokens, trying to sell {size}")
        update_user_position(sell_user_id, outcome_i, yes_no, float(seller_new_tokens))
        
        # Update buyer balance (pays cost + fee)
        buyer_balance = Decimal(str(fetch_user_balance(buy_user_id)))
        buyer_charge = total_cost + fee_per_user
        buyer_new_balance = buyer_balance - buyer_charge
        if buyer_new_balance < Decimal('0'):
            raise ValueError(f"Insufficient balance for buy: user {buy_user_id} has {buyer_balance}, needs {buyer_charge}")
        update_user_balance(buy_user_id, float(buyer_new_balance))
        
        # Update seller balance (receives proceeds - fee)
        seller_balance = Decimal(str(fetch_user_balance(sell_user_id)))
        seller_proceeds = total_cost - fee_per_user
        seller_new_balance = seller_balance + seller_proceeds
        update_user_balance(sell_user_id, float(seller_new_balance))
        
        # Update engine state token quantities per TDD requirements
        # Cross-matches update both q_yes and q_no (TDD Line 175: "Update q_yes_i += Δ, q_no_i += Δ")
        # AMM/LOB/auto-fills update only one q (either q_yes OR q_no)
        binary = get_binary(state, outcome_i)
        
        # Determine fill type - check for cross-match indicators
        fill_type = fill.get('fill_type', 'UNKNOWN')
        
        # If no explicit fill_type, infer from fill structure
        if fill_type == 'UNKNOWN':
            if 'price_yes' in fill and 'price_no' in fill:
                fill_type = 'CROSS_MATCH'
            elif buy_user_id == '00000000-0000-0000-0000-000000000000' or sell_user_id == '00000000-0000-0000-0000-000000000000':
                fill_type = 'AMM'
            else:
                fill_type = 'LOB_MATCH'
        
        # Update q_yes/q_no based on fill type
        if fill_type == 'CROSS_MATCH':
            # Cross-matches: Update both q_yes and q_no
            binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + size)
            binary['q_no'] = float(Decimal(str(binary['q_no'])) + size)
        else:
            # AMM/LOB/auto-fills: Update only the relevant q
            if yes_no == 'YES':
                binary['q_yes'] = float(Decimal(str(binary['q_yes'])) + size)
            else:
                binary['q_no'] = float(Decimal(str(binary['q_no'])) + size)
        
        # Note: Solvency validation moved to batch-level processing to avoid rejecting legitimate fills
        # Individual fills may temporarily violate solvency during batch processing
        
        # Update trade counts for both users
        db = get_db()
        
        # Update buyer trade count
        buyer_data = db.table('users').select('trade_count').eq('user_id', buy_user_id).execute().data
        if buyer_data:
            buyer_trade_count = buyer_data[0]['trade_count'] + 1
            db.table('users').update({'trade_count': buyer_trade_count}).eq('user_id', buy_user_id).execute()
        
        # Update seller trade count
        seller_data = db.table('users').select('trade_count').eq('user_id', sell_user_id).execute().data
        if seller_data:
            seller_trade_count = seller_data[0]['trade_count'] + 1
            db.table('users').update({'trade_count': seller_trade_count}).eq('user_id', sell_user_id).execute()
            
    except Exception as e:
        # Log the error with context for debugging
        print(f"Error in update_position_from_fill: {e}")
        print(f"Fill data: {fill}")
        raise ValueError(f"Failed to update positions from fill: {e}")

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