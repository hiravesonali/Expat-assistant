"""Put `app/` on sys.path, like `streamlit run app/Home.py` does, so tests can import the app modules."""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
