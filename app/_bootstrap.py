"""Make the `expat` package importable in every environment. Import this FIRST in every page.

- Locally, `uv run streamlit run app/Home.py` already has `expat` installed (uv installs the project in
  editable mode), so this is a no-op.
- On Streamlit Community Cloud, dependencies come from `app/requirements.txt`, which lists third-party
  packages only (`uv export --no-emit-project`), because a relative `-e .` line is resolved differently by
  pip and uv. So we put `<repo>/src` on `sys.path` instead (the src-layout equivalent of `-e .`).

Streamlit itself puts the entrypoint's directory (`app/`) on `sys.path`, which is why the pages can
`import ui`, `import demo_pipeline` etc. without `app/` being a package.
"""

import sys
from pathlib import Path

try:
    import expat  # noqa: F401
except ImportError:  # pragma: no cover - only on Cloud / bare `streamlit run`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
