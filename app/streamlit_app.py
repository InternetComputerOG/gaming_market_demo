import streamlit as st
import time
import json
from uuid import uuid4
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime

from app.config import get_supabase_client
from app.utils import get_current_ms, usdc_amount, price_value, validate_size, validate_price, validate_limit_price_bounds
from app.db.queries import load_config, insert_user, fetch_user_balance, fetch_positions, fetch_user_orders, get_current_tick, fetch_pools, fetch_engine_state
from app.services.orders import submit_order, cancel_order, get_user_orders, estimate_slippage
from app.services.positions import fetch_user_positions
# Realtime functionality now handled via fragments
from app.engine.state import get_binary, get_p_yes, get_p_no

client = get_supabase_client()

# System users to filter out from leaderboards and rankings
SYSTEM_USERS = {
    'AMM System',
    'Limit YES Pool', 
    'Limit NO Pool',
    'Limit Pool',
    'Market User'
}

def filter_system_users(users):
    """Filter out system users from user list"""
    return [user for user in users if user.get('display_name', '') not in SYSTEM_USERS]

if 'user_id' not in st.session_state:
    display_name = st.text_input("Enter display name", key="display-name-input")
    if st.button("Join", key="join-button"):
        config = load_config()
        user_id = str(uuid4())
        insert_user(user_id, display_name, float(config['params']['starting_balance']))
        st.session_state['user_id'] = user_id
        st.session_state['display_name'] = display_name
        st.session_state['last_tick'] = 0
        st.session_state['last_check'] = time.time()
        st.rerun()

if 'user_id' not in st.session_state:
    st.stop()

user_id = st.session_state['user_id']
config = load_config()
status = config['status']
params: Dict[str, Any] = config['params']

# Fragment-based realtime updates - no need for manual realtime containers

# Fragment-based realtime updates using Streamlit's native approach
# Initialize fragment update timers
if 'last_price_update' not in st.session_state:
    st.session_state.last_price_update = 0
if 'last_leaderboard_update' not in st.session_state:
    st.session_state.last_leaderboard_update = 0
if 'realtime_user_count' not in st.session_state:
    st.session_state.realtime_user_count = 0


# Get batch interval from config for fragment update timing
batch_interval_ms = params.get('batch_interval_ms', 5000)
batch_interval_s = batch_interval_ms / 1000.0

# Fragment for current market prices - must be defined at module scope
@st.fragment(run_every=batch_interval_s)
def price_fragment(outcome_i):
    try:
        current_p_yes, current_p_no = get_current_prices(outcome_i)
        
        # Display current market prices
        price_col1, price_col2 = st.columns(2)
        with price_col1:
            st.metric("YES Market Price", f"${current_p_yes:.4f}", delta=None)
        with price_col2:
            st.metric("NO Market Price", f"${current_p_no:.4f}", delta=None)
        
        # Spread calculation
        spread = abs(current_p_yes - current_p_no)
        st.markdown(f"**Spread:** ${spread:.4f}")
        
        return current_p_yes, current_p_no
    except Exception as e:
        st.warning("Could not load current market prices")
        return None, None

# Fragment for portfolio data - updates at batch interval
@st.fragment(run_every=batch_interval_s)
def portfolio_fragment(user_id):
    # Check if we have cached data and it's recent
    cache_key = f'portfolio_cache_{user_id}'
    current_time = time.time()
    
    # Always refresh if cache is older than batch interval to catch fills/ticks
    if (cache_key in st.session_state and 
        'timestamp' in st.session_state[cache_key] and 
        current_time - st.session_state[cache_key]['timestamp'] < batch_interval_s):
        return st.session_state[cache_key]['data']
    
    try:
        positions = fetch_user_positions(user_id)
        orders = get_user_orders(user_id, 'OPEN')
        
        result = {
            'success': True,
            'positions': positions,
            'orders': orders,
            'error': None
        }
        
        # Cache the result
        st.session_state[cache_key] = {
            'data': result,
            'timestamp': current_time
        }
        
        return result
    except Exception as e:
        error_result = {
            'success': False,
            'positions': [],
            'orders': [],
            'error': str(e)
        }
        
        # Don't cache errors, but return them
        return error_result

# Helper function for getting current prices (used by price fragment)
def get_current_prices(outcome_i):
    """Get current YES and NO prices for an outcome"""
    engine_state = fetch_engine_state()
    binary = get_binary(engine_state, outcome_i)
    current_p_yes = get_p_yes(binary)
    current_p_no = get_p_no(binary)
    return current_p_yes, current_p_no

# Fragment for waiting room status checking - only runs when status is DRAFT
@st.fragment(run_every=3)  # Check every 3 seconds
def waiting_room_status_fragment():
    """Fragment to check demo status and transition from waiting room"""
    try:
        fresh_config = load_config()
        current_status = fresh_config['status']
        
        # Update session state for UI display
        if 'status_check_count' not in st.session_state:
            st.session_state.status_check_count = 0
        st.session_state.status_check_count += 1
        st.session_state.last_status_check = time.time()
        
        # If status changed from DRAFT, trigger transition
        if current_status != 'DRAFT':
            st.success("🚀 Demo is starting! Redirecting to trading interface...")
            time.sleep(1)  # Brief pause for user to see the message
            st.rerun()
        
        return {
            'success': True,
            'status': current_status,
            'check_count': st.session_state.status_check_count,
            'last_check': st.session_state.last_status_check
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'status': 'DRAFT',
            'check_count': st.session_state.get('status_check_count', 0),
            'last_check': st.session_state.get('last_status_check', time.time())
        }

