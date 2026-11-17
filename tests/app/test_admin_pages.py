"""AppTest smoke tests for the admin pages: empty states, demo data, populated data and the password gate."""

import json
from datetime import date
from pathlib import Path

import pipeline_adapter
import pytest
from demo_pipeline import CORPUS
from streamlit.testing.v1 import AppTest

from expat.config import get_settings

PAGES = Path(__file__).resolve().parents[2] / "app" / "pages"
DEBUGGER = "1_🔎_Retrieval_Debugger.py"
BROWSER = "2_📚_Collection_Browser.py"
EVALS = "3_📊_Evals.py"
INGESTION = "4_⚙️_Ingestion_Status.py"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Point Settings.data_dir at an empty temp dir (Settings is lru_cached, so clear it around the test)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline_adapter, "has_api_key", lambda: False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _run(page: str, **secrets) -> AppTest:
    at = AppTest.from_file(str(PAGES / page), default_timeout=30)
    for k, v in secrets.items():
        at.secrets[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("page", [DEBUGGER, BROWSER, EVALS, INGESTION])
def test_pages_render_empty_states(page):
    _run(page)


def test_debugger_retrieves_on_demo_data():
    at = _run(DEBUGGER)
    next(b for b in at.button if b.label == "Retrieve").click().run()
    assert not at.exception, at.exception
    assert at.session_state.debug_run["result"].sub_results
    # The R0 preset flips the checkboxes through its on_click callback.
    next(b for b in at.button if b.label == "R0 baseline").click().run()
    assert at.session_state["cfg_use_bm25"] is False


def test_collection_browser_with_chunks(data_dir):
    processed = data_dir / "processed"
    processed.mkdir()
    lines = [
        json.dumps({"text": text, "embed_text": text, "metadata": meta.model_dump(mode="json")})
        for meta, text, _ in CORPUS
    ]
    (processed / "chunks.jsonl").write_text("\n".join(lines), encoding="utf-8")
    at = _run(BROWSER)
    assert at.dataframe, "the chunk table should render"


def test_ingestion_status_with_manifest(data_dir):
    processed = data_dir / "processed"
    processed.mkdir()
    manifest = {
        "bgb": {"status": "ok", "chunks": 120, "fetched_at": str(date(2026, 11, 18))},
        "bmg": {"status": "failed", "chunks": 0, "error": "timeout"},
    }
    (processed / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    at = _run(INGESTION)
    assert at.metric[1].value == "1"


def test_evals_sample_preview():
    at = _run(EVALS)
    if at.toggle:  # only present when there are no real results in evals/results/
        at.toggle[0].set_value(True).run()
        assert not at.exception, at.exception
        assert at.dataframe


def test_admin_gate_blocks_until_password():
    at = _run(INGESTION, ADMIN_PASSWORD="s3cret")
    assert at.text_input[0].label == "Admin password"
    assert not at.title  # page content is not rendered behind the gate
    at.text_input[0].input("s3cret")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state.admin_ok
