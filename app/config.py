from typing_extensions import TypedDict
import os
from dotenv import load_dotenv
from supabase import create_client, Client

def load_env() -> dict[str, str]:
    # Try to load from .env file (for local development)
    load_dotenv()
    
    required_vars = ['ADMIN_PASSWORD', 'SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'DATABASE_URL']
    env_vars = {}
    
    for key in required_vars:
        # First try environment variables (works locally and on cloud)
        value = os.getenv(key)
        
        # If not found, try Streamlit secrets (for Streamlit Community Cloud)
        if value is None:
            try:
                import streamlit as st
                if hasattr(st, 'secrets') and key in st.secrets:
                    value = st.secrets[key]
            except ImportError:
                # streamlit not available, continue with None
                pass
        
        env_vars[key] = value
        
        # Only raise error if we still don't have the value
        if value is None:
            raise ValueError(f"Missing required environment variable or secret: {key}. "
                           f"Please set it as an environment variable or add it to Streamlit secrets.")
    
    return env_vars

def get_supabase_client() -> Client:
    env = load_env()
    return create_client(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY'])

class EngineParams(TypedDict):
    n_outcomes: int
    outcome_names: list[str]
    z: float
    gamma: float
    q0: float
    f: float
    p_max: float
    p_min: float
    eta: float
    tick_size: float
    f_match: float
    sigma: float
    af_cap_frac: float
    af_max_pools: int
    af_max_surplus: float
    cm_enabled: bool
    af_enabled: bool
    mr_enabled: bool
    vc_enabled: bool
    mu_start: float
    mu_end: float
    nu_start: float
    nu_end: float
    kappa_start: float
    kappa_end: float
    zeta_start: float
    zeta_end: float
    interpolation_mode: str
    res_schedule: list[int]
    total_duration: int
    final_winner: int
    res_offsets: list[int]
    freeze_durs: list[int]
    elim_outcomes: list[list[int]] | int
    starting_balance: float
    gas_fee: float
    batch_interval_ms: int

def get_default_engine_params() -> EngineParams:
    return EngineParams(
        n_outcomes=3,
        outcome_names=["Outcome A", "Outcome B", "Outcome C"],
        z=1000.0,
        gamma=0.0001,
        q0=1000.0/6,  # (z/n_outcomes)/2 = (1000/3)/2 = 1000/6 to ensure p_yes = p_no = 0.5
        f=0.01,
        p_max=0.99,
        p_min=0.01,
        eta=2.0,
        tick_size=0.01,
        f_match=0.005,
        sigma=0.5,
        af_cap_frac=0.1,
        af_max_pools=3,
        af_max_surplus=0.05,
        cm_enabled=True,
        af_enabled=True,
        mr_enabled=False,
        vc_enabled=True,
        mu_start=2.0,
        mu_end=2.0,
        nu_start=1.0,
        nu_end=1.0,
        kappa_start=0.0,
        kappa_end=0.0,
        zeta_start=0.05,
        zeta_end=0.0,
        interpolation_mode='continue',
        res_schedule=[],
        total_duration=3600,
        final_winner=0,
        res_offsets=[],
        freeze_durs=[],
        elim_outcomes=0,
        starting_balance=1000.0,
        gas_fee=0.00,
        batch_interval_ms=5000,
    )