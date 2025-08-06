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
from app.services.realtime import publish_resolution_update, publish_demo_status_update
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

def insert_system_users():
    """
    Insert system users required for LOB matching and AMM operations.
    These users are needed as foreign key references for trades.
    """
    try:
        client = get_client()
        
        # Define system users with their UUIDs
        system_users = [
            {'user_id': '00000000-0000-0000-0000-000000000000', 'display_name': 'AMM System', 'is_admin': False, 'balance': 0, 'net_pnl': 0, 'trade_count': 0},
            {'user_id': '11111111-1111-1111-1111-111111111111', 'display_name': 'Limit YES Pool', 'is_admin': False, 'balance': 0, 'net_pnl': 0, 'trade_count': 0},
            {'user_id': '22222222-2222-2222-2222-222222222222', 'display_name': 'Limit NO Pool', 'is_admin': False, 'balance': 0, 'net_pnl': 0, 'trade_count': 0},
            {'user_id': '33333333-3333-3333-3333-333333333333', 'display_name': 'Limit Pool', 'is_admin': False, 'balance': 0, 'net_pnl': 0, 'trade_count': 0},
            {'user_id': '44444444-4444-4444-4444-444444444444', 'display_name': 'Market User', 'is_admin': False, 'balance': 0, 'net_pnl': 0, 'trade_count': 0}
        ]
        
        # Insert system users using upsert to avoid conflicts
        result = client.table('users').upsert(system_users).execute()
        st.success(f"✅ System users inserted successfully ({len(system_users)} users)")
        return True
        
    except Exception as e:
        st.error(f"❌ Failed to insert system users: {e}")
        return False

