"""Headless smoke tests of the Streamlit pages with `streamlit.testing.v1.AppTest` (Demo mode, offline)."""

from pathlib import Path

import demo_pipeline
import pipeline_adapter
import pytest
from streamlit.testing.v1 import AppTest

from expat.schemas.profile import Citizenship

APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture(autouse=True)
def _offline_and_fast(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(pipeline_adapter, "has_api_key", lambda: False)  # force Demo mode even with a .env
    monkeypatch.setattr(demo_pipeline, "_sleep", lambda _s: None)  # no streaming delays in tests


def _home() -> AppTest:
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def test_home_renders_empty_state_with_examples():
    at = _home()
    examples = [b for b in at.button if b.key and b.key.startswith("example-")]
    assert len(examples) == 4
    assert any("not legal or tax advice" in c.value for c in at.caption)


def test_example_prompt_produces_a_cited_answer():
    at = _home()
    next(b for b in at.button if b.key == "example-0").click().run()
    assert not at.exception, at.exception

    conv = at.session_state.conversations[at.session_state.current]
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert "[S1]" in conv["messages"][1]["content"]
    chip_keys = {b.key for b in at.button if b.key and b.key.endswith(("-S1", "-S2", "-T1"))}
    assert len(chip_keys) == 3


def test_chat_input_and_error_retry():
    at = _home()
    at.chat_input[0].set_value("simulate error").run()
    assert not at.exception, at.exception
    assert at.error, "the ErrorEvent should render as st.error"
    retry = next(b for b in at.button if b.key and b.key.startswith("retry-"))
    retry.click().run()
    assert not at.exception, at.exception
    conv = at.session_state.conversations[at.session_state.current]
    assert len(conv["messages"]) == 2  # failed turn replaced by the retried one


def test_profile_form_saves_to_session_state():
    at = _home()
    at.selectbox(key="pf_citizenship").set_value(Citizenship.NON_EU)
    at.selectbox(key="pf_children_count").set_value(2)
    at.selectbox(key="pf_youngest_child_age").set_value(3)
    next(b for b in at.button if b.label == "Save profile").click().run()
    assert not at.exception, at.exception
    profile = at.session_state.profile
    assert profile.children_count == 2 and profile.youngest_child_age == 3
    assert profile.citizenship.value == "non_eu"
