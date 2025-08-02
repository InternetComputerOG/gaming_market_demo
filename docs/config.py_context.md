## Overview
Handles loading environment variables from .env, initializing Supabase client, and providing default EngineParams for session configuration. Short utility file for centralizing config access, used across DB, services, and runners per implementation plan.

## Key Exports/Interfaces
- `load_env() -> dict[str, str]`: Loads and validates required env vars (ADMIN_PASSWORD, SUPABASE_URL, SUPABASE_SERVICE_KEY, DATABASE_URL); raises ValueError if missing.
- `get_supabase_client() -> Client`: Creates and returns Supabase client using loaded env vars.
- `class EngineParams(TypedDict)`: Defines session params per TDD (e.g., n_outcomes: int, z: float, gamma: float, q0: float, f: float, p_max: float, p_min: float, eta: float, tick_size: float, f_match: float, sigma: float, af_cap_frac: float, af_max_pools: int, af_max_surplus: float, cm_enabled: bool, af_enabled: bool, mr_enabled: bool, vc_enabled: bool, mu_start/end: float, nu_start/end: float, kappa_start/end: float, zeta_start/end: float, interpolation_mode: str, res_schedule: list[int]) plus demo fields (total_duration: int, final_winner: int, res_offsets: list[int], freeze_durs: list[int], elim_outcomes: list[list[int]], starting_balance: float, gas_fee: float, batch_interval_ms: int).
- `get_default_engine_params() -> EngineParams`: Returns default TypedDict with values per TDD defaults (e.g., n_outcomes=3, z=10000.0, gamma=0.0001) and demo settings (e.g., gas_fee=0.0, batch_interval_ms=1000).

## Dependencies/Imports
- Imports: os (path handling), dotenv (load_dotenv), typing_extensions (TypedDict), supabase (create_client, Client).
- Interactions: Provides env dict and Supabase client to db/queries.py for connections; EngineParams used in engine/params.py for interpolation, services/* for validation, runner/* for intervals; JSONB-compatible for DB storage in config table.

## Usage Notes
- Central config loader; fetch/override params from DB config table (jsonb) in production flows. Supports dynamic params per TDD addendum (start/end values, interpolation_mode 'reset'/'continue'). Use for admin config form in streamlit_admin.py. JSON-serializable for state persistence.

## Edge Cases/Invariants
- Env vars must exist or raise error; defaults ensure safe ranges (e.g., zeta_start <=1/(n_outcomes-1)). Assumes single session (no room_id); params immutable post-load for determinism. For tests: Validate TypedDict keys match TDD table; check defaults align with design (e.g., mu_start=1.0 for asymmetry).