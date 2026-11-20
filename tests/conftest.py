"""Test-wide setup: tests are offline and must never send traces, even with a real `.env` on the machine.

`expat.config.get_settings()` exports `.env` into os.environ with override=False, so values set here win.
"""

import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
