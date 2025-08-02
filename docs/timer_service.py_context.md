# timer_service.py_context.md

## Overview
Background service for monitoring real-time countdowns, triggering automatic intermediate/final resolutions, enforcing trading freezes, and updating status per impl plan §6-7 and TDD multi-resolution mechanics. Runs as a daemon thread, checking timings against config offsets/durations.

## Key Exports/Interfaces
- `start_timer_service() -> None`: Initializes start_ts_ms if unset, updates config status to 'RUNNING', launches monitor_loop thread.
- `monitor_loop() -> None`: Infinite loop: Loads config, computes elapsed_ms, checks for next resolution offset (mr_enabled) or total_duration; freezes status, calls trigger_resolution_service, publishes update, sleeps for freeze_dur, resumes or resolves status.

## Dependencies/Imports
- Imports: threading, time, typing (Dict, Any, Union).
- From app.config: EngineParams, get_supabase_client (unused directly).
- From app.utils: get_current_ms.
- From app.db.queries: load_config, update_config.
- From app.services.resolutions: trigger_resolution_service.
- From app.services.realtime: publish_resolution_update.
- Interactions: Updates config table (status, current_round, start_ts_ms); calls resolutions.py for engine triggers; publishes via realtime.py; assumes batch_runner.py pauses on 'FROZEN' status.

## Usage Notes
- Use ms timestamps for determinism; supports mr_enabled (rounds via res_offsets/elim_outcomes/freeze_durs) or single final (total_duration/final_winner). Sleep(1) for checks; publish for UI countdowns. Tie to TDD: Prepares pre_sum_yes implicitly via state; interpolates params if dynamic (but not handled here). JSON-compatible config updates.

## Edge Cases/Invariants
- Invariants: Status transitions deterministic (RUNNING -> FROZEN -> RUNNING/RESOLVED); current_round increments to len(res_offsets); elapsed_ms >= offset exact. Edges: No mr_enabled (single final); zero freeze_dur (immediate resume); t=0/end handled; no active outcomes raises in resolutions.py. Deterministic: Sort elim_outcomes if list; assumes valid config (e.g., sum(elim) = N-1). For tests: Mock time/config for trigger sims, verify status sequences/publishes.