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
    config = load_config(client=client)
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
                    update_config(client=client, params=params)
                    st.success("Configuration saved.")
                except ValueError as e:
                    st.error(f"Invalid configuration: {e}")

    # Joined Users
    users = fetch_users(client=client)
    st.subheader(f"Joined Users ({len(users)})")
    st.table(users)

    # Controls
    st.subheader("Demo Controls")
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    with col_ctrl1:
        if st.button("Start Demo") and status == 'DRAFT':
            config['status'] = 'RUNNING'
            config['start_ts_ms'] = get_current_ms()
            update_config(client=client, params=config['params'], status='RUNNING', start_ts_ms=config['start_ts_ms'])
            start_timer_service()
            start_batch_runner()
            st.success("Demo started.")
    with col_ctrl2:
        if st.button("Freeze Trading") and status == 'RUNNING':
            config['status'] = 'FROZEN'
            update_config(client=client, status='FROZEN')
            st.success("Trading frozen.")
    with col_ctrl3:
        if st.button("Resume Trading") and status == 'FROZEN':
            config['status'] = 'RUNNING'
            update_config(client=client, status='RUNNING')
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

    # Realtime refresh
    if 'last_tick' not in st.session_state:
        st.session_state.last_tick = 0
    current_tick = get_current_tick(client=client).get('tick_id', 0)
    if current_tick > st.session_state.last_tick:
        st.session_state.last_tick = current_tick
        st.rerun()

if __name__ == "__main__":
    run_admin_app()