def reset_demo_state():
    """
    Completely reset the demo state by clearing all relevant database tables
    and resetting the config to DRAFT status with atomic transaction support.
    """
    try:
        client = get_client()
        
        # Use atomic transaction approach for better reliability
        st.info("🔄 Starting atomic demo reset...")
        
        # Step 1: Collect all records to delete (for verification)
        tables_to_clear = [
            ('users', 'user_id'),
            ('positions', 'position_id'),
            ('orders', 'order_id'), 
            ('lob_pools', 'pool_id'),
            ('trades', 'trade_id'),
            ('events', 'event_id'),
            ('metrics', 'metric_id'),
            ('ticks', 'tick_id')
        ]
        
        initial_counts = {}
        for table_name, id_field in tables_to_clear:
            try:
                count_result = client.table(table_name).select('count', count='exact').execute()
                initial_counts[table_name] = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
                st.info(f"📊 {table_name}: {initial_counts[table_name]} records to clear")
            except Exception as e:
                st.warning(f"Could not count {table_name}: {e}")
                initial_counts[table_name] = 0
        
        # Step 2: Attempt to clear all tables with better error handling
        deletion_success = True
        deletion_errors = []
        
        for table_name, id_field in tables_to_clear:
            try:
                if initial_counts.get(table_name, 0) > 0:
                    st.info(f"🗑️ Clearing {table_name}...")
                    
                    # Try bulk delete first (more efficient)
                    try:
                        # Use a condition that matches all records
                        result = client.table(table_name).delete().neq(id_field, 'impossible-uuid-that-never-exists').execute()
                        st.success(f"✅ {table_name} cleared via bulk delete")
                    except Exception as bulk_error:
                        st.warning(f"Bulk delete failed for {table_name}, trying individual deletion: {bulk_error}")
                        
                        # Fallback to individual record deletion
                        records = client.table(table_name).select(id_field).execute()
                        if records.data:
                            failed_deletes = 0
                            for record in records.data:
                                try:
                                    client.table(table_name).delete().eq(id_field, record[id_field]).execute()
                                except Exception as record_error:
                                    failed_deletes += 1
                                    if failed_deletes <= 3:  # Only show first few errors
                                        st.warning(f"Failed to delete {table_name} record {record[id_field]}: {record_error}")
                            
                            if failed_deletes > 0:
                                st.warning(f"⚠️ {failed_deletes} records in {table_name} could not be deleted")
                                deletion_success = False
                                deletion_errors.append(f"{table_name}: {failed_deletes} failed deletions")
                            else:
                                st.success(f"✅ {table_name} cleared via individual deletion")
                else:
                    st.info(f"ℹ️ {table_name} was already empty")
                    
            except Exception as table_error:
                st.error(f"❌ Error clearing {table_name}: {table_error}")
                deletion_success = False
                deletion_errors.append(f"{table_name}: {str(table_error)}")
        
        # Step 3: Verify deletion results
        st.info("🔍 Verifying deletion results...")
        verification_success = True
        
        for table_name, id_field in tables_to_clear:
            try:
                remaining_result = client.table(table_name).select('count', count='exact').execute()
                remaining_count = remaining_result.count if hasattr(remaining_result, 'count') else len(remaining_result.data)
                
                if remaining_count > 0:
                    st.warning(f"⚠️ {table_name} still has {remaining_count} records remaining")
                    verification_success = False
                else:
                    st.success(f"✅ {table_name} successfully cleared (0 records)")
            except Exception as verify_error:
                st.warning(f"Could not verify {table_name}: {verify_error}")
        
        # Step 4: Report overall deletion status
        if deletion_success and verification_success:
            st.success("🎉 All database tables successfully cleared!")
        elif deletion_success:
            st.warning("⚠️ Deletion completed but verification found remaining records")
        else:
            st.error(f"❌ Deletion encountered errors: {'; '.join(deletion_errors)}")
            st.info("💡 Some records may remain due to foreign key constraints or permissions")
        
        # 9. Reset config to DRAFT state with default parameters and proper engine state
        default_params = get_default_engine_params()
        
        # Initialize proper engine state according to TDD specification
        from app.engine.state import init_state
        fresh_engine_state = init_state(default_params)
        
        reset_config = {
            'status': 'DRAFT',
            'params': default_params,
            'current_round': 0,
            'engine_state': fresh_engine_state
        }
        
        # Update the config and verify it worked
        try:
            update_config(reset_config)
            st.info("Config reset to DRAFT status")
            
            # Verify the status was actually set
            updated_config = load_config()
            actual_status = updated_config.get('status', 'UNKNOWN')
            
            if actual_status == 'DRAFT':
                st.success(f"✅ Status successfully reset to '{actual_status}'")
            else:
                st.warning(f"⚠️ Status is '{actual_status}' instead of 'DRAFT' - trying direct update")
                
                # Try a more direct approach if the first attempt failed
                # First get the config_id to target the right record
                existing = client.table('config').select('config_id').execute()
                if existing.data:
                    config_id = existing.data[0]['config_id']
                    client.table('config').update({'status': 'DRAFT'}).eq('config_id', config_id).execute()
                    st.info(f"Direct update targeted config_id: {config_id}")
                else:
                    st.error("No config record found to update")
                
                # Verify again
                final_config = load_config()
                final_status = final_config.get('status', 'UNKNOWN')
                st.info(f"Final status after direct update: '{final_status}'")
                
        except Exception as config_error:
            st.error(f"Error updating config: {config_error}")
            # Try direct database update as fallback
            try:
                # Get the config_id to target the right record
                existing = client.table('config').select('config_id').execute()
                if existing.data:
                    config_id = existing.data[0]['config_id']
                    client.table('config').update({'status': 'DRAFT'}).eq('config_id', config_id).execute()
                    st.info(f"Used direct database update as fallback (config_id: {config_id})")
                else:
                    st.error("No config record found for fallback update")
            except Exception as direct_error:
                st.error(f"Direct update also failed: {direct_error}")
                return False
        
        return True
        
    except Exception as e:
        st.error(f"Error resetting demo state: {str(e)}")
        return False

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
        password = st.text_input("Enter Admin Password", type="password", key="password-input")
        if st.button("Login", key="login-button"):
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
    
    # Ensure params is properly initialized with defaults (moved here to use in status dashboard)
    default_params = get_default_engine_params()
    params: EngineParams = default_params.copy()  # Initialize with defaults first
    
    # Robust params initialization that handles all edge cases
    try:
        if config and 'params' in config and config['params'] and isinstance(config['params'], dict):
            # Merge config params with defaults, ensuring defaults take precedence for missing keys
            config_params = config['params']
            
            # First, update params with values from default_params
            for key, default_value in default_params.items():
                if key in config_params and config_params[key] is not None:
                    # Preserve the type from defaults
                    try:
                        if isinstance(default_value, (int, float)):
                            params[key] = type(default_value)(config_params[key])
                        else:
                            params[key] = config_params[key]
                    except (ValueError, TypeError):
                        # If conversion fails, keep default
                        params[key] = default_value
                else:
                    # Key missing or None in config, use default
                    params[key] = default_value
            
            # Then, add any additional runtime fields from config_params that aren't in defaults
            # This preserves fields like start_ts_ms, current_round, etc.
            for key, value in config_params.items():
                if key not in default_params and value is not None:
                    params[key] = value
                    
            # Ensure critical parameters are never missing
            critical_params = ['n_outcomes', 'z', 'gamma', 'q0', 'f', 'total_duration', 'final_winner']
            for param in critical_params:
                if param not in params or params[param] is None:
                    params[param] = default_params[param]
                    st.warning(f"Missing critical parameter '{param}', using default: {default_params[param]}")
                    
    except Exception as e:
        # If anything goes wrong, fall back to defaults
        st.error(f"Config initialization error: {e}. Using default parameters.")
        params = default_params.copy()
    
    # Demo Status Dashboard Section
    st.markdown("---")
    st.subheader("🎮 Demo Status")
    
    # Status display with visual indicators
    status_col1, status_col2, status_col3 = st.columns([1, 2, 1])
    
    with status_col1:
        # Status indicator with colors
        if status == 'DRAFT':
            st.markdown("**Status:** 🔵 DRAFT")
        elif status == 'RUNNING':
            st.markdown("**Status:** 🟢 RUNNING")
        elif status == 'FROZEN':
            st.markdown("**Status:** 🟡 FROZEN")
        elif status == 'RESOLVED':
            st.markdown("**Status:** 🔴 RESOLVED")
    
    with status_col2:
        # Countdown and progress information
        if status in ['RUNNING', 'FROZEN']:
            # Check if demo has started (has start timestamp in params)
            start_ts_ms = params.get('start_ts_ms', 0)
            if start_ts_ms > 0:
                current_ms = get_current_ms()
                elapsed_ms = current_ms - start_ts_ms
                elapsed_seconds = elapsed_ms // 1000
                
                # Format time display function
                def format_time(seconds):
                    mins, secs = divmod(int(seconds), 60)
                    hours, mins = divmod(mins, 60)
                    if hours > 0:
                        return f"{hours:02d}:{mins:02d}:{secs:02d}"
                    else:
                        return f"{mins:02d}:{secs:02d}"
                
                # Always show elapsed time
                st.markdown(f"**Elapsed:** {format_time(elapsed_seconds)}")
                
                # Get total duration from params
                total_duration_s = params.get('total_duration', 0)
                
                if total_duration_s > 0:
                    remaining_seconds = max(0, total_duration_s - elapsed_seconds)
                    
                    st.markdown(f"**Remaining:** {format_time(remaining_seconds)}")
                    
                    # Progress bar
                    progress = min(1.0, elapsed_seconds / total_duration_s)
                    st.progress(progress)
                    
                    # Show percentage
                    percentage = int(progress * 100)
                    st.markdown(f"**Progress:** {percentage}%")
                else:
                    st.markdown("**Duration:** Not configured")
                    st.info("💡 Set 'Total Duration' in configuration to see countdown timer")
            else:
                st.markdown("**Status:** Demo starting...")
                st.info("⏳ Initializing demo systems...")
        elif status == 'RESOLVED':
            st.markdown("**Demo Completed!** ✅")
            start_ts_ms = params.get('start_ts_ms', 0)
            if start_ts_ms > 0:
                current_ms = get_current_ms()
                total_elapsed = (current_ms - start_ts_ms) // 1000
                def format_time(seconds):
                    mins, secs = divmod(int(seconds), 60)
                    hours, mins = divmod(mins, 60)
                    if hours > 0:
                        return f"{hours:02d}:{mins:02d}:{secs:02d}"
                    else:
                        return f"{mins:02d}:{secs:02d}"
                st.markdown(f"**Total Duration:** {format_time(total_elapsed)}")
        else:
            st.markdown("**Ready to start demo**")
    
    with status_col3:
        # Multi-resolution progress (if enabled)
        mr_enabled = params.get('mr_enabled', False)
        if mr_enabled and status in ['RUNNING', 'FROZEN', 'RESOLVED']:
            current_round = config.get('current_round', 0)
            res_offsets = params.get('res_offsets', [])
            total_rounds = len(res_offsets)
            
            if total_rounds > 0:
                st.markdown(f"**Round:** {current_round + 1}/{total_rounds}")
                round_progress = (current_round + 1) / total_rounds
                st.progress(round_progress)
                st.markdown(f"**Round Progress:** {int(round_progress * 100)}%")
            else:
                st.markdown("**Multi-Resolution:** Enabled")
                st.info("Configure resolution offsets to see round progress")
        elif status in ['RUNNING', 'FROZEN', 'RESOLVED']:
            # Show single resolution mode info
            st.markdown("**Mode:** Single Resolution")
            if status == 'RUNNING':
                st.markdown("**Next:** Final resolution")
    
    st.markdown("---")
    
    # Config Form
    with st.expander("Configure Session", expanded=status == 'DRAFT'):
        with st.form(key="config_form"):
            col1, col2, col3 = st.columns(3)

            with col1:
                params['n_outcomes'] = st.number_input("Number of Outcomes", min_value=3, max_value=10, value=params['n_outcomes'])
                
                # Outcome Names Configuration
                st.subheader("📝 Outcome Names")
                # Ensure outcome_names list has the right length
                current_names = params.get('outcome_names', [])
                if len(current_names) != params['n_outcomes']:
                    # Adjust the list to match n_outcomes
                    if len(current_names) < params['n_outcomes']:
                        # Add default names for missing outcomes
                        for i in range(len(current_names), params['n_outcomes']):
                            current_names.append(f"Outcome {chr(65 + i)}")
                    else:
                        # Trim excess names
                        current_names = current_names[:params['n_outcomes']]
                    params['outcome_names'] = current_names
                
                # Create input fields for each outcome name
                outcome_names = []
                for i in range(params['n_outcomes']):
                    name = st.text_input(
                        f"Outcome {i + 1} Name", 
                        value=params['outcome_names'][i] if i < len(params['outcome_names']) else f"Outcome {chr(65 + i)}",
                        key=f"outcome_name_{i}"
                    )
                    outcome_names.append(name)
                params['outcome_names'] = outcome_names
                
                st.divider()
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
                # Multi-resolution configuration with proper validation
                try:
                    res_offsets_str = st.text_input("Resolution Offsets (JSON list)", value=json.dumps(params['res_offsets']))
                    if res_offsets_str.strip():
                        parsed_offsets = json.loads(res_offsets_str)
                        if not isinstance(parsed_offsets, list) or not all(isinstance(x, (int, float)) and x >= 0 for x in parsed_offsets):
                            st.error("Resolution offsets must be a list of non-negative numbers")
                            params['res_offsets'] = []
                        else:
                            params['res_offsets'] = parsed_offsets
                    else:
                        params['res_offsets'] = []
                except json.JSONDecodeError:
                    st.error("Invalid JSON format for resolution offsets")
                    params['res_offsets'] = []
                
                try:
                    freeze_durs_str = st.text_input("Freeze Durations (JSON list)", value=json.dumps(params['freeze_durs']))
                    if freeze_durs_str.strip():
                        parsed_freeze = json.loads(freeze_durs_str)
                        if not isinstance(parsed_freeze, list) or not all(isinstance(x, (int, float)) and x >= 0 for x in parsed_freeze):
                            st.error("Freeze durations must be a list of non-negative numbers")
                            params['freeze_durs'] = []
                        else:
                            params['freeze_durs'] = parsed_freeze
                    else:
                        params['freeze_durs'] = []
                except json.JSONDecodeError:
                    st.error("Invalid JSON format for freeze durations")
                    params['freeze_durs'] = []
                
                # Enhanced elim_outcomes validation per TDD requirements
                try:
                    elim_outcomes_str = st.text_input("Elim Outcomes (JSON list of lists for multi-res, int for final)", value=json.dumps(params['elim_outcomes']))
                    if elim_outcomes_str.strip():
                        parsed_elim = json.loads(elim_outcomes_str)
                        
                        # Validate based on multi-resolution mode
                        if params['mr_enabled']:
                            # Multi-resolution: must be list[list[int]]
                            if not isinstance(parsed_elim, list):
                                st.error("Multi-resolution elim_outcomes must be a list of lists (e.g., [[1], [2]])")
                                params['elim_outcomes'] = []
                            elif not all(isinstance(sublist, list) and all(isinstance(i, int) and 0 <= i < params['n_outcomes'] for i in sublist) for sublist in parsed_elim):
                                st.error("Each elimination round must be a list of valid outcome indices (0 to N-1)")
                                params['elim_outcomes'] = []
                            else:
                                # Validate total eliminations = N-1
                                total_eliminated = sum(len(round_elims) for round_elims in parsed_elim)
                                if total_eliminated != params['n_outcomes'] - 1:
                                    st.error(f"Total eliminated outcomes ({total_eliminated}) must equal N-1 ({params['n_outcomes'] - 1})")
                                    params['elim_outcomes'] = []
                                else:
                                    params['elim_outcomes'] = parsed_elim
                        else:
                            # Single resolution: must be int (final winner)
                            if isinstance(parsed_elim, int):
                                if 0 <= parsed_elim < params['n_outcomes']:
                                    params['elim_outcomes'] = parsed_elim
                                else:
                                    st.error(f"Final winner must be between 0 and {params['n_outcomes'] - 1}")
                                    params['elim_outcomes'] = 0
                            else:
                                st.error("Single resolution elim_outcomes must be an integer (final winner index)")
                                params['elim_outcomes'] = 0
                    else:
                        params['elim_outcomes'] = [] if params['mr_enabled'] else 0
                except json.JSONDecodeError:
                    st.error("Invalid JSON format for elim outcomes")
                    params['elim_outcomes'] = [] if params['mr_enabled'] else 0

            submitted = st.form_submit_button("Save Configuration")
            if submitted:
                try:
                    # Enhanced validation with comprehensive checks
                    validation_errors = []
                    
                    # Multi-resolution validation
                    if params['mr_enabled']:
                        if not isinstance(params['elim_outcomes'], list):
                            validation_errors.append("Multi-resolution requires elim_outcomes as list of lists")
                        elif params['elim_outcomes']:
                            total_eliminated = sum(len(elims) for elims in params['elim_outcomes'] if isinstance(elims, list))
                            if total_eliminated != params['n_outcomes'] - 1:
                                validation_errors.append(f"Sum of eliminated outcomes ({total_eliminated}) must equal N-1 ({params['n_outcomes'] - 1})")
                            
                            # Validate resolution timing consistency
                            if len(params['res_offsets']) != len(params['elim_outcomes']):
                                validation_errors.append("Resolution offsets and elim_outcomes must have same length")
                            if len(params['freeze_durs']) != len(params['elim_outcomes']):
                                validation_errors.append("Freeze durations and elim_outcomes must have same length")
                    
                    # Parameter range validation per TDD
                    if params['zeta_start'] >= 1.0 / (params['n_outcomes'] - 1):
                        validation_errors.append(f"zeta_start ({params['zeta_start']}) must be < 1/(N-1) = {1.0/(params['n_outcomes']-1):.4f}")
                    if params['zeta_end'] >= 1.0 / (params['n_outcomes'] - 1):
                        validation_errors.append(f"zeta_end ({params['zeta_end']}) must be < 1/(N-1) = {1.0/(params['n_outcomes']-1):.4f}")
                    
                    if params['p_min'] >= params['p_max']:
                        validation_errors.append(f"p_min ({params['p_min']}) must be < p_max ({params['p_max']})")
                    
                    if params['gamma'] >= 0.001:
                        validation_errors.append(f"gamma ({params['gamma']}) should be < 0.001 per TDD recommendations")
                    
                    # Timing validation
                    if params['total_duration'] <= 0:
                        validation_errors.append("Total duration must be positive")
                    
                    if validation_errors:
                        for error in validation_errors:
                            st.error(f"❌ {error}")
                        st.error("Please fix validation errors before saving")
                    else:
                        update_config({'params': params})
                        st.success("✅ Configuration saved and validated successfully")
                        
                except json.JSONDecodeError as json_error:
                    st.error(f"❌ JSON parsing error: {json_error}")
                except Exception as e:
                    st.error(f"❌ Configuration error: {e}")
                    st.exception(e)

    # Joined Users
    users = fetch_users()
    st.subheader(f"Joined Users ({len(users)})")
    st.table(users)

    # Controls
    st.subheader("Demo Controls")
    col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns(4)
    with col_ctrl1:
        # Debug information for Start Demo button
        st.caption(f"Debug: Status = '{status}', Can start = {status == 'DRAFT'}")
        
        start_button_clicked = st.button("Start Demo", key="start-demo-button")
        if start_button_clicked:
            if status == 'DRAFT':
                try:
                    # First, insert system users required for trading operations
                    st.info("Inserting system users...")
                    if not insert_system_users():
                        st.error("Failed to insert system users. Cannot start demo.")
                        return
                    
                    # Initialize engine state explicitly per TDD requirements
                    st.info("Initializing engine state...")
                    try:
                        from app.engine.state import init_state
                        from app.db.queries import save_engine_state, fetch_engine_state
                        
                        # Check if engine state already exists
                        existing_state = fetch_engine_state()
                        if not existing_state or not existing_state.get('binaries'):
                            st.info("Creating fresh engine state per TDD specification")
                            fresh_engine_state = init_state(params)
                            save_engine_state(fresh_engine_state)
                            st.success("✅ Engine state initialized successfully")
                        else:
                            st.info("Engine state already exists, preserving current state")
                    except Exception as state_error:
                        st.error(f"Failed to initialize engine state: {state_error}")
                        st.error("Cannot start demo without proper engine state")
                        return
                    
                    # Update config with current params and start demo
                    start_ts = get_current_ms()
                    st.info(f"Starting demo with timestamp: {start_ts}")
                    
                    # Fix parameter nesting issue - store timing at top level for timer_service compatibility
                    params_with_timing = params.copy()
                    params_with_timing['current_round'] = 0
                    
                    update_config({
                        'params': params_with_timing,
                        'status': 'RUNNING', 
                        'start_ts_ms': start_ts,  # Top-level for timer_service.py compatibility
                        'current_round': 0
                    })
                    
                    # Broadcast status change to all users via realtime
                    publish_demo_status_update('RUNNING', 'Demo has started! Trading is now active.')
                    
                    st.info("Config updated, starting services...")
                    
                    # Start services with health verification
                    try:
                        start_timer_service()
                        st.info("✅ Timer service started")
                        
                        start_batch_runner()
                        st.info("✅ Batch runner started")
                        
                        # Verify batch runner health immediately after startup
                        st.info("Verifying batch runner health...")
                        import time
                        time.sleep(2)  # Give services time to initialize
                        
                        try:
                            from app.runner.batch_runner import is_batch_runner_healthy, get_batch_runner_stats
                            
                            if is_batch_runner_healthy():
                                stats = get_batch_runner_stats()
                                st.success(f"✅ Batch runner is healthy (Thread: {stats.get('thread_alive', False)})")
                            else:
                                st.error("❌ Batch runner failed health check")
                                st.warning("Demo may not process orders correctly")
                                # Don't return - let demo start but warn user
                                
                        except ImportError:
                            st.warning("⚠️ Could not verify batch runner health (monitoring not available)")
                        except Exception as health_error:
                            st.warning(f"⚠️ Health check failed: {health_error}")
                        
                        st.success("🎉 Demo started successfully! Refreshing page...")
                        st.rerun()  # Force page refresh to show new status
                        
                    except Exception as service_error:
                        st.error(f"Failed to start services: {service_error}")
                        # Try to revert status back to DRAFT
                        try:
                            update_config({'status': 'DRAFT'})
                            st.info("Reverted status back to DRAFT due to service startup failure")
                        except:
                            pass
                        return
                    
                except Exception as e:
                    st.error(f"Error starting demo: {e}")
                    st.exception(e)
            else:
                st.warning(f"Cannot start demo. Current status is '{status}', but needs to be 'DRAFT'")
    with col_ctrl2:
        if st.button("Freeze Trading") and status == 'RUNNING':
            config['status'] = 'FROZEN'
            update_config({'status': 'FROZEN'})
            publish_demo_status_update('FROZEN', 'Trading has been frozen by admin.')
            st.success("Trading frozen.")
    with col_ctrl3:
        if st.button("Resume Trading") and status == 'FROZEN':
            config['status'] = 'RUNNING'
            update_config({'status': 'RUNNING'})
            publish_demo_status_update('RUNNING', 'Trading has been resumed by admin.')
            st.success("Trading resumed.")
    with col_ctrl4:
        # Reset Demo button with confirmation
        if st.button("🔄 Reset Demo", type="secondary", key="reset-demo-button"):
            # Use session state for confirmation dialog
            st.session_state.show_reset_confirmation = True
        
        # Show confirmation dialog if requested
        if st.session_state.get('show_reset_confirmation', False):
            st.warning("⚠️ This will completely reset the demo and clear all data!")
            col_confirm1, col_confirm2 = st.columns(2)
            with col_confirm1:
                if st.button("✅ Confirm Reset", type="primary", key="confirm-reset-button"):
                    # Reset all demo state
                    reset_success = reset_demo_state()
                    st.session_state.show_reset_confirmation = False
                    
                    if reset_success:
                        st.success("Demo reset completed! Please refresh the page manually to see the updated status.")
                        st.info("💡 Tip: Press F5 or refresh your browser to see the DRAFT status")
                    else:
                        st.error("Reset encountered errors. Check the messages above for details.")
                    
                    # Don't auto-refresh so user can see all messages
            with col_confirm2:
                if st.button("❌ Cancel"):
                    st.session_state.show_reset_confirmation = False
                    st.rerun()

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
            try:
                # Enhanced rankings export with post-resolution validation
                if status == 'RESOLVED':
                    st.info("🔍 Verifying post-resolution state for accurate rankings...")
                    
                    # Check if payouts have been applied
                    try:
                        from app.db.queries import fetch_engine_state
                        from app.services.resolutions import get_resolution_status
                        
                        engine_state = fetch_engine_state()
                        if engine_state:
                            # Verify resolution completeness
                            active_outcomes = [i for i, binary in enumerate(engine_state.get('binaries', [])) if binary.get('active', True)]
                            
                            if len(active_outcomes) == 1:
                                st.success(f"✅ Resolution complete - Winner: Outcome {active_outcomes[0]}")
                            elif len(active_outcomes) == 0:
                                st.warning("⚠️ No active outcomes found - this may indicate resolution issues")
                            else:
                                st.warning(f"⚠️ Multiple active outcomes ({len(active_outcomes)}) - resolution may be incomplete")
                            
                            # Check for unfilled LOB pools that need pro-rata distribution
                            lob_pools = engine_state.get('lob_pools', {})
                            unfilled_volume = sum(float(pool.get('volume', 0)) for pool in lob_pools.values() if float(pool.get('volume', 0)) > 0)
                            
                            if unfilled_volume > 0:
                                st.warning(f"⚠️ {unfilled_volume:.2f} USDC in unfilled LOB pools - pro-rata distribution may be needed")
                                st.info("💡 Rankings may not include unfilled limit order returns per TDD requirements")
                            else:
                                st.success("✅ All LOB pools cleared - no unfilled returns to distribute")
                        else:
                            st.warning("⚠️ Could not verify engine state - rankings may be incomplete")
                            
                    except Exception as verify_error:
                        st.warning(f"⚠️ Could not verify resolution state: {verify_error}")
                        st.info("Proceeding with rankings export but results may be incomplete")
                    
                    st.info("📊 Generating comprehensive rankings with final balances...")
                else:
                    st.info("📊 Generating current rankings (demo not yet resolved)...")
                
                # Generate the rankings CSV
                export_rankings_csv("rankings.csv")
                
                # Verify the file was created and has content
                if os.path.exists("rankings.csv"):
                    file_size = os.path.getsize("rankings.csv")
                    if file_size > 0:
                        st.success(f"✅ Rankings CSV generated ({file_size} bytes)")
                        with open("rankings.csv", "rb") as f:
                            st.download_button("Download Rankings CSV", f.read(), "rankings.csv")
                        os.remove("rankings.csv")
                    else:
                        st.error("❌ Rankings CSV is empty - no user data found")
                        if os.path.exists("rankings.csv"):
                            os.remove("rankings.csv")
                else:
                    st.error("❌ Failed to generate rankings CSV file")
                    
            except Exception as export_error:
                st.error(f"❌ Error generating rankings: {export_error}")
                st.info("💡 Rankings export requires user data and completed trades")
                if os.path.exists("rankings.csv"):
                    os.remove("rankings.csv")

    # Graph
    st.subheader("Performance Graph")
    if status == 'RESOLVED':
        try:
            generate_graph(output_path="graph.png")
            if os.path.exists("graph.png"):
                st.image("graph.png")
                os.remove("graph.png")
            else:
                st.warning("⚠️ No graph data available. This may be because no trading activity occurred during the demo.")
        except Exception as e:
            st.error(f"Error generating graph: {e}")
            st.info("💡 Graph generation requires trading activity and metrics data.")
    else:
        st.info("Graph available after resolution.")

    # Batch Runner Monitoring Section
    st.subheader("⚙️ Batch Runner Status")
    
    try:
        from app.runner.batch_runner import get_batch_runner_stats, is_batch_runner_healthy, restart_batch_runner_if_needed
        
        batch_stats = get_batch_runner_stats()
        is_healthy = is_batch_runner_healthy()
        
        # Health status indicator
        col_health1, col_health2, col_health3 = st.columns(3)
        
        with col_health1:
            if is_healthy:
                st.success("🟢 **Batch Runner: HEALTHY**")
            else:
                st.error("🔴 **Batch Runner: UNHEALTHY**")
                if st.button("🔄 Restart Batch Runner", type="primary"):
                    try:
                        restart_batch_runner_if_needed()
                        st.success("Batch runner restarted successfully!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to restart batch runner: {e}")
        
        with col_health2:
            st.metric("Thread Active", "✅ Yes" if batch_stats['is_active'] else "❌ No")
            st.metric("Thread Alive", "✅ Yes" if batch_stats['thread_alive'] else "❌ No")
        
        with col_health3:
            if batch_stats['last_tick_time']:
                import datetime
                time_since_tick = (datetime.datetime.now() - batch_stats['last_tick_time']).total_seconds()
                st.metric("Last Tick", f"{time_since_tick:.1f}s ago")
            else:
                st.metric("Last Tick", "Never")
        
        # Detailed statistics
        with st.expander("📈 Batch Runner Statistics", expanded=False):
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1:
                st.metric("Total Ticks", batch_stats['total_ticks'])
                st.metric("Thread Restarts", batch_stats['thread_restarts'])
            
            with col_stat2:
                st.metric("Orders Processed", batch_stats['total_orders_processed'])
                st.metric("Fills Generated", batch_stats['total_fills_generated'])
            
            with col_stat3:
                st.metric("Error Count", batch_stats['error_count'])
                if batch_stats['thread_id']:
                    st.metric("Thread ID", batch_stats['thread_id'])
            
            with col_stat4:
                if batch_stats['last_error']:
                    st.error(f"**Last Error:** {batch_stats['last_error']}")
                else:
                    st.success("**No Recent Errors**")
                
                # Processing rate
                if batch_stats['total_ticks'] > 0:
                    avg_orders_per_tick = batch_stats['total_orders_processed'] / batch_stats['total_ticks']
                    st.metric("Avg Orders/Tick", f"{avg_orders_per_tick:.2f}")
    
    except Exception as e:
        st.error(f"Error loading batch runner status: {e}")
        st.info("💡 Batch runner monitoring requires the enhanced batch runner implementation.")
    
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
    
    # Auto-refresh when demo is running to show real-time countdown
    # This is placed at the end so button interactions are processed first
    if status in ['RUNNING', 'FROZEN']:
        import time
        time.sleep(1)  # Refresh every 1 second
        st.rerun()

if __name__ == "__main__":
    run_admin_app()