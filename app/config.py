from typing_extensions import TypedDict
import os
from dotenv import load_dotenv
from supabase import create_client, Client

def load_env() -> dict[str, str]:
    load_dotenv()
    required_vars = ['ADMIN_PASSWORD', 'SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'DATABASE_URL']
    env_vars = {key: os.getenv(key) for key in required_vars}
    for key, value in env_vars.items():
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
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
    elim_outcomes: list[list[int]]
    starting_balance: float
    gas_fee: float
    batch_interval_ms: int

def get_default_engine_params() -> EngineParams:
    return EngineParams(
        n_outcomes=3,
        outcome_names=["Outcome A", "Outcome B", "Outcome C"],
        z=10000.0,
        gamma=0.0001,
        q0=10000.0/6,  # (z/n_outcomes)/2 = (10000/3)/2 = 10000/6 to ensure p_yes = p_no = 0.5
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
        mu_start=1.0,
        mu_end=1.0,
        nu_start=1.0,
        nu_end=1.0,
        kappa_start=0.001,
        kappa_end=0.001,
        zeta_start=0.1,
        zeta_end=0.1,
        interpolation_mode='continue',
        res_schedule=[],
        total_duration=3600,
        final_winner=0,
        res_offsets=[],
        freeze_durs=[],
        elim_outcomes=[],
        starting_balance=1000.0,
        gas_fee=0.0,
        batch_interval_ms=1000,
    )