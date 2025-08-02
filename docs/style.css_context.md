# style.css_context.md

## Overview
Static CSS file for customizing Streamlit UI to resemble Polymarket aesthetics: dark theme, green/red accents for YES/NO/Buy/Sell, rounded elements, shadows for depth. Enhances trading panels, tabs, forms, tables, and responsiveness for demo hype.

## Key Exports/Interfaces
- No exports; pure CSS selectors targeting Streamlit classes (e.g., .stTabs, .stButton, .stDataFrame) and custom elements (e.g., .countdown if added).
- Global styles: body (dark bg #1A1A1A, sans-serif), headings (white).
- Component styles:
  - Tabs: Pill-shaped, active green (#00FF00).
  - Buttons: Gray bg, primary green, hover effects.
  - Radio: Green for YES/Buy, red (#FF0000) for NO/Sell.
  - Forms: Dark padded boxes with shadows.
  - Tables: Striped dark, bid green/ask red columns.
  - Sidebar: Darker bg for leaderboard.
  - Messages: Colored for error/success.
  - Media query: Responsive for <768px.

## Dependencies/Imports
- No imports; loaded via st.markdown in streamlit_app.py and streamlit_admin.py (unsafe_allow_html=True).
- Interactions: Applies to UI elements like outcome tabs (st.tabs), order tickets (st.form), books/trades (st.table/st.dataframe), metrics (st.metric).

## Usage Notes
- Reference Polymarket: Clean, intuitive; use for tabs (outcomes), radios (YES/NO, Buy/Sell), forms (tickets with confirmation expanders), tables (books with bid/ask colors, trades/positions).
- Dark mode for hype; green/red for visual excitement per TDD user implications.
- Static file; no dynamic CSS; ensure fast load (<1KB).

## Edge Cases/Invariants
- Cross-browser: Basic styles, no prefixes needed for demo.
- Invariants: Dark theme consistent; colors reinforce YES/NO (green positive, red negative); responsive for mobile demo users.
- Deterministic: No variables; applies uniformly to all Streamlit renders.