# Enhanced waiting room with fragment-based status updates
if status == 'DRAFT':
    st.title("🎮 Gaming Market Demo")
    st.header("⏳ Waiting Room")
    
    # Get status check data from fragment
    status_data = waiting_room_status_fragment()
    
    # Show joined users count with realtime updates
    try:
        # Check if we have realtime user count
        if st.session_state['realtime_user_count'] > 0:
            user_count = st.session_state['realtime_user_count']
            users = client.table('users').select('*').execute().data  # Still need this for player list
        else:
            # Fallback to static fetch and store in realtime cache
            users = client.table('users').select('*').execute().data
            user_count = len(users)
            st.session_state['realtime_user_count'] = user_count
        
        # Display user count
        st.markdown(f'👥 **{user_count} players joined** - Waiting for admin to start the demo...')
        
    except Exception as e:
        st.error(f"⚠️ Connection issue: {str(e)}")
        user_count = 0
        users = []
    
    # Manual refresh button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔄 Check Status", type="primary"):
            # Reset status check count and force immediate rerun
            if 'status_check_count' in st.session_state:
                st.session_state.status_check_count = 0
            st.rerun()
    
    # Show current players
    if users:
        st.subheader("👥 Joined Players")
        player_names = [user['display_name'] for user in users]
        # Display players in a nice grid
        cols = st.columns(min(3, len(player_names)))
        for i, name in enumerate(player_names):
            with cols[i % len(cols)]:
                st.write(f"• {name}")
    
    # Status notification area
    with st.container():
        st.markdown("---")
        col_status1, col_status2 = st.columns(2)
        with col_status1:
            if status_data['success']:
                st.caption(f"🔄 Auto-checking every 3 seconds... (Check #{status_data['check_count']})")
            else:
                st.caption("⚠️ Auto-check error - Use manual check button")
        with col_status2:
            if status_data['success']:
                time_since_last_check = time.time() - status_data['last_check']
                if time_since_last_check < 1:
                    st.caption("🟢 Just checked - Status: DRAFT")
                else:
                    st.caption(f"⏱️ Next check in {max(0, 3 - int(time_since_last_check))} seconds")
            else:
                st.caption(f"❌ Error: {status_data.get('error', 'Unknown error')}")
    
    st.stop()

if status == 'FROZEN':
    st.warning("⏸️ **Trading is currently frozen**")
    st.info("The admin has temporarily paused trading. Please wait for trading to resume.")
    
    # Auto-refresh for frozen status too
    if 'last_frozen_check' not in st.session_state:
        st.session_state.last_frozen_check = time.time()
    
    current_time = time.time()
    if current_time - st.session_state.last_frozen_check > 2:
        st.session_state.last_frozen_check = current_time
        fresh_config = load_config()
        if fresh_config['status'] != 'FROZEN':
            st.success("✅ Trading has resumed!")
            time.sleep(1)
            st.rerun()
    
    if st.button("🔄 Check Status"):
        st.rerun()
    st.stop()

if status == 'RESOLVED':
    st.write("Market resolved")
    users = client.table('users').select('*').execute().data
    
    # Filter out system users
    users = filter_system_users(users)
    
    rankings = sorted(users, key=lambda u: float(u['net_pnl']), reverse=True)
    starting_balance = params.get('starting_balance', 0)
    st.table([{ 'Name': r['display_name'], 'Net PNL': float(r['net_pnl']), '% Gain': float(r['net_pnl']) / float(starting_balance) * 100 if starting_balance else 0, 'Trades': r['trade_count'] } for r in rankings])
    from app.scripts.generate_graph import generate_graph
    fig = generate_graph()
    st.pyplot(fig)
    st.stop()

current_ms = get_current_ms()

# Simplified and robust start time calculation
start_ms = None

# Try to get start_ts_ms from params first (where timer_service stores it)
if 'params' in config and config['params'] and 'start_ts_ms' in config['params']:
    start_ms = int(config['params']['start_ts_ms'])
# Fallback to top-level start_ts_ms
elif 'start_ts_ms' in config and config['start_ts_ms']:
    start_ms = int(config['start_ts_ms'])
# Fallback to start_ts if present
elif 'start_ts' in config and config['start_ts']:
    try:
        # Simple ISO timestamp parsing
        timestamp_str = config['start_ts'].replace('Z', '+00:00')
        start_dt = datetime.fromisoformat(timestamp_str)
        start_ms = int(start_dt.timestamp() * 1000)
    except Exception as e:
        print(f"Error parsing start_ts: {e}")
        start_ms = None

# If no valid start time found, show "Not Started" message
if start_ms is None:
    st.metric("Time to End", "Demo not started")
