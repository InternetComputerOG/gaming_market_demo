```markdown
# app_services__init__.py Context

## Overview
Package initializer for /app/services, exporting key service functions from submodules (e.g., orders.py, positions.py) for easy imports in UI (streamlit_app.py), runners (batch_runner.py), and scripts. Minimal file with no logic, focusing on relative imports per Implementation Plan section 11.

## Key Exports/Interfaces
- Exports: 
  - from .orders import submit_order, validate_order, cancel_order  # Order submission/validation/cancellation.
  - from .positions import update_positions, update_balances, process_payouts  # Position/balance updates, payouts handling.
  - from .ticks import process_tick_summary, update_metrics  # Tick summaries and metrics computation.
  - from .resolutions import trigger_resolution_service  # Resolution triggering and renormalization.
  - from .realtime import publish_event, subscribe_to_channel  # Realtime event publishing/subscriptions via Supabase.

## Dependencies/Imports
- No direct imports; relies on submodules for functionality.
- Interacts with: db/queries.py (via services for DB ops), engine/* (via services for deterministic calls), config.py (env vars), utils.py (validation helpers).

## Usage Notes
- Use for relative imports in higher-level modules (e.g., import services.orders.submit_order).
- Supports demo integration: Services handle validation (e.g., slippage/gas checks), engine calls (apply_orders), DB updates (JSONB state), realtime pushes per Implan section 3/6.
- Essential for batch_runner/timer_service: Call exported functions for tick/resolution processing.

## Edge Cases/Invariants
- Invariants: Exports must match submodule definitions; no runtime logic, so no edges.
- Assumptions: Submodules generated sequentially; deterministic via engine underneath.
- For tests: No direct tests; indirectly via engine/tests (e.g., mock services for integration).
```