# state.py_context.md

## Overview
Manages the deterministic EngineState for the AMM, encapsulating per-binary variables (V, L, q_yes/no, virtual_yes, etc.) and global pre_sum_yes for multi-resolution renormalization. Provides initialization, serialization/deserialization for DB JSONB, and helper functions for access/updates per TDD state management and implementation plan's engine package.

## Key Exports/Interfaces
- `class BinaryState(TypedDict)`: Per-outcome dict with keys: outcome_i (int), V (float), subsidy (float), L (float), q_yes (float), q_no (float), virtual_yes (float), seigniorage (float), active (bool), lob_pools (Dict[str, Dict[str, Dict[int, Dict[str, Any]]]]: 'YES'/'NO' -> 'buy'/'sell' -> tick: {'volume': float, 'shares': Dict[str, float]}).
- `class EngineState(TypedDict)`: Top-level dict with keys: binaries (List[BinaryState]), pre_sum_yes (float).
- `init_state(params: Dict[str, Any]) -> EngineState`: Initializes state from params (n_outcomes, z, gamma, q0); sets initial subsidy_i = z/n_outcomes, L_i = subsidy_i, q_yes/no = q0, virtual_yes=0, active=True, empty lob_pools; pre_sum_yes = n_outcomes * (q0 / subsidy_i).
- `serialize_state(state: EngineState) -> Dict[str, Any]`: Converts state to JSON-compatible dict, stringifying int tick keys in lob_pools.
- `deserialize_state(json_dict: Dict[str, Any]) -> EngineState`: Restores state from JSON dict, int-ifying str tick keys in lob_pools.
- `get_binary(state: EngineState, outcome_i: int) -> BinaryState`: Retrieves BinaryState for given outcome_i; raises ValueError if not found.
- `get_p_yes(binary: BinaryState) -> float`: Computes p_yes = (q_yes + virtual_yes) / L.
- `get_p_no(binary: BinaryState) -> float`: Computes p_no = q_no / L.
- `update_subsidies(state: EngineState, params: Dict[str, Any]) -> None`: Recomputes subsidy_i = max(0, z/n_outcomes - gamma * V_i) and L_i for all binaries.

## Dependencies/Imports
- Imports: typing_extensions (TypedDict), typing (List, Dict, Any).
- Interactions: Params from engine/params.py; state used/updated in engine/orders.py (e.g., V_i += f_i * X), engine/resolutions.py (virtual_yes adjustments); serialized to DB via db/queries.py; no numpy here but assumes float precision for tests.

## Usage Notes
- State JSONB-compatible for Supabase storage; use serialize/deserialize for DB I/O. Tie to TDD invariants (q_yes_eff < L_i); update subsidies after any V changes. Deterministic: No random; init sets p_yes/no=0.5. For tests: Validate init matches TDD defaults, serialization round-trips, p computations align with derivations.

## Edge Cases/Invariants
- Invariants: subsidy >=0, L = V + subsidy >0, q_yes/no >= q0 initially, virtual_yes >=0 (capped in resolutions), active binaries only for computations (N_active from count(active)). Edges: Zero subsidy (trades continue); negative virtual_yes capped (vc_enabled); empty lob_pools; raises on invalid outcome_i. Assumes params valid per TDD ranges; solvency q_yes + q_no < 2*L (enforced in orders). Deterministic with float ops.