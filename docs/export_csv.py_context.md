# export_csv.py_context.md

## Overview
Script for generating CSV exports of trades, config, metrics, and user rankings (including gas costs, % gain/loss) per impl plan §7/§13, using pandas for data processing and writing.

## Key Exports/Interfaces
- `fetch_trades(client: Client) -> List[Dict[str, Any]]`: Fetches all trades from DB, sorted by ts_ms.
- `fetch_metrics(client: Client) -> List[Dict[str, Any]]`: Fetches all metrics from DB, sorted by tick_id.
- `export_trades_csv(filename: str) -> None`: Exports trades DataFrame to CSV with 6-decimal precision.
- `export_config_csv(filename: str) -> None`: Flattens config params JSONB to DataFrame and exports to CSV.
- `export_metrics_csv(filename: str) -> None`: Exports metrics DataFrame to CSV with 6-decimal precision.
- `export_rankings_csv(filename: str) -> None`: Computes user rankings (final_usdc, pnl, pct_gain_loss using safe_divide, trade_count, gas_costs = gas_fee * trade_count), sorts by pct_gain_loss descending, exports to CSV.

## Dependencies/Imports
- Imports: pandas (pd), typing (List, Dict), decimal (Decimal), supabase (Client).
- From app.config: get_supabase_client.
- From app.utils: safe_divide.
- From app.db.queries: load_config, fetch_users.
- Interactions: Uses Supabase client for table selects (trades/metrics); load_config for params; fetch_users for rankings; called by streamlit_admin.py for export buttons.

## Usage Notes
- Use Decimal for computations (balance, gas_cost, pnl), convert to float for CSV; float_format='%.6f' for USDC precision. Flatten params dict for config export. Rankings incorporate gas deductions in pnl/% gain/loss per TDD/impl fee model.

## Edge Cases/Invariants
- Empty results: Exports empty CSV. Zero starting_balance: safe_divide handles div-by-zero (returns 0). Deterministic: Sorts by ts_ms/tick_id/user pct. Assumes config params exist (starting_balance, gas_fee); post-resolution balances include payouts. Invariants: pnl = balance - starting_balance; gas_cost >=0.