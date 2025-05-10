"""
Simple runner script for the new_dub package.
This file can be run directly from the command line:
python run_new_dub.py
"""

import os
import sys

# Ensure the project root is in PYTHONPATH to allow absolute imports for the new_dub package
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from new_dub.main import main_new_dub
except ImportError as e:
    print(f"Error importing main_new_dub: {e}")
    print("Please ensure that the script is run from the 'live-dub' directory,")
    print("or that 'live-dub' is in your PYTHONPATH.")
    sys.exit(1)

if __name__ == "__main__":
    main_new_dub()
