# app/services/__init__.py

# This module serves as the package initializer for the services directory.
# It exports key service functions from submodules to facilitate easy imports
# in other parts of the application, such as streamlit_app.py, runners, and scripts.
# Exports are added as services modules are implemented.
from .orders import submit_order, cancel_order, get_user_orders, estimate_slippage
from .positions import fetch_user_positions, update_position_from_fill, apply_payouts
from .ticks import compute_summary, create_tick
from .resolutions import trigger_resolution_service
from .realtime import publish_event, publish_tick_update