else:
    # Calculate time remaining
    elapsed_ms = current_ms - start_ms
    total_duration_ms = params.get('total_duration', 0) * 1000
    
    if total_duration_ms > 0:
        time_to_end = max(0, (total_duration_ms - elapsed_ms) / 1000)
        
        # Create a placeholder for the countdown timer
        countdown_placeholder = st.empty()
        
        # Format time nicely
        def format_time(seconds):
            mins, secs = divmod(int(seconds), 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                return f"{hours:02d}:{mins:02d}:{secs:02d}"
            else:
                return f"{mins:02d}:{secs:02d}"
        
        # Fragment-based countdown timer - updates every second
        @st.fragment(run_every=1.0)  # Update every 1 second
        def countdown_fragment():
            # Recalculate current time for accurate countdown
            current_ms_live = get_current_ms()
            elapsed_ms_live = current_ms_live - start_ms
            time_to_end_live = max(0, (total_duration_ms - elapsed_ms_live) / 1000)
            progress_live = min(1.0, elapsed_ms_live / total_duration_ms) if total_duration_ms > 0 else 0
            
            # Display countdown with live updates
            col1, col2 = st.columns([3, 1])
            with col1:
                st.metric("Time Remaining", format_time(time_to_end_live))
                if total_duration_ms > 0:
                    st.progress(progress_live, text=f"Progress: {int(progress_live * 100)}%")
            with col2:
                st.metric("Elapsed", format_time(elapsed_ms_live / 1000))
            
            return time_to_end_live, progress_live
        
        # Call the countdown fragment for live updates
        time_remaining, current_progress = countdown_fragment()
    else:
        st.metric("Time to End", "Duration not configured")

# Legacy polling mechanism removed - fragments handle all realtime updates now
# No need for manual st.rerun() calls as fragments update automatically

# Fragment for user balance - updates at batch interval
@st.fragment(run_every=batch_interval_s)
def balance_fragment():
    # Check if we have cached data and it's recent
    cache_key = f'balance_cache_{user_id}'
    current_time = time.time()
    
    if (cache_key in st.session_state and 
        'timestamp' in st.session_state[cache_key] and 
        current_time - st.session_state[cache_key]['timestamp'] < batch_interval_s):
        cached_balance = st.session_state[cache_key]['data']
        st.metric("Balance", f"${cached_balance:.2f}")
        return cached_balance
    
    try:
        balance = fetch_user_balance(user_id)
        balance_float = float(balance)
        
        # Cache the result
        st.session_state[cache_key] = {
            'data': balance_float,
            'timestamp': current_time
        }
        
        st.metric("Balance", f"${balance_float:.2f}")
        return balance_float
    except Exception as e:
        st.warning(f"Could not load balance: {str(e)}")
        return 0

balance = balance_fragment()

# Fragment for leaderboard - updates at 2x batch interval (less frequent)
@st.fragment(run_every=batch_interval_s * 2)
def leaderboard_fragment():
    try:
        users = client.table('users').select('*').execute().data
        
        # Filter out system users
        users = filter_system_users(users)
        
        # Calculate total portfolio value including current market value of tokens
        users_with_portfolio_value = []
        for user in users:
            total_value = float(user['balance']) + float(user['net_pnl'])
            
            # Add current market value of held tokens
            try:
                positions = client.table('positions').select('*').eq('user_id', user['user_id']).execute().data
                for p in positions:
                    if float(p['tokens']) > 0:
                        outcome_i = int(p['outcome_i'])
                        current_p_yes, current_p_no = get_current_prices(outcome_i)
                        if current_p_yes is not None and current_p_no is not None:
                            if p['yes_no'] == 'YES':
                                total_value += float(p['tokens']) * current_p_yes
                            else:
                                total_value += float(p['tokens']) * current_p_no
                        else:
                            # Fallback to $0.50 if prices unavailable
                            total_value += float(p['tokens']) * 0.5
            except Exception:
                # If we can't get positions, just use balance + net_pnl
                pass
            
            user_copy = user.copy()
            user_copy['total_portfolio_value'] = total_value
            users_with_portfolio_value.append(user_copy)
        
        leaderboard = sorted(users_with_portfolio_value, key=lambda u: u['total_portfolio_value'], reverse=True)[:5]
        
        # Return data instead of writing to sidebar directly
        return {
            'success': True,
            'leaderboard': leaderboard,
            'user_count': len(users),
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'leaderboard': [],
            'user_count': 0,
            'error': str(e)
        }

# Call fragment within sidebar context
with st.sidebar:
    st.header("Leaderboard")
    
    leaderboard_data = leaderboard_fragment()
    
    if leaderboard_data['success']:
        for rank, user in enumerate(leaderboard_data['leaderboard'], 1):
            total_value = user.get('total_portfolio_value', float(user['balance']) + float(user['net_pnl']))
            st.write(f"{rank}. {user['display_name']}: ${total_value:.2f}")
        
        # Display user count
        st.markdown(f'👥 **{leaderboard_data["user_count"]} players online**')
        user_count = leaderboard_data['user_count']
    else:
        st.warning(f"Could not load leaderboard: {leaderboard_data['error']}")
        user_count = 0

# Use actual outcome names from config, filtering for active outcomes only (multi-resolution support)
try:
    # Get engine state to check for active outcomes in multi-resolution scenarios
    engine_state = fetch_engine_state()
    active_outcomes = []
    
    for i in range(params['n_outcomes']):
        # Check if outcome is still active (not eliminated in multi-resolution)
        if i < len(engine_state.get('binaries', [])):
            binary = engine_state['binaries'][i]
            is_active = binary.get('active', True)  # Default to active if not specified
            if is_active:
                active_outcomes.append(i)
        else:
            # Fallback: assume active if state unavailable
            active_outcomes.append(i)
    
    # If no active outcomes found, show all (fallback for single-resolution or state issues)
    if not active_outcomes:
        active_outcomes = list(range(params['n_outcomes']))
        
except Exception:
    # Fallback: show all outcomes if state fetch fails
    active_outcomes = list(range(params['n_outcomes']))

# Create tabs only for active outcomes
outcome_tabs = st.tabs([
    params['outcome_names'][i] if i < len(params['outcome_names']) else f"Outcome {i+1}" 
    for i in active_outcomes
])

for tab_index, tab in enumerate(outcome_tabs):
    # Use actual outcome index from active_outcomes, not tab index
    outcome_i = active_outcomes[tab_index]
    with tab:
        col1, col2 = st.columns(2)
        with col1:
            st.header("Order Ticket")
            yes_no = st.radio("Token", ['YES', 'NO'], key=f"yes-no-radio-{outcome_i}")
            direction = st.radio("Direction", ['Buy', 'Sell'], key=f"buy-sell-radio-{outcome_i}")
            is_buy = direction == 'Buy'
            order_type = st.selectbox("Type", ['MARKET', 'LIMIT'], key=f"order-type-select-{outcome_i}")
            size_input = st.number_input("Size", min_value=0.01, value=1.0, key=f"size-input-{outcome_i}")
            size = usdc_amount(size_input)
            limit_price_input: Optional[float] = None
            max_slippage_input: Optional[float] = None
            if order_type == 'LIMIT':
                limit_price_input = st.number_input("Limit Price", min_value=0.0, max_value=1.0, step=0.01, value=0.5, key=f"limit_price_{outcome_i}")
            else:
                max_slippage_input = st.number_input("Max Slippage %", min_value=0.0, value=5.0, key=f"max_slippage_{outcome_i}") / 100
            af_opt_in = st.checkbox("Auto-Fill Opt-In", value=True, key=f"af_opt_in_{outcome_i}") if params['af_enabled'] else False

            try:
                validate_size(size)
                if limit_price_input is not None:
                    limit_price = price_value(limit_price_input)
                    validate_price(limit_price)
                    validate_limit_price_bounds(limit_price, Decimal(str(params['p_min'])), Decimal(str(params['p_max'])))
                if max_slippage_input is not None:
                    validate_price(price_value(max_slippage_input))
                est = estimate_slippage(outcome_i, yes_no, size, is_buy, price_value(max_slippage_input) if max_slippage_input else None)
                
                # Enhanced transaction confirmation with comprehensive details
                with st.expander("📋 Transaction Confirmation", expanded=True):
                    # Order Summary
                    st.subheader("📊 Order Summary")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**Token:** {yes_no}")
                        st.write(f"**Direction:** {direction}")
                        st.write(f"**Size:** {float(size):.2f} tokens")
                        if limit_price_input is not None:
                            st.write(f"**Limit Price:** ${limit_price_input:.4f}")
                    with col_b:
                        st.write(f"**Order Type:** {order_type}")
                        if order_type == 'MARKET':
                            st.write(f"**Max Slippage:** {max_slippage_input*100:.1f}%" if max_slippage_input else "No limit")
                        st.write(f"**Auto-Fill:** {'✅ Yes' if af_opt_in else '❌ No'}")
                    
                    # Fee Breakdown
                    st.subheader("💰 Fee Breakdown")
                    est_cost = est['est_cost']
                    gas_fee = Decimal(params['gas_fee'])
                    
                    # Calculate trading fee estimate and effective price
                    if order_type == 'LIMIT' and limit_price_input is not None:
                        # For limit orders: use proper fee structure based on match type
                        execution_cost = float(size) * limit_price_input
                        # Use f_match for cross-matches, f for same-side matches (simplified to f_match for estimation)
                        trading_fee_est = params.get('f_match', 0.02) * float(size) * limit_price_input
                        effective_price = limit_price_input  # True limit price enforcement
                    else:
                        # For market orders: est_cost already includes fees from service
                        execution_cost = float(est_cost)  # This already includes trading fees
                        trading_fee_est = 0  # Don't double-count fees
                        effective_price = float(est_cost) / float(size) if float(size) > 0 else 0
                    
                    fee_col1, fee_col2 = st.columns(2)
                    with fee_col1:
                        st.write(f"**Execution Cost:** ${execution_cost:.2f}")
                        st.write(f"**Trading Fee (est.):** ${trading_fee_est:.4f}")
                        st.write(f"**Gas Fee:** ${float(gas_fee):.4f}")
                    with fee_col2:
                        total_fees = trading_fee_est + float(gas_fee)
                        if is_buy:
                            total_cost = execution_cost + trading_fee_est + float(gas_fee)
                            st.write(f"**Total Cost:** ${total_cost:.2f}")
                            effective_cost_per_token = total_cost / float(size)
                        else:
                            total_proceeds = execution_cost - trading_fee_est - float(gas_fee)
                            st.write(f"**Total Proceeds:** ${total_proceeds:.2f}")
                            effective_cost_per_token = total_proceeds / float(size)
                        st.write(f"**Total Fees:** ${total_fees:.4f}")
                        st.write(f"**Effective Price/Token:** ${effective_cost_per_token:.4f}")
                    
                    # Market order specific info
                    if order_type == 'MARKET':
                        st.write(f"**Estimated Slippage:** {float(est['estimated_slippage'])*100:.2f}%")
                        if est['would_reject']:
                            st.error("⚠️ Estimated slippage exceeds maximum allowed")
                    
                    # Potential Returns Analysis
                    st.subheader("🎯 Potential Returns")
                    if is_buy:
                        # Calculate potential return if user wins
                        total_investment = total_cost
                        tokens_acquired = float(size)
                        payout_if_win = tokens_acquired * 1.0  # Each token pays $1 if outcome occurs
                        net_profit = payout_if_win - total_investment
                        return_multiple = payout_if_win / total_investment if total_investment > 0 else 0
                        
                        # Create prominent return display
                        st.markdown(f"""
<div style="border: 1px solid #D6E9C6; padding: 10px; margin-bottom: 10px; border-radius: 3px;">
    <strong>🎲 TRADE BREAKDOWN:</strong><br>
    <strong>Investment:</strong> ${total_investment:.2f}<br>
    <strong>If {yes_no} wins:</strong> ${payout_if_win:.2f} payout<br>
    <strong>Net Profit:</strong> ${net_profit:.2f}<br>
    <strong>Return Multiple:</strong> {return_multiple:.2f}x
</div>
""", unsafe_allow_html=True)

                        # Risk warning
                        if effective_cost_per_token > 0.8:
                            st.warning("⚠️ **High Risk Trade:** You're paying more than $0.80 per token. Consider the probability carefully.")
                        elif effective_cost_per_token > 0.6:
                            st.info("ℹ️ **Moderate Risk:** You're paying a premium price. Make sure you're confident in this outcome.")
                        else:
                            st.info("✅ **Value Opportunity:** You're getting tokens at a reasonable price relative to potential payout.")
                    else:
                        # For sell orders
                        st.info(f"**Selling {float(size):.2f} {yes_no} tokens for ~${total_proceeds:.2f}**")
                        st.write("You're reducing your exposure to this outcome.")
                    
                    # True limit price enforcement explanation for limit orders
                    if order_type == 'LIMIT':
                        st.info("✅ **True Limit Price Enforcement**: You will pay/receive exactly your limit price. All fees are separate and transparent.")
                    
                    # Additional checks
                    if 'est' in locals() and est['would_reject']:
                        st.error("Order would be rejected: Estimated slippage too high")
                    if execution_cost + trading_fee_est + float(gas_fee) > float(balance):
                        st.warning(f"Insufficient balance: Need ${execution_cost + trading_fee_est + float(gas_fee) - float(balance):.2f} more")
                
            except ValueError as e:
                st.error(str(e))
                est = {'would_reject': True}

            disable_submit = est['would_reject'] if 'est' in locals() else True
            if st.button("Submit Order", disabled=disable_submit, key=f"submit-order-button-{outcome_i}"):
                try:
                    order_data = {
                        'outcome_i': outcome_i,
                        'yes_no': yes_no,
                        'type': order_type,
                        'is_buy': is_buy,
                        'size': size,
                        'limit_price': price_value(limit_price_input) if limit_price_input is not None else None,
                        'max_slippage': price_value(max_slippage_input) if max_slippage_input is not None else None,
                        'af_opt_in': af_opt_in,
                        'ts_ms': get_current_ms()
                    }
                    order_id = submit_order(user_id, order_data)
                    st.success(f"✅ Order {order_id} submitted successfully!")
                    
                    # Clear any cached fragment data to force immediate refresh
                    # Clear portfolio cache with correct user-specific key
                    portfolio_cache_key = f'portfolio_cache_{user_id}'
                    if portfolio_cache_key in st.session_state:
                        del st.session_state[portfolio_cache_key]
                    
                    # Clear balance cache with correct user-specific key
                    balance_cache_key = f'balance_cache_{user_id}'
                    if balance_cache_key in st.session_state:
                        del st.session_state[balance_cache_key]
                    
                    # Clear trades cache (this one is global)
                    if 'trades_cache' in st.session_state:
                        del st.session_state['trades_cache']
                    
                    # Force immediate page refresh to show updated portfolio and trades
                    st.rerun()
                except ValueError as e:
                    st.error(f"❌ Order submission failed: {str(e)}")

        with col2:
            st.header("📊 Order Book")
            
            # Use module-scope price fragment for live updates
            current_p_yes, current_p_no = price_fragment(outcome_i)
            
            # Enhanced order book aggregation with user position tracking
            pools: List[Dict[str, Any]] = fetch_pools(outcome_i)
            tick_size = Decimal(str(params.get('tick_size', 0.01)))
            
            # Data structures for enhanced order book
            order_book_data = {
                'YES': {'bids': {}, 'asks': {}},
                'NO': {'bids': {}, 'asks': {}}
            }
            user_positions_in_pools = {
                'YES': {'bids': {}, 'asks': {}},
                'NO': {'bids': {}, 'asks': {}}
            }
            
            # Process pools and aggregate by price level
            for pool in pools:
                tick = int(pool['tick'])
                price = Decimal(tick) * tick_size
                volume = Decimal(pool['volume'])
                token = pool['yes_no']
                side = 'bids' if pool['is_buy'] else 'asks'
                
                # Initialize price level if not exists
                if price not in order_book_data[token][side]:
                    order_book_data[token][side][price] = {
                        'volume': Decimal('0'),
                        'user_share': Decimal('0'),
                        'tick': tick
                    }
                
                # Aggregate volume
                order_book_data[token][side][price]['volume'] += volume
                
                # Check if user has position in this pool
                if 'shares' in pool and isinstance(pool['shares'], dict):
                    user_share = Decimal(str(pool['shares'].get(user_id, 0)))
                    order_book_data[token][side][price]['user_share'] += user_share
                    if user_share > 0:
                        user_positions_in_pools[token][side][price] = user_share
            
            # Display enhanced order book
            tab1, tab2 = st.tabs(["📈 YES Token", "📉 NO Token"])
            
            with tab1:
                st.subheader("YES Token Order Book")
                
                # YES Asks (sorted low to high)
                if order_book_data['YES']['asks']:
                    st.write("**🔴 Asks (Sellers)**")
                    asks_data = []
                    for price in sorted(order_book_data['YES']['asks'].keys()):
                        data = order_book_data['YES']['asks'][price]
                        user_indicator = "👤" if data['user_share'] > 0 else ""
                        asks_data.append({
                            'Price': f"${float(price):.4f}",
                            'Volume': f"{float(data['volume']):.2f}",
                            'Your Share': f"{float(data['user_share']):.2f}" if data['user_share'] > 0 else "-",
                            'User': user_indicator
                        })
                    st.dataframe(asks_data, use_container_width=True)
                else:
                    st.write("*No asks available*")
                
                # Current market price indicator
                if current_p_yes:
                    st.write(f"**📊 Current Market Price: ${current_p_yes:.4f}**")
                
                # YES Bids (sorted high to low)
                if order_book_data['YES']['bids']:
                    st.write("**🟢 Bids (Buyers)**")
                    bids_data = []
                    for price in sorted(order_book_data['YES']['bids'].keys(), reverse=True):
                        data = order_book_data['YES']['bids'][price]
                        user_indicator = "👤" if data['user_share'] > 0 else ""
                        bids_data.append({
                            'Price': f"${float(price):.4f}",
                            'Volume': f"{float(data['volume']):.2f}",
                            'Your Share': f"{float(data['user_share']):.2f}" if data['user_share'] > 0 else "-",
                            'User': user_indicator
                        })
                    st.dataframe(bids_data, use_container_width=True)
                else:
                    st.write("*No bids available*")
            
            with tab2:
                st.subheader("NO Token Order Book")
                
                # NO Asks (sorted low to high)
                if order_book_data['NO']['asks']:
                    st.write("**🔴 Asks (Sellers)**")
                    asks_data = []
                    for price in sorted(order_book_data['NO']['asks'].keys()):
                        data = order_book_data['NO']['asks'][price]
                        user_indicator = "👤" if data['user_share'] > 0 else ""
                        asks_data.append({
                            'Price': f"${float(price):.4f}",
                            'Volume': f"{float(data['volume']):.2f}",
                            'Your Share': f"{float(data['user_share']):.2f}" if data['user_share'] > 0 else "-",
                            'User': user_indicator
                        })
                    st.dataframe(asks_data, use_container_width=True)
                else:
                    st.write("*No asks available*")
                
                # Current market price indicator
                if current_p_no:
                    st.write(f"**📊 Current Market Price: ${current_p_no:.4f}**")
                
                # NO Bids (sorted high to low)
                if order_book_data['NO']['bids']:
                    st.write("**🟢 Bids (Buyers)**")
                    bids_data = []
                    for price in sorted(order_book_data['NO']['bids'].keys(), reverse=True):
                        data = order_book_data['NO']['bids'][price]
                        user_indicator = "👤" if data['user_share'] > 0 else ""
                        bids_data.append({
                            'Price': f"${float(price):.4f}",
                            'Volume': f"{float(data['volume']):.2f}",
                            'Your Share': f"{float(data['user_share']):.2f}" if data['user_share'] > 0 else "-",
                            'User': user_indicator
                        })
                    st.dataframe(bids_data, use_container_width=True)
                else:
                    st.write("*No bids available*")
            
            # Summary of user's LOB positions
            total_user_positions = sum(
                len(user_positions_in_pools[token][side]) 
                for token in ['YES', 'NO'] 
                for side in ['bids', 'asks']
            )
            
            if total_user_positions > 0:
                st.info(f"👤 **You have positions in {total_user_positions} LOB pools** - Look for the 👤 indicator above")

        # Recent Trades section moved to bottom of page

# Enhanced Position and Order Management
st.header("💼 Your Portfolio")

# Create tabs for different views
pos_tab1, pos_tab2, pos_tab3 = st.tabs(["🏆 Filled Positions", "⏳ Open Limit Orders", "📊 Portfolio Summary"])

with pos_tab1:
    st.subheader("🏆 Your Filled Positions")
    
    # Get positions using portfolio fragment for live updates
    portfolio_data = portfolio_fragment(user_id)
    
    if portfolio_data['success']:
        positions = portfolio_data['positions']
    else:
        st.warning(f"Could not load positions: {portfolio_data['error']}")
        positions = []
    
    if positions:
        # Enhanced position display with potential returns
        position_data = []
        total_portfolio_value = 0
        total_invested = 0
        
        for p in positions:
            tokens = float(p['tokens'])
            if tokens > 0:  # Only show positions with actual tokens
                # Calculate potential payout (each token pays $1 if outcome occurs)
                potential_payout = tokens * 1.0
                
                # Estimate cost basis (this would ideally come from trade history)
                # For now, use current market price as rough estimate
                try:
                    engine_state = fetch_engine_state()
                    binary = get_binary(engine_state, p['outcome_i'])
                    if p['yes_no'] == 'YES':
                        current_price = get_p_yes(binary)
                    else:
                        current_price = get_p_no(binary)
                    estimated_cost_basis = tokens * current_price
                except:
                    estimated_cost_basis = tokens * 0.5  # Fallback estimate
                
                total_portfolio_value += potential_payout
                total_invested += estimated_cost_basis
                
                position_data.append({
                    'Outcome': p['outcome_i'],
                    'Token': f"{p['yes_no']} 🎯",
                    'Tokens': f"{tokens:.2f}",
                    'Current Value': f"${estimated_cost_basis:.2f}",
                    'Max Payout': f"${potential_payout:.2f}",
                    'Potential Profit': f"${potential_payout - estimated_cost_basis:.2f}",
                    'Return Multiple': f"{potential_payout / estimated_cost_basis:.2f}x" if estimated_cost_basis > 0 else "∞"
                })
        
        if position_data:
            st.dataframe(position_data, use_container_width=True)
            
            # Portfolio summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Positions", len(position_data))
            with col2:
                st.metric("Current Value", f"${total_invested:.2f}")
            with col3:
                st.metric("Max Potential", f"${total_portfolio_value:.2f}")
        else:
            st.info("📭 No filled positions yet. Place some orders to start building your portfolio!")
    else:
        st.info("📭 No filled positions yet. Place some orders to start building your portfolio!")

with pos_tab2:
    st.subheader("⏳ Your Open Limit Orders")
    
    # Get orders using portfolio fragment for live updates
    portfolio_data = portfolio_fragment(user_id)
    
    if portfolio_data['success']:
        orders = portfolio_data['orders']
    else:
        st.warning(f"Could not load orders: {portfolio_data['error']}")
        orders = []
    
    if orders:
        st.write(f"**You have {len(orders)} open limit orders**")
        
        for i, order in enumerate(orders):
            with st.expander(f"📋 Order #{order['order_id']} - {order['yes_no']} {order['type']}", expanded=True):
                # Order details in columns
                detail_col1, detail_col2, detail_col3 = st.columns(3)
                
                with detail_col1:
                    st.write(f"**Token:** {order['yes_no']}")
                    st.write(f"**Type:** {order['type']}")
                    st.write(f"**Size:** {float(order['size']):.2f} tokens")
                
                with detail_col2:
                    limit_price_display = f"${float(order['limit_price']):.4f}" if order['limit_price'] is not None else "N/A (Market Order)"
                    st.write(f"**Limit Price:** {limit_price_display}")
                    st.write(f"**Remaining:** {float(order['remaining']):.2f} tokens")
                    st.write(f"**Status:** {order['status']}")
                
                with detail_col3:
                    # Calculate potential returns for limit orders only
                    remaining_tokens = float(order['remaining'])
                    
                    if order['type'] == 'LIMIT' and order['limit_price'] is not None and remaining_tokens > 0:
                        limit_price = float(order['limit_price'])
                        total_cost = remaining_tokens * limit_price
                        potential_payout = remaining_tokens * 1.0
                        potential_profit = potential_payout - total_cost
                        return_multiple = potential_payout / total_cost if total_cost > 0 else 0
                        
                        st.write(f"**Total Cost:** ${total_cost:.2f}")
                        st.write(f"**Max Payout:** ${potential_payout:.2f}")
                        st.write(f"**Potential Profit:** ${potential_profit:.2f}")
                        st.write(f"**Return Multiple:** {return_multiple:.2f}x")
                        
                        # Risk assessment
                        if limit_price > 0.8:
                            st.warning("⚠️ High risk - paying premium price")
                        elif limit_price > 0.6:
                            st.info("ℹ️ Moderate risk - above average price")
                        else:
                            st.success("✅ Good value - reasonable price")
                    else:
                        # For MARKET orders or orders without limit price
                        if order['type'] == 'MARKET':
                            st.write(f"**Market Order:** {remaining_tokens:.2f} tokens")
                            st.write("**Price:** Determined at execution")
                        else:
                            st.write(f"**Order:** {remaining_tokens:.2f} tokens")
                            st.write("**Status:** Pending processing")
                
                # Enhanced cancellation interface
                st.write("---")
                cancel_col1, cancel_col2 = st.columns([3, 1])
                
                with cancel_col1:
                    st.write("💡 **Tip:** You can cancel this order anytime to free up your funds")
                
                with cancel_col2:
                    # Use a unique key for each cancel button
                    cancel_key = f"cancel_confirm_{order['order_id']}_{i}"
                    
                    if st.button("🗑️ Cancel Order", key=f"cancel-order-button-{order['order_id']}-{i}", type="secondary"):
                        # Store the order to cancel in session state
                        st.session_state[f'cancel_pending_{order["order_id"]}'] = True
                    
                    # Show confirmation dialog if cancellation is pending
                    if st.session_state.get(f'cancel_pending_{order["order_id"]}', False):
                        st.warning("⚠️ **Confirm Cancellation**")
                        
                        confirm_col1, confirm_col2 = st.columns(2)
                        with confirm_col1:
                            if st.button("✅ Yes, Cancel", key=f"confirm_yes_{order['order_id']}_{i}", type="primary"):
                                try:
                                    cancel_order(order['order_id'], user_id)
                                    st.success(f"✅ Order #{order['order_id']} canceled successfully!")
                                    
                                    # Clear the pending state
                                    if f'cancel_pending_{order["order_id"]}' in st.session_state:
                                        del st.session_state[f'cancel_pending_{order["order_id"]}']
                                    
                                    # Clear cached fragment data to force immediate refresh
                                    if 'portfolio_cache' in st.session_state:
                                        del st.session_state['portfolio_cache']
                                    if f'portfolio_cache_{user_id}' in st.session_state:
                                        del st.session_state[f'portfolio_cache_{user_id}']
                                    if f'balance_cache_{user_id}' in st.session_state:
                                        del st.session_state[f'balance_cache_{user_id}']
                                    
                                    st.rerun()
                                except ValueError as e:
                                    st.error(f"❌ Error canceling order: {str(e)}")
                        
                        with confirm_col2:
                            if st.button("❌ No, Keep", key=f"confirm_no_{order['order_id']}_{i}"):
                                # Clear the pending state
                                if f'cancel_pending_{order["order_id"]}' in st.session_state:
                                    del st.session_state[f'cancel_pending_{order["order_id"]}']
                                st.rerun()
    else:
        st.info("📭 No open limit orders. Your limit orders will appear here once placed.")
        st.write("💡 **Tip:** Limit orders let you set exact prices and potentially get better deals than market orders.")

with pos_tab3:
    st.subheader("📊 Portfolio Summary")
    
    # Get both positions and orders using fragment for live updates
    portfolio_data = portfolio_fragment(user_id)
    
    if portfolio_data['success']:
        positions = portfolio_data['positions']
        orders = portfolio_data['orders']
    else:
        st.warning(f"Could not load portfolio data: {portfolio_data['error']}")
        positions = []
        orders = []
    
    summary_col1, summary_col2 = st.columns(2)
    
    with summary_col1:
        st.write("**📈 Current Holdings**")
        filled_positions = [p for p in positions if float(p['tokens']) > 0]
        if filled_positions:
            # Group positions by outcome and sum YES/NO holdings
            outcome_holdings = {}
            for p in filled_positions:
                outcome_i = int(p['outcome_i'])
                outcome_name = params['outcome_names'][outcome_i] if outcome_i < len(params['outcome_names']) else f"Outcome {outcome_i + 1}"
                
                if outcome_name not in outcome_holdings:
                    outcome_holdings[outcome_name] = {'YES': 0.0, 'NO': 0.0}
                
                outcome_holdings[outcome_name][p['yes_no']] += float(p['tokens'])
            
            # Display summarized holdings
            for outcome_name, holdings in outcome_holdings.items():
                yes_tokens = holdings['YES']
                no_tokens = holdings['NO']
                
                if yes_tokens > 0 and no_tokens > 0:
                    st.write(f"• **{outcome_name}**: {yes_tokens:.2f} YES, {no_tokens:.2f} NO tokens")
                elif yes_tokens > 0:
                    st.write(f"• **{outcome_name}**: {yes_tokens:.2f} YES tokens")
                elif no_tokens > 0:
                    st.write(f"• **{outcome_name}**: {no_tokens:.2f} NO tokens")
        else:
            st.write("*No current holdings*")
    
    with summary_col2:
        st.write("**⏳ Pending Orders**")
        if orders:
            for order in orders:
                remaining = float(order['remaining'])
                if order['limit_price'] is not None:
                    price_display = f"@ ${float(order['limit_price']):.4f}"
                else:
                    price_display = "(Market Price)"
                st.write(f"• {order['type']} {remaining:.2f} {order['yes_no']} {price_display}")
        else:
            st.write("*No pending orders*")
    
    # Portfolio Metrics Fragment - updates with price changes for accurate portfolio value
    @st.fragment(run_every=batch_interval_s)
    def portfolio_metrics_fragment():
        try:
            # Get current user balance
            current_balance = float(fetch_user_balance(user_id))
            
            # Calculate token holdings value at current prices
            token_holdings_value = 0
            for p in positions:
                if float(p['tokens']) > 0:
                    outcome_i = int(p['outcome_i'])
                    current_p_yes, current_p_no = get_current_prices(outcome_i)
                    if current_p_yes is not None and current_p_no is not None:
                        if p['yes_no'] == 'YES':
                            token_holdings_value += float(p['tokens']) * current_p_yes
                        else:
                            token_holdings_value += float(p['tokens']) * current_p_no
                    else:
                        # Fallback to $0.50 if prices unavailable
                        token_holdings_value += float(p['tokens']) * 0.5
            
            # Calculate total committed capital from open orders only
            # Note: We track committed capital in pending orders, not historical cost basis of filled positions
            open_order_capital = 0
            for order in orders:
                if order['type'] == 'LIMIT' and order['limit_price'] is not None:
                    # LIMIT orders: remaining size * limit price
                    open_order_capital += float(order['remaining']) * float(order['limit_price'])
                elif order['type'] == 'MARKET':
                    # MARKET orders: estimate using current price (they execute quickly)
                    try:
                        outcome_i = int(order['outcome_i'])
                        current_p_yes, current_p_no = get_current_prices(outcome_i)
                        if current_p_yes is not None and current_p_no is not None:
                            if order['yes_no'] == 'YES':
                                estimated_price = current_p_yes
                            else:
                                estimated_price = current_p_no
                            open_order_capital += float(order['remaining']) * estimated_price
                        else:
                            # Fallback to $0.50 if prices unavailable
                            open_order_capital += float(order['remaining']) * 0.5
                    except (ValueError, KeyError, TypeError):
                        # Fallback for malformed order data
                        open_order_capital += float(order['remaining']) * 0.5
            
            # Calculate gas fees
            try:
                config = load_config()
                gas_fee_per_tx = config.get('params', {}).get('gas_fee_per_tx', 0.0)
                user_data = client.table('users').select('trade_count').eq('user_id', user_id).single().execute()
                if user_data.data:
                    total_gas_spent = float(user_data.data['trade_count']) * gas_fee_per_tx
                else:
                    total_gas_spent = 0.0
            except Exception:
                total_gas_spent = 0.0
            
            return {
                'current_balance': current_balance,
                'token_holdings_value': token_holdings_value,
                'open_order_capital': open_order_capital,
                'total_gas_spent': total_gas_spent
            }
        except Exception as e:
            st.error(f"Error calculating portfolio metrics: {e}")
            return {
                'current_balance': 0.0,
                'token_holdings_value': 0.0,
                'open_order_capital': 0.0,
                'total_gas_spent': 0.0
            }
    
    # Overall portfolio metrics
    st.write("---")
    st.write("**🎯 Portfolio Metrics**")
    
    # Get metrics from fragment
    metrics = portfolio_metrics_fragment()
    
    # Display metrics in columns
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    
    with metric_col1:
        st.metric("Active Positions", len([p for p in positions if float(p['tokens']) > 0]))
    
    with metric_col2:
        st.metric("Open Orders", len(orders))
    
    with metric_col3:
        st.metric("Capital Committed", f"${metrics['open_order_capital']:.2f}")
    
    with metric_col4:
        # USD Portfolio Value = Balance + Token Holdings at Current Price
        total_portfolio_value = metrics['current_balance'] + metrics['token_holdings_value']
        st.metric("USD Portfolio Value", f"${total_portfolio_value:.2f}")
    
    with metric_col5:
        st.metric("Gas Spent", f"${metrics['total_gas_spent']:.2f}")

    # Per-Outcome Potential Payouts Table
    st.write("---")
    st.write("**💰 Potential Payouts by Outcome**")
    
    # Group positions by outcome
    outcome_positions = {}
    for p in positions:
        if float(p['tokens']) > 0:
            outcome_i = int(p['outcome_i'])
            if outcome_i not in outcome_positions:
                outcome_positions[outcome_i] = {'YES': 0, 'NO': 0}
            outcome_positions[outcome_i][p['yes_no']] += float(p['tokens'])
    
    if outcome_positions:
        # Create payout table
        payout_data = []
        
        # Get outcome names from config
        try:
            config = load_config()
            outcome_names = config.get('params', {}).get('outcome_names', [])
        except:
            outcome_names = []
        
        for outcome_i in sorted(outcome_positions.keys()):
            # Get outcome name
            if outcome_i < len(outcome_names):
                outcome_name = outcome_names[outcome_i]
            else:
                outcome_name = f"Outcome {outcome_i + 1}"
            
            yes_tokens = outcome_positions[outcome_i]['YES']
            no_tokens = outcome_positions[outcome_i]['NO']
            
            # Calculate winnings if this outcome wins
            # If outcome i wins: YES tokens pay $1 each, NO tokens pay $0
            # If outcome i loses: YES tokens pay $0, NO tokens pay $1 each
            
            if_wins_winnings = yes_tokens * 1.0 + no_tokens * 0.0  # YES pays $1, NO pays $0
            if_loses_winnings = yes_tokens * 0.0 + no_tokens * 1.0  # YES pays $0, NO pays $1
            
            # Calculate P/L (Profit/Loss) = Winnings - Capital Committed
            # For P/L calculation, we need to estimate what was paid for these tokens
            # Since we don't track cost basis, use current market value as approximation
            try:
                current_p_yes, current_p_no = get_current_prices(outcome_i)
                if current_p_yes is not None and current_p_no is not None:
                    estimated_cost = yes_tokens * current_p_yes + no_tokens * current_p_no
                else:
                    estimated_cost = (yes_tokens + no_tokens) * 0.5
            except:
                estimated_cost = (yes_tokens + no_tokens) * 0.5
            
            if_wins_pl = if_wins_winnings - estimated_cost
            if_loses_pl = if_loses_winnings - estimated_cost
            
            # Add row for "if this outcome wins"
            payout_data.append({
                'Outcome': f"{outcome_name} WINS",
                'YES Tokens': f"{yes_tokens:.2f}",
                'NO Tokens': f"{no_tokens:.2f}",
                'Winnings': f"${if_wins_winnings:.2f}",
                'P/L': f"${if_wins_pl:+.2f}"
            })
            
            # Add row for "if this outcome loses" (only if user has NO tokens that would pay out)
            if if_loses_winnings > 0:
                payout_data.append({
                    'Outcome': f"{outcome_name} LOSES",
                    'YES Tokens': f"{yes_tokens:.2f}",
                    'NO Tokens': f"{no_tokens:.2f}",
                    'Winnings': f"${if_loses_winnings:.2f}",
                    'P/L': f"${if_loses_pl:+.2f}"
                })
        
        if payout_data:
            # Display as table
            import pandas as pd
            df = pd.DataFrame(payout_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No active positions to display payouts for.")
    else:
        st.info("No active positions to display payouts for.")

# Recent Trades Section - moved to bottom of page
st.header("📈 Recent Trades")
st.write("Latest trades across all outcomes")

# Fragment for recent trades - updates at batch interval
@st.fragment(run_every=batch_interval_s)
def recent_trades_fragment():
    # Check if we have cached data and it's recent
    cache_key = 'trades_cache'
    current_time = time.time()
    
    if (cache_key in st.session_state and 
        'timestamp' in st.session_state[cache_key] and 
        current_time - st.session_state[cache_key]['timestamp'] < batch_interval_s):
        return st.session_state[cache_key]['data']
    
    try:
        # Get all recent trades across all outcomes
        # Note: trades table has both buy_user_id and sell_user_id, so we need to handle this differently
        trades = client.table('trades').select('*').order('ts_ms', desc=True).limit(20).execute().data
        
        # Get user information separately to avoid ambiguous relationship
        user_ids = set()
        for trade in trades:
            if trade.get('buy_user_id'):
                user_ids.add(trade['buy_user_id'])
            if trade.get('sell_user_id'):
                user_ids.add(trade['sell_user_id'])
        
        # Fetch user display names
        users_data = {}
        if user_ids:
            users = client.table('users').select('user_id, display_name').in_('user_id', list(user_ids)).execute().data
            users_data = {u['user_id']: u['display_name'] for u in users}
        
        result = {
            'success': True,
            'trades': trades,
            'users_data': users_data,
            'error': None
        }
        
        # Cache the result
        st.session_state[cache_key] = {
            'data': result,
            'timestamp': current_time
        }
        
        return result
    except Exception as e:
        error_result = {
            'success': False,
            'trades': [],
            'users_data': {},
            'error': str(e)
        }
        
        # Don't cache errors, but return them
        return error_result

# Get recent trades using fragment for live updates
trades_data = recent_trades_fragment()

if trades_data['success'] and trades_data['trades']:
    # Process trades data with requested modifications
    processed_trades = []
    users_data = trades_data.get('users_data', {})
    
    # System user IDs (from app/engine/lob_matching.py and app/engine/orders.py)
    SYSTEM_USER_IDS = {
        '00000000-0000-0000-0000-000000000000',  # AMM System
        '11111111-1111-1111-1111-111111111111',  # Limit YES Pool
        '22222222-2222-2222-2222-222222222222',  # Limit NO Pool
        '33333333-3333-3333-3333-333333333333',  # Limit Pool
        '44444444-4444-4444-4444-444444444444',  # Market User
    }
    
    for t in trades_data['trades']:
        # Get user display name by identifying which side is NOT a system user
        user_name = "Unknown"
        is_user_buy = False
        
        buy_user_id = t.get('buy_user_id')
        sell_user_id = t.get('sell_user_id')
        
        if sell_user_id in SYSTEM_USER_IDS:
            # Seller is a system user, so buyer is the actual user (user initiated a buy)
            if buy_user_id and buy_user_id in users_data:
                user_name = users_data[buy_user_id]
            is_user_buy = True
        elif buy_user_id in SYSTEM_USER_IDS:
            # Buyer is a system user, so seller is the actual user (user initiated a sell)
            if sell_user_id and sell_user_id in users_data:
                user_name = users_data[sell_user_id]
            is_user_buy = False
        else:
            # Neither is a system user - this is a user-to-user trade
            # Show the buyer as the "active" user for consistency
            if buy_user_id and buy_user_id in users_data:
                user_name = users_data[buy_user_id]
            is_user_buy = True
        
        # Add directionality to size (negative for sells)
        size = float(t['size'])
        if is_user_buy:
            size_display = f"{size:.2f}"  # Positive for buys
        else:
            size_display = f"-{size:.2f}"  # Negative for sells
        
        # Get outcome name
        outcome_i = int(t.get('outcome_i', 0))
        outcome_name = params['outcome_names'][outcome_i] if outcome_i < len(params['outcome_names']) else f"Outcome {outcome_i + 1}"
        
        processed_trades.append({
            'Outcome': outcome_name,
            'User': user_name,
            'Price': f"${float(t['price']):.4f}",
            'Size': size_display,
            'Side': t['yes_no']
        })
    
    # Display the trades table
    st.table(processed_trades)
else:
    if trades_data['success']:
        st.info("No recent trades yet")
    else:
        st.warning(f"Could not load recent trades: {trades_data['error']}")

# Legacy refresh button removed - fragments handle all updates automatically