import streamlit as st
import time
from uuid import uuid4
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime

from app.config import get_supabase_client
from app.utils import get_current_ms, usdc_amount, price_value, validate_size, validate_price, validate_limit_price_bounds
from app.db.queries import load_config, insert_user, fetch_user_balance, fetch_positions, fetch_user_orders, get_current_tick, fetch_pools, fetch_engine_state
from app.services.orders import submit_order, cancel_order, get_user_orders, estimate_slippage
from app.services.positions import fetch_user_positions
from app.engine.state import get_binary, get_p_yes, get_p_no

client = get_supabase_client()

if 'user_id' not in st.session_state:
    display_name = st.text_input("Enter display name")
    if st.button("Join"):
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

# Enhanced waiting room with realtime status updates
if status == 'DRAFT':
    st.title("🎮 Gaming Market Demo")
    st.header("⏳ Waiting Room")
    
    # Show joined users count with error handling
    try:
        users = client.table('users').select('*').execute().data
        st.info(f"👥 **{len(users)} players joined** - Waiting for admin to start the demo...")
    except Exception as e:
        st.error(f"⚠️ Connection issue: {str(e)}")
        users = []
    
    # Initialize session state for status monitoring
    if 'last_status_check' not in st.session_state:
        st.session_state.last_status_check = time.time()
        st.session_state.refresh_counter = 0
    
    # Check for status updates every 3 seconds (controlled refresh)
    current_time = time.time()
    time_since_last_check = current_time - st.session_state.last_status_check
    
    if time_since_last_check > 3:
        st.session_state.last_status_check = current_time
        st.session_state.refresh_counter += 1
        
        # Reload config to check for status changes with error handling
        try:
            fresh_config = load_config()
            if fresh_config['status'] != 'DRAFT':
                st.success("🚀 Demo is starting! Redirecting to trading interface...")
                time.sleep(1)  # Brief pause for user to see the message
                st.rerun()
            else:
                # Only refresh if we haven't refreshed too many times
                if st.session_state.refresh_counter < 100:  # Prevent infinite loops
                    st.rerun()
        except Exception as e:
            st.warning(f"⚠️ Could not check status: {str(e)}")
            # Continue without refreshing if there's an error
    
    # Manual refresh button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔄 Check Status", type="primary"):
            st.session_state.refresh_counter = 0  # Reset counter on manual refresh
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
            st.caption(f"🔄 Auto-checking every 3 seconds... (Check #{st.session_state.refresh_counter})")
        with col_status2:
            if time_since_last_check < 1:
                st.caption("🟢 Just checked - Status: DRAFT")
            else:
                st.caption(f"⏱️ Next check in {max(0, 3 - int(time_since_last_check))} seconds")
    
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
    rankings = sorted(users, key=lambda u: float(u['net_pnl']), reverse=True)
    st.table([{ 'Name': r['display_name'], 'Net PNL': float(r['net_pnl']), '% Gain': float(r['net_pnl']) / float(config['starting_balance']) * 100 if config['starting_balance'] else 0, 'Trades': r['trade_count'] } for r in rankings])
    from app.scripts.generate_graph import generate_graph
    fig = generate_graph()
    st.pyplot(fig)
    st.stop()

params: Dict[str, Any] = config['params']
current_ms = get_current_ms()

# Handle both start_ts_ms (integer) and start_ts (ISO string) formats
if 'start_ts_ms' in config and config['start_ts_ms']:
    start_ms = int(config['start_ts_ms'])
elif 'start_ts' in config and config['start_ts']:
    # Parse ISO timestamp and convert to milliseconds
    # Handle timestamps with variable decimal precision
    timestamp_str = config['start_ts'].replace('Z', '+00:00')
    
    # Fix decimal precision issue: pad or truncate to 6 digits after decimal
    import re
    if '.' in timestamp_str:
        # Split at the decimal point
        before_decimal, after_decimal_and_tz = timestamp_str.split('.', 1)
        # Extract decimal digits and timezone
        decimal_match = re.match(r'(\d+)(.*)', after_decimal_and_tz)
        if decimal_match:
            decimal_digits, tz_part = decimal_match.groups()
            # Pad or truncate to exactly 6 digits (microseconds)
            decimal_digits = decimal_digits.ljust(6, '0')[:6]
            timestamp_str = f"{before_decimal}.{decimal_digits}{tz_part}"
    
    start_dt = datetime.fromisoformat(timestamp_str)
    start_ms = int(start_dt.timestamp() * 1000)
else:
    # Fallback to current time if no start time is set
    start_ms = current_ms

elapsed_ms = current_ms - start_ms
total_duration_ms = params['total_duration'] * 1000
time_to_end = max(0, (total_duration_ms - elapsed_ms) / 1000)
st.metric("Time to End", f"{time_to_end:.0f} seconds")

if time.time() - st.session_state['last_check'] > 1:
    st.session_state['last_check'] = time.time()
    current_tick = get_current_tick()
    if current_tick and current_tick['tick_id'] > st.session_state['last_tick']:
        st.session_state['last_tick'] = current_tick['tick_id']
        st.experimental_rerun()

balance = fetch_user_balance(user_id)
st.metric("Balance", f"${float(balance):.2f}")

st.sidebar.header("Leaderboard")
users = client.table('users').select('*').execute().data
leaderboard = sorted(users, key=lambda u: float(u['balance']) + float(u['net_pnl']), reverse=True)[:5]
for rank, user in enumerate(leaderboard, 1):
    st.sidebar.write(f"{rank}. {user['display_name']}: ${float(user['balance']) + float(user['net_pnl']):.2f}")

outcome_tabs = st.tabs([f"Outcome {i+1}" for i in range(params['n_outcomes'])])

for outcome_i, tab in enumerate(outcome_tabs):
    with tab:
        col1, col2 = st.columns(2)
        with col1:
            st.header("Order Ticket")
            yes_no = st.radio("Token", ['YES', 'NO'], key=f"token_{outcome_i}")
            direction = st.radio("Direction", ['Buy', 'Sell'], key=f"direction_{outcome_i}")
            is_buy = direction == 'Buy'
            order_type = st.selectbox("Type", ['MARKET', 'LIMIT'], key=f"order_type_{outcome_i}")
            size_input = st.number_input("Size", min_value=0.01, value=1.0, key=f"size_{outcome_i}")
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
                    validate_limit_price_bounds(limit_price, params)
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
                        # For limit orders: transparent fee structure with true limit price enforcement
                        trading_fee_est = params['f_match'] * float(size) * limit_price_input / 2
                        effective_price = limit_price_input  # True limit price enforcement
                        execution_cost = float(size) * limit_price_input
                    else:
                        # For market orders: use slippage estimation
                        trading_fee_est = float(est_cost) * params.get('f', 0.01)  # Fallback fee estimate
                        effective_price = float(est_cost) / float(size) if float(size) > 0 else 0
                        execution_cost = float(est_cost)
                    
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
                        total_investment = total_cost if order_type == 'LIMIT' else execution_cost + float(gas_fee)
                        tokens_acquired = float(size)
                        payout_if_win = tokens_acquired * 1.0  # Each token pays $1 if outcome occurs
                        net_profit = payout_if_win - total_investment
                        return_multiple = payout_if_win / total_investment if total_investment > 0 else 0
                        
                        # Create prominent return display
                        st.success(f"""**🎲 POTENTIAL OUTCOME:**
**Investment:** ${total_investment:.2f}
**If {yes_no} wins:** ${payout_if_win:.2f} payout
**Net Profit:** ${net_profit:.2f}
**Return Multiple:** {return_multiple:.2f}x""")
                        
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
                        
            except ValueError as e:
                st.error(str(e))
                est = {'would_reject': True}

            disable_submit = est['would_reject'] if 'est' in locals() else True
            if st.button("Submit Order", disabled=disable_submit, key=f"submit_{outcome_i}"):
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
                    st.success(f"Order {order_id} submitted")
                except ValueError as e:
                    st.error(str(e))

        with col2:
            st.header("📊 Order Book")
            
            # Get current market prices for reference
            try:
                engine_state = fetch_engine_state()
                binary = get_binary(engine_state, outcome_i)
                current_p_yes = get_p_yes(binary)
                current_p_no = get_p_no(binary)
                
                # Display current market prices prominently
                price_col1, price_col2 = st.columns(2)
                with price_col1:
                    st.metric("YES Market Price", f"${current_p_yes:.4f}", delta=None)
                with price_col2:
                    st.metric("NO Market Price", f"${current_p_no:.4f}", delta=None)
                
                st.write(f"**Spread:** ${abs(current_p_yes - current_p_no):.4f}")
            except Exception as e:
                st.warning("Could not load current market prices")
                current_p_yes = current_p_no = None
            
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

        st.header("Recent Trades")
        trades = client.table('trades').select('*').eq('outcome_i', outcome_i).order('ts_ms', desc=True).limit(10).execute().data
        st.table([{ 'Price': float(t['price']), 'Size': float(t['size']), 'Side': t['yes_no'] } for t in trades])

# Enhanced Position and Order Management
st.header("💼 Your Portfolio")

# Create tabs for different views
pos_tab1, pos_tab2, pos_tab3 = st.tabs(["🏆 Filled Positions", "⏳ Open Limit Orders", "📊 Portfolio Summary"])

with pos_tab1:
    st.subheader("🏆 Your Filled Positions")
    positions = fetch_user_positions(user_id)
    
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
    orders = get_user_orders(user_id, 'OPEN')
    
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
                    
                    if st.button("🗑️ Cancel Order", key=f"cancel_btn_{order['order_id']}_{i}", type="secondary"):
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
    
    # Get both positions and orders for comprehensive summary
    positions = fetch_user_positions(user_id)
    orders = get_user_orders(user_id, 'OPEN')
    
    summary_col1, summary_col2 = st.columns(2)
    
    with summary_col1:
        st.write("**📈 Current Holdings**")
        filled_positions = [p for p in positions if float(p['tokens']) > 0]
        if filled_positions:
            for p in filled_positions:
                st.write(f"• Outcome {p['outcome_i']}: {float(p['tokens']):.2f} {p['yes_no']} tokens")
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
    
    # Overall portfolio metrics
    st.write("---")
    st.write("**🎯 Portfolio Metrics**")
    
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    
    with metric_col1:
        st.metric("Active Positions", len([p for p in positions if float(p['tokens']) > 0]))
    
    with metric_col2:
        st.metric("Open Orders", len(orders))
    
    with metric_col3:
        # Calculate total committed capital in open orders (LIMIT orders only)
        total_committed = sum(
            float(order['remaining']) * float(order['limit_price']) 
            for order in orders 
            if order['type'] == 'LIMIT' and order['limit_price'] is not None
        )
        st.metric("Capital Committed", f"${total_committed:.2f}")
    
    with metric_col4:
        # Calculate total potential payout from positions
        total_max_payout = sum(
            float(p['tokens']) 
            for p in positions 
            if float(p['tokens']) > 0
        )
        st.metric("Max Potential Payout", f"${total_max_payout:.2f}")

if st.button("Refresh"):
    st.rerun()