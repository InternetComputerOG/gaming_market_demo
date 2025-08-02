import streamlit as st
import time
from uuid import uuid4
from typing import Dict, Any, List, Optional
from decimal import Decimal

from app.config import get_supabase_client
from app.utils import get_current_ms, usdc_amount, price_value, validate_size, validate_price
from app.db.queries import load_config, insert_user, fetch_user_balance, fetch_positions, fetch_user_orders, get_current_tick, fetch_pools
from app.services.orders import submit_order, cancel_order, get_user_orders, estimate_slippage
from app.services.positions import fetch_user_positions

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

if status == 'DRAFT':
    st.write("Waiting for admin to start")
    st.stop()

if status == 'FROZEN':
    st.write("Trading frozen")
    if st.button("Refresh"):
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
start_ms = int(config['start_ts'])
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
            yes_no = st.radio("Token", ['YES', 'NO'])
            direction = st.radio("Direction", ['Buy', 'Sell'])
            is_buy = direction == 'Buy'
            order_type = st.selectbox("Type", ['MARKET', 'LIMIT'])
            size_input = st.number_input("Size", min_value=0.01, value=1.0)
            size = usdc_amount(size_input)
            limit_price_input: Optional[float] = None
            max_slippage_input: Optional[float] = None
            if order_type == 'LIMIT':
                limit_price_input = st.number_input("Limit Price", min_value=0.0, max_value=1.0, step=0.01, value=0.5)
            else:
                max_slippage_input = st.number_input("Max Slippage %", min_value=0.0, value=5.0) / 100
            af_opt_in = st.checkbox("Auto-Fill Opt-In", value=True) if params['af_enabled'] else False

            try:
                validate_size(size)
                if limit_price_input is not None:
                    validate_price(price_value(limit_price_input))
                if max_slippage_input is not None:
                    validate_price(price_value(max_slippage_input))
                est = estimate_slippage(outcome_i, yes_no, size, is_buy, price_value(max_slippage_input) if max_slippage_input else None)
                with st.expander("Confirmation"):
                    st.write(f"Estimated Slippage: {float(est['estimated_slippage']):.4f}")
                    st.write(f"Would Reject: {est['would_reject']}")
                    est_cost = est['est_cost']
                    gas_fee = Decimal(params['gas_fee'])
                    total_est = est_cost + gas_fee if is_buy else est_cost - gas_fee
                    st.write(f"Est Cost/Proceeds: ${float(est_cost):.2f}")
                    st.write(f"Gas Fee: ${float(gas_fee):.2f}")
                    st.write(f"Total: ${float(total_est):.2f}")
                    if est['would_reject']:
                        st.error("Estimated slippage exceeds max")
            except ValueError as e:
                st.error(str(e))
                est = {'would_reject': True}

            disable_submit = est['would_reject'] if 'est' in locals() else True
            if st.button("Submit Order", disabled=disable_submit):
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
            st.header("Order Book")
            pools: List[Dict[str, Any]] = fetch_pools(outcome_i)
            bids_yes: Dict[int, Decimal] = {}
            asks_yes: Dict[int, Decimal] = {}
            bids_no: Dict[int, Decimal] = {}
            asks_no: Dict[int, Decimal] = {}
            for pool in pools:
                tick = int(pool['tick'])
                volume = Decimal(pool['volume'])
                if pool['yes_no'] == 'YES':
                    if pool['is_buy']:
                        bids_yes[tick] = bids_yes.get(tick, Decimal(0)) + volume
                    else:
                        asks_yes[tick] = asks_yes.get(tick, Decimal(0)) + volume
                else:
                    if pool['is_buy']:
                        bids_no[tick] = bids_no.get(tick, Decimal(0)) + volume
                    else:
                        asks_no[tick] = asks_no.get(tick, Decimal(0)) + volume
            st.subheader("YES Bids")
            st.table(sorted(bids_yes.items(), reverse=True))
            st.subheader("YES Asks")
            st.table(sorted(asks_yes.items()))
            st.subheader("NO Bids")
            st.table(sorted(bids_no.items(), reverse=True))
            st.subheader("NO Asks")
            st.table(sorted(asks_no.items()))

        st.header("Recent Trades")
        trades = client.table('trades').select('*').eq('outcome_i', outcome_i).order('ts_ms', desc=True).limit(10).execute().data
        st.table([{ 'Price': float(t['price']), 'Size': float(t['size']), 'Side': t['yes_no'] } for t in trades])

st.header("Your Positions")
positions = fetch_user_positions(user_id)
st.table([{ 'Outcome': p['outcome_i'], 'Token': p['yes_no'], 'Tokens': float(p['tokens']) } for p in positions])

st.header("Your Open Orders")
orders = get_user_orders(user_id, 'OPEN')
for order in orders:
    st.write(order)
    if st.button("Cancel", key=f"cancel_{order['order_id']}"):
        try:
            cancel_order(order['order_id'], user_id)
            st.success("Order canceled")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

if st.button("Refresh"):
    st.rerun()