import argparse
import json
from typing import Dict, Any

from app.config import EngineParams, get_default_engine_params
from app.db.queries import load_config, update_config


def seed_config(overrides: Dict[str, Any] = None) -> None:
    """
    Seeds the initial configuration into the DB using defaults, with optional overrides.
    Upserts the config row with params as JSONB, status='DRAFT', start_ts=None, current_tick=0.
    """
    # Load existing config if any, but we'll overwrite with defaults + overrides
    existing_config = load_config()
    default_params: EngineParams = get_default_engine_params()

    # Apply overrides if provided
    params_dict: Dict[str, Any] = dict(default_params)
    if overrides:
        for key, value in overrides.items():
            if key in params_dict:
                params_dict[key] = value
            else:
                print(f"Warning: Override key '{key}' not in EngineParams.")

    # Prepare full config dict (params as sub-dict, but update_config takes params dict directly)
    # Assuming update_config serializes params to JSONB
    update_config(params_dict)

    print("Config seeded successfully with defaults and overrides.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial config into DB with optional overrides.")
    parser.add_argument("--n_outcomes", type=int, help="Number of outcomes")
    parser.add_argument("--z", type=float, help="Initial subsidy")
    parser.add_argument("--gamma", type=float, help="Subsidy phase-out rate")
    parser.add_argument("--q0", type=float, help="Initial virtual supply")
    parser.add_argument("--f", type=float, help="Fee fraction")
    parser.add_argument("--p_max", type=float, help="Maximum price")
    parser.add_argument("--p_min", type=float, help="Minimum price")
    parser.add_argument("--eta", type=float, help="Penalty exponent")
    parser.add_argument("--tick_size", type=float, help="Tick granularity")
    parser.add_argument("--f_match", type=float, help="Match fee fraction")
    parser.add_argument("--sigma", type=float, help="Seigniorage share")
    parser.add_argument("--af_cap_frac", type=float, help="Auto-fill volume cap fraction")
    parser.add_argument("--af_max_pools", type=int, help="Max pools per auto-fill")
    parser.add_argument("--af_max_surplus", type=float, help="Max surplus per trade")
    parser.add_argument("--cm_enabled", type=bool, help="Cross-match enabled")
    parser.add_argument("--af_enabled", type=bool, help="Auto-fill enabled")
    parser.add_argument("--mr_enabled", type=bool, help="Multi-resolution enabled")
    parser.add_argument("--vc_enabled", type=bool, help="Virtual cap enabled")
    parser.add_argument("--mu_start", type=float, help="Mu start")
    parser.add_argument("--mu_end", type=float, help="Mu end")
    parser.add_argument("--nu_start", type=float, help="Nu start")
    parser.add_argument("--nu_end", type=float, help="Nu end")
    parser.add_argument("--kappa_start", type=float, help="Kappa start")
    parser.add_argument("--kappa_end", type=float, help="Kappa end")
    parser.add_argument("--zeta_start", type=float, help="Zeta start")
    parser.add_argument("--zeta_end", type=float, help="Zeta end")
    parser.add_argument("--interpolation_mode", type=str, help="Interpolation mode ('reset' or 'continue')")
    parser.add_argument("--res_schedule", type=str, help="Resolution schedule as JSON list (e.g., '[1,1]')")
    parser.add_argument("--total_duration", type=int, help="Total duration in seconds")
    parser.add_argument("--final_winner", type=int, help="Final winner outcome index")
    parser.add_argument("--res_offsets", type=str, help="Resolution offsets as JSON list")
    parser.add_argument("--freeze_durs", type=str, help="Freeze durations as JSON list")
    parser.add_argument("--elim_outcomes", type=str, help="Elim outcomes as JSON list of lists")
    parser.add_argument("--starting_balance", type=float, help="Starting user balance")
    parser.add_argument("--gas_fee", type=float, help="Gas fee per transaction")
    parser.add_argument("--batch_interval_ms", type=int, help="Batch interval in ms")

    args = parser.parse_args()
    overrides = {k: v for k, v in vars(args).items() if v is not None}
    
    # Handle JSON string args
    if "res_schedule" in overrides:
        overrides["res_schedule"] = json.loads(overrides["res_schedule"])
    if "res_offsets" in overrides:
        overrides["res_offsets"] = json.loads(overrides["res_offsets"])
    if "freeze_durs" in overrides:
        overrides["freeze_durs"] = json.loads(overrides["freeze_durs"])
    if "elim_outcomes" in overrides:
        overrides["elim_outcomes"] = json.loads(overrides["elim_outcomes"])

    seed_config(overrides)