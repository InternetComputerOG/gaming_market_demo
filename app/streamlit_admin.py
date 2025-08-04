import streamlit as st
from typing import Dict, Any, List
from supabase import Client
import json
import os
import io
import pandas as pd
from matplotlib.figure import Figure

from app.config import get_supabase_client, EngineParams, get_default_engine_params
from app.db.queries import load_config, update_config, fetch_users, get_current_tick
from app.utils import get_current_ms
from app.services.realtime import publish_resolution_update
from app.services.resolutions import trigger_resolution_service
from app.scripts.export_csv import fetch_trades, fetch_metrics, export_config_csv, export_rankings_csv
from app.scripts.generate_graph import generate_graph
from app.runner.batch_runner import start_batch_runner
from app.runner.timer_service import start_timer_service

# Load environment variables
env = {}
try:
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                env[key] = value
except FileNotFoundError:
    st.error(".env file not found.")
    st.stop()

ADMIN_PASSWORD = env.get('ADMIN_PASSWORD')

def get_client() -> Client:
    return get_supabase_client()

def download_csv(data: List[Dict[str, Any]], filename: str) -> bytes:
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    return output.getvalue().encode('utf-8')

def run_admin_app():
    st.set_page_config(page_title="Gaming Market Admin", layout="wide")
    st.markdown('<link rel="stylesheet" href="static/style.css">', unsafe_allow_html=True)

    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    st.title("Gaming Market Admin Dashboard")

    client = get_client()
    config = load_config()
    status = config.get('status', 'DRAFT')
    params: EngineParams = config.get('params', get_default_engine_params())

    # Config Form
    with st.expander("Configure Session", expanded=status == 'DRAFT'):
        with st.form(key="config_form"):
            col1, col2, col3 = st.columns(3)

            with col1:
                params['n_outcomes'] = st.number_input("Number of Outcomes", min_value=3, max_value=10, value=params['n_outcomes'])
                params['z'] = st.number_input("Initial Subsidy (Z)", min_value=0.0, value=params['z'])
                params['gamma'] = st.number_input("Subsidy Phase-Out Rate (γ)", min_value=0.0, max_value=0.001, value=params['gamma'], format="%.6f")
                params['q0'] = st.number_input("Initial Virtual Supply (q0)", min_value=0.0, value=params['q0'])
                params['f'] = st.number_input("Fee Fraction (f)", min_value=0.0, max_value=0.05, value=params['f'], format="%.4f")
                params['p_max'] = st.number_input("Maximum Price (p_max)", min_value=0.5, max_value=1.0, value=params['p_max'], format="%.4f")
                params['p_min'] = st.number_input("Minimum Price (p_min)", min_value=0.0, max_value=0.5, value=params['p_min'], format="%.4f")

            with col2:
                params['eta'] = st.number_input("Penalty Exponent (η)", min_value=1.0, value=params['eta'])
                params['tick_size'] = st.number_input("Tick Granularity", min_value=0.001, value=params['tick_size'], format="%.4f")
                params['f_match'] = st.number_input("Match Fee Fraction (f_match)", min_value=0.0, max_value=0.02, value=params['f_match'], format="%.4f")
                params['sigma'] = st.number_input("Seigniorage Share (σ)", min_value=0.0, max_value=1.0, value=params['sigma'], format="%.4f")
                params['af_cap_frac'] = st.number_input("Auto-Fill Volume Cap Fraction", min_value=0.0, max_value=0.2, value=params['af_cap_frac'], format="%.4f")
                params['af_max_pools'] = st.number_input("Max Pools per Auto-Fill", min_value=1, max_value=5, value=params['af_max_pools'])
                params['af_max_surplus'] = st.number_input("Max Surplus per Trade", min_value=0.0, value=params['af_max_surplus'], format="%.4f")

            with col3:
                params['mu_start'] = st.number_input("μ Start", min_value=0.0, value=params['mu_start'])
                params['mu_end'] = st.number_input("μ End", min_value=0.0, value=params['mu_end'])
                params['nu_start'] = st.number_input("ν Start", min_value=0.0, value=params['nu_start'])
                params['nu_end'] = st.number_input("ν End", min_value=0.0, value=params['nu_end'])
                params['kappa_start'] = st.number_input("κ Start", min_value=0.0, value=params['kappa_start'], format="%.6f")
                params['kappa_end'] = st.number_input("κ End", min_value=0.0, value=params['kappa_end'], format="%.6f")
                params['zeta_start'] = st.number_input("ζ Start", min_value=0.0, max_value=1.0/(params['n_outcomes']-1), value=params['zeta_start'], format="%.4f")
                params['zeta_end'] = st.number_input("ζ End", min_value=0.0, max_value=1.0/(params['n_outcomes']-1), value=params['zeta_end'], format="%.4f")

            col4, col5, col6 = st.columns(3)

            with col4:
                params['interpolation_mode'] = st.selectbox("Interpolation Mode", options=['reset', 'continue'], index=['reset', 'continue'].index(params['interpolation_mode']))
                params['cm_enabled'] = st.checkbox("Cross-Match Enabled", value=params['cm_enabled'])
                params['af_enabled'] = st.checkbox("Auto-Fill Enabled", value=params['af_enabled'])
                params['mr_enabled'] = st.checkbox("Multi-Resolution Enabled", value=params['mr_enabled'])
                params['vc_enabled'] = st.checkbox("Virtual Cap Enabled", value=params['vc_enabled'])

            with col5:
                params['total_duration'] = st.number_input("Total Duration (seconds)", min_value=0, value=params['total_duration'])
                params['final_winner'] = st.number_input("Final Winner Outcome", min_value=0, max_value=params['n_outcomes']-1, value=params['final_winner'])
                params['starting_balance'] = st.number_input("Starting Balance (USDC)", min_value=0.0, value=params['starting_balance'])
                params['gas_fee'] = st.number_input("Gas Fee per Transaction", min_value=0.0, value=params['gas_fee'])
                params['batch_interval_ms'] = st.number_input("Batch Interval (ms)", min_value=100, value=params['batch_interval_ms'])

            with col6:
                res_offsets_str = st.text_input("Resolution Offsets (JSON list)", value=json.dumps(params['res_offsets']))
                params['res_offsets'] = json.loads(res_offsets_str) if res_offsets_str else []
                freeze_durs_str = st.text_input("Freeze Durations (JSON list)", value=json.dumps(params['freeze_durs']))
                params['freeze_durs'] = json.loads(freeze_durs_str) if freeze_durs_str else []
                elim_outcomes_str = st.text_input("Elim Outcomes (JSON list of lists)", value=json.dumps(params['elim_outcomes']))
                params['elim_outcomes'] = json.loads(elim_outcomes_str) if elim_outcomes_str else []

            submitted = st.form_submit_button("Save Configuration")
            if submitted:
                try:
                    # Basic validation
                    if params['mr_enabled'] and sum(len(elims) for elims in params['elim_outcomes']) != params['n_outcomes'] - 1:
                        raise ValueError("Sum of eliminated outcomes must equal N-1")
                    update_config({'params': params})
                    st.success("Configuration saved.")
                except ValueError as e:
                    st.error(f"Invalid configuration: {e}")

    # Joined Users
    users = fetch_users()
    st.subheader(f"Joined Users ({len(users)})")
    st.table(users)

    # Controls
    st.subheader("Demo Controls")
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    with col_ctrl1:
        if st.button("Start Demo") and status == 'DRAFT':
            config['status'] = 'RUNNING'
            config['start_ts_ms'] = get_current_ms()
            update_config({'params': config['params'], 'status': 'RUNNING', 'start_ts_ms': config['start_ts_ms']})
            start_timer_service()
            start_batch_runner()
            st.success("Demo started.")
    with col_ctrl2:
        if st.button("Freeze Trading") and status == 'RUNNING':
            config['status'] = 'FROZEN'
            update_config({'status': 'FROZEN'})
            st.success("Trading frozen.")
    with col_ctrl3:
        if st.button("Resume Trading") and status == 'FROZEN':
            config['status'] = 'RUNNING'
            update_config({'status': 'RUNNING'})
            st.success("Trading resumed.")

    # Manual Resolution (override)
    if params['mr_enabled']:
        current_round = config.get('current_round', 0)
        if st.button("Trigger Next Resolution") and status == 'FROZEN' and current_round < len(params['elim_outcomes']):
            elims = params['elim_outcomes'][current_round]
            trigger_resolution_service(is_final=False, elim_outcomes=elims, current_time=(get_current_ms() - config['start_ts_ms']) // 1000)
            publish_resolution_update(is_final=False, elim_outcomes=elims)
            st.success("Resolution triggered.")

    # Exports
    st.subheader("Exports")
    col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
    with col_exp1:
        trades_data = fetch_trades(client=client)
        csv_trades = download_csv(trades_data, "trades.csv")
        st.download_button("Download Trades CSV", csv_trades, "trades.csv")
    with col_exp2:
        config_data = [config['params']]
        csv_config = download_csv(config_data, "config.csv")
        st.download_button("Download Config CSV", csv_config, "config.csv")
    with col_exp3:
        metrics_data = fetch_metrics(client=client)
        csv_metrics = download_csv(metrics_data, "metrics.csv")
        st.download_button("Download Metrics CSV", csv_metrics, "metrics.csv")
    with col_exp4:
        if st.button("Generate Rankings CSV"):
            export_rankings_csv("rankings.csv")
            with open("rankings.csv", "rb") as f:
                st.download_button("Download Rankings CSV", f.read(), "rankings.csv")
            os.remove("rankings.csv")

    # Graph
    st.subheader("Performance Graph")
    if status == 'RESOLVED':
        generate_graph(output_path="graph.png")
        st.image("graph.png")
        os.remove("graph.png")
    else:
        st.info("Graph available after resolution.")

    # LOB Monitoring Section (Section 4.2 of LOB Update Checklist)
    st.subheader("📊 LOB Monitoring")
    
    if status in ['RUNNING', 'FROZEN']:
        try:
            from app.db.queries import fetch_engine_state
            from app.services.ticks import get_lob_pool_statistics
            from decimal import Decimal
            
            engine_state = fetch_engine_state()
            
            # LOB Pool Statistics
            with st.expander("🏦 LOB Pool Statistics", expanded=True):
                if engine_state and 'lob_pools' in engine_state:
                    lob_pools = engine_state['lob_pools']
                    
                    # Summary metrics
                    col_lob1, col_lob2, col_lob3, col_lob4 = st.columns(4)
                    
                    total_pools = len(lob_pools)
                    active_pools = sum(1 for pool_key, pool_data in lob_pools.items() if pool_data.get('volume', 0) > 0)
                    total_volume = sum(float(pool_data.get('volume', 0)) for pool_data in lob_pools.values())
                    total_users = len(set(
                        user_id for pool_data in lob_pools.values() 
                        for user_id in pool_data.get('shares', {}).keys()
                    ))
                    
                    with col_lob1:
                        st.metric("Total LOB Pools", total_pools)
                    with col_lob2:
                        st.metric("Active Pools", active_pools)
                    with col_lob3:
                        st.metric("Total Volume", f"${total_volume:.2f}")
                    with col_lob4:
                        st.metric("Active Users", total_users)
                    
                    # Per-outcome breakdown
                    st.subheader("📈 Per-Outcome LOB Activity")
                    
                    outcome_data = {}
                    for pool_key, pool_data in lob_pools.items():
                        # Parse pool key format: "outcome_i:yes_no:is_buy:tick"
                        try:
                            parts = pool_key.split(':')
                            if len(parts) >= 4:
                                outcome_i = int(parts[0])
                                yes_no = parts[1]
                                is_buy = parts[2] == 'True'
                                tick = int(parts[3])
                                
                                if outcome_i not in outcome_data:
                                    outcome_data[outcome_i] = {
                                        'YES_buy': {'pools': 0, 'volume': 0.0},
                                        'YES_sell': {'pools': 0, 'volume': 0.0},
                                        'NO_buy': {'pools': 0, 'volume': 0.0},
                                        'NO_sell': {'pools': 0, 'volume': 0.0}
                                    }
                                
                                pool_type = f"{yes_no}_{'buy' if is_buy else 'sell'}"
                                volume = float(pool_data.get('volume', 0))
                                
                                if volume > 0:
                                    outcome_data[outcome_i][pool_type]['pools'] += 1
                                    outcome_data[outcome_i][pool_type]['volume'] += volume
                        except (ValueError, IndexError):
                            continue
                    
                    # Display outcome breakdown
                    for outcome_i in sorted(outcome_data.keys()):
                        data = outcome_data[outcome_i]
                        with st.expander(f"Outcome {outcome_i + 1}", expanded=False):
                            col_yes, col_no = st.columns(2)
                            
                            with col_yes:
                                st.write("**YES Token Pools**")
                                st.write(f"Buy Pools: {data['YES_buy']['pools']} (${data['YES_buy']['volume']:.2f})")
                                st.write(f"Sell Pools: {data['YES_sell']['pools']} (${data['YES_sell']['volume']:.2f})")
                            
                            with col_no:
                                st.write("**NO Token Pools**")
                                st.write(f"Buy Pools: {data['NO_buy']['pools']} (${data['NO_buy']['volume']:.2f})")
                                st.write(f"Sell Pools: {data['NO_sell']['pools']} (${data['NO_sell']['volume']:.2f})")
                else:
                    st.info("No LOB pool data available")
            
            # Cross-Matching Activity Metrics
            with st.expander("⚡ Cross-Matching Activity", expanded=True):
                try:
                    # Get recent cross-matching metrics from ticks/metrics table
                    recent_ticks = client.table('ticks').select('*').order('tick_id', desc=True).limit(10).execute().data
                    
                    if recent_ticks:
                        # Aggregate cross-matching metrics from recent ticks
                        total_cm_volume = 0.0
                        total_cm_events = 0
                        total_cm_fees = 0.0
                        avg_solvency_margin = 0.0
                        avg_pool_utilization = 0.0
                        
                        valid_ticks = 0
                        for tick in recent_ticks:
                            summary = tick.get('summary', {})
                            if isinstance(summary, dict):
                                cm_data = summary.get('cross_matching', {})
                                if cm_data.get('total_events', 0) > 0:
                                    total_cm_volume += cm_data.get('total_volume', 0)
                                    total_cm_events += cm_data.get('total_events', 0)
                                    total_cm_fees += cm_data.get('total_fees', 0)
                                    avg_solvency_margin += cm_data.get('avg_solvency_margin', 0)
                                    avg_pool_utilization += cm_data.get('pool_utilization', 0)
                                    valid_ticks += 1
                        
                        # Display metrics
                        col_cm1, col_cm2, col_cm3, col_cm4 = st.columns(4)
                        
                        with col_cm1:
                            st.metric("CM Events (Last 10 Ticks)", total_cm_events)
                        with col_cm2:
                            st.metric("CM Volume", f"${total_cm_volume:.2f}")
                        with col_cm3:
                            st.metric("CM Fees Collected", f"${total_cm_fees:.4f}")
                        with col_cm4:
                            if valid_ticks > 0:
                                st.metric("Avg Solvency Margin", f"{avg_solvency_margin/valid_ticks:.4f}")
                            else:
                                st.metric("Avg Solvency Margin", "N/A")
                        
                        # Additional metrics
                        col_cm5, col_cm6 = st.columns(2)
                        with col_cm5:
                            if valid_ticks > 0:
                                st.metric("Avg Pool Utilization", f"{(avg_pool_utilization/valid_ticks)*100:.1f}%")
                            else:
                                st.metric("Avg Pool Utilization", "N/A")
                        with col_cm6:
                            if total_cm_volume > 0:
                                fee_rate = (total_cm_fees / total_cm_volume) * 100
                                st.metric("Effective Fee Rate", f"{fee_rate:.3f}%")
                            else:
                                st.metric("Effective Fee Rate", "N/A")
                    else:
                        st.info("No recent cross-matching activity")
                        
                except Exception as e:
                    st.error(f"Error loading cross-matching metrics: {e}")
            
            # LOB Parameter Controls
            with st.expander("⚙️ LOB Parameter Controls", expanded=False):
                st.write("**Current LOB Parameters:**")
                
                col_param1, col_param2, col_param3 = st.columns(3)
                
                with col_param1:
                    st.write(f"**f_match (Match Fee):** {params.get('f_match', 0.0):.4f}")
                    st.write(f"**Cross-Match Enabled:** {params.get('cm_enabled', False)}")
                    st.write(f"**Tick Size:** {params.get('tick_size', 0.01):.4f}")
                
                with col_param2:
                    st.write(f"**p_min (Min Price):** {params.get('p_min', 0.01):.4f}")
                    st.write(f"**p_max (Max Price):** {params.get('p_max', 0.99):.4f}")
                    st.write(f"**Seigniorage Share (σ):** {params.get('sigma', 0.5):.4f}")
                
                with col_param3:
                    st.write(f"**Auto-Fill Enabled:** {params.get('af_enabled', False)}")
                    st.write(f"**AF Cap Fraction:** {params.get('af_cap_frac', 0.1):.4f}")
                    st.write(f"**AF Max Pools:** {params.get('af_max_pools', 3)}")
                
                st.info("💡 **Tip:** LOB parameters can be modified in the 'Configure Session' section above. Changes take effect on the next tick.")
                
                # Parameter explanations
                with st.expander("📖 Parameter Explanations", expanded=False):
                    st.markdown("""
                    **True Limit Price Enforcement Parameters:**
                    
                    - **f_match**: Fee fraction for cross-matching trades (typically 0.001-0.01)
                    - **Cross-Match Enabled**: Allows YES/NO limit orders to cross-match when profitable
                    - **Tick Size**: Price granularity for limit orders (e.g., 0.01 = 1 cent increments)
                    - **p_min/p_max**: Price bounds for limit orders [0.01, 0.99] prevents extreme prices
                    - **Seigniorage Share (σ)**: Fraction of cross-matching surplus allocated to system
                    - **Auto-Fill**: Automatically fills limit orders when AMM prices cross limit prices
                    - **AF Cap Fraction**: Maximum fraction of pool volume that can be auto-filled per trade
                    - **AF Max Pools**: Maximum number of pools that can be auto-filled in one transaction
                    
                    **Key Features:**
                    - YES buyers pay exactly their limit price
                    - NO sellers receive exactly their limit price  
                    - Trading fees are transparent and separate from execution prices
                    - Cross-matching creates additional liquidity and price discovery
                    """)
        
        except Exception as e:
            st.error(f"Error loading LOB monitoring data: {e}")
            st.info("LOB monitoring requires engine state data. Ensure the system is running and processing ticks.")
    
    else:
        st.info("LOB monitoring is available when the market is RUNNING or FROZEN.")

    # Realtime refresh
    if 'last_tick' not in st.session_state:
        st.session_state.last_tick = 0
    current_tick = get_current_tick().get('tick_id', 0)
    if current_tick > st.session_state.last_tick:
        st.session_state.last_tick = current_tick
        st.rerun()

if __name__ == "__main__":
    run_admin_app()