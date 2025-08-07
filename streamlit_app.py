#!/usr/bin/env python3
"""
Main entry point for Streamlit Community Cloud deployment.
This file sets up the Python path and runs the actual app.
"""

import sys
import os

# Add the project root to Python path for app module imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now execute the original app file
exec(open(os.path.join(project_root, 'app', 'streamlit_app.py')).read())
