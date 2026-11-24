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
    # the tenancy suggestion: its demo answer cites two sources and one tool result
    next(b for b in at.button if b.key and b.key.startswith("example-") and "notice" in (b.help or "")).click().run()
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


def test_punctuation_only_question_is_rejected_and_not_answered():
    at = _home()
    at.chat_input[0].set_value("???").run()
    assert not at.exception, at.exception
    assert any("Please type a question" in w.value for w in at.warning)
    assert not at.session_state.conversations[at.session_state.current]["messages"]


def test_export_buttons_appear_once_the_chat_has_messages():
    at = _home()
    assert not at.get("download_button")  # nothing to export on the start screen
    next(b for b in at.button if b.key and b.key.startswith("example-")).click().run()
    assert not at.exception, at.exception
    labels = [d.proto.label for d in at.get("download_button")]
    assert labels == ["PDF (.pdf)", "Markdown (.md)", "CSV (.csv)", "JSON (.json)"]


def test_help_guide_opens_and_an_example_from_it_is_asked():
    at = _home()
    assert not at.tabs  # closed by default
    at.button(key="help-open").click().run()
    assert not at.exception, at.exception
    assert [tab.label for tab in at.tabs] == ["Topics", "How to ask", "Reading an answer", "Limits & privacy"]
    assert any("20 Live questions per hour" in m.value for m in at.markdown)  # limits come from the settings
    at.button(key="help-try-2").click().run()  # "Renting"
    assert not at.exception, at.exception
    messages = at.session_state.conversations[at.session_state.current]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"] and "give notice" in messages[0]["content"]
    assert not at.tabs  # the guide closed itself


def test_help_guide_has_the_same_shape_in_both_languages():
    import i18n

    en, de = i18n.HELP["en"], i18n.HELP["de"]
    assert en.keys() == de.keys()
    assert all(len(en[k]) == len(de[k]) for k in en)
    for guide in (en, de):  # every bullet list must survive .format with the three limit values
        for key in ("how", "reading", "limits"):
            "\n".join(guide[key]).format(max_chars=1, per_hour=1, voice_seconds=1)


def test_which_city_follow_up_saves_the_city_and_answers_the_original_question(monkeypatch):
    """Pipeline asks for the city -> user clicks "Berlin" -> profile updated, question re-asked and answered."""
    from expat.schemas import ClarificationEvent, DoneEvent, TokenEvent

    def fake_run(mode, question, history, profile):
        if profile.city is None:
            yield TokenEvent(text="Which city do you live in?")
            yield ClarificationEvent(
                original_question=question, options=[("berlin", "Berlin"), ("other", "Other city")]
            )
        else:
            yield TokenEvent(text=f"Answer for {profile.city}.")
        yield DoneEvent()

    monkeypatch.setattr(pipeline_adapter, "run_pipeline", fake_run)
    at = _home()
    at.chat_input[0].set_value("Where do I register my address?").run()
    assert not at.exception, at.exception
    next(b for b in at.button if b.key == "pick-city-berlin").click().run()
    assert not at.exception, at.exception

    assert at.session_state.profile.city == "berlin" and at.session_state.profile.state == "BE"
    conv = at.session_state.conversations[at.session_state.current]
    assert [m["content"] for m in conv["messages"]] == ["Where do I register my address?", "Answer for berlin."]


def test_budget_errors_become_an_actionable_message_without_provider_links():
    from expat.schemas import ErrorEvent

    raw = ErrorEvent(
        code="retrieval_failed",
        message="Error code: 403 - Key limit exceeded (total limit). Manage it using https://openrouter.ai/x",
        retryable=True,
    )
    friendly = pipeline_adapter.friendly_error(raw)
    assert friendly.code == "budget_exhausted" and not friendly.retryable
    assert "openrouter.ai" not in friendly.message and "Live answers" in friendly.message
    other = ErrorEvent(code="generation_failed", message="timeout", retryable=True)
    assert pipeline_adapter.friendly_error(other) is other


def test_english_is_the_default_for_interface_and_answers():
    at = _home()
    assert at.session_state.lang == "en" and at.session_state.profile.answer_language == "en"
    assert at.segmented_control(key="lang_switch").value == "en"
    assert any("not legal or tax advice" in c.value for c in at.caption)


def test_switching_to_german_translates_the_interface_and_the_answer_language():
    at = _home()
    at.segmented_control(key="lang_switch").set_value("de").run()
    assert not at.exception, at.exception
    assert at.session_state.lang == "de" and at.session_state.profile.answer_language == "de"
    card = next(b for b in at.button if b.key == "example-1")
    assert "Wohnung kündigen" in card.label and "kündige" in (card.help or "")
    assert any("keine Rechts- oder Steuerberatung" in c.value for c in at.caption)


def test_budget_exhausted_offers_demo_answers_and_switches_live_off(monkeypatch):
    from expat.schemas import DoneEvent, ErrorEvent, TokenEvent

    def fake_run(mode, question, history, profile):
        if mode == pipeline_adapter.LIVE:
            yield ErrorEvent(code="budget_exhausted", message="Live answers are paused.", retryable=False)
        else:
            yield TokenEvent(text=f"Demo answer to: {question}")
        yield DoneEvent()

    monkeypatch.setattr(pipeline_adapter, "has_api_key", lambda: True)  # Live available
    monkeypatch.setattr(pipeline_adapter, "live_status", lambda: (True, ""))
    monkeypatch.setattr(pipeline_adapter, "run_pipeline", fake_run)
    at = _home()
    at.chat_input[0].set_value("what should i do for the anmeldung").run()
    assert not at.exception, at.exception
    assert any("paused" in i.value for i in at.info) and not at.error  # calm notice, not a red error
    next(b for b in at.button if b.key and b.key.startswith("demo-")).click().run()
    assert not at.exception, at.exception
    assert at.session_state.live_toggle is False
    conv = at.session_state.conversations[at.session_state.current]
    assert conv["messages"][-1]["content"] == "Demo answer to: what should i do for the anmeldung"


# ------------------------------------------------------------------------------------------- voice


def _live_with_fake_pipeline(monkeypatch) -> None:
    """Live mode without network: the pipeline answers with one token, speech calls are replaced per test."""
    from expat.schemas import DoneEvent, TokenEvent

    def fake_run(mode, question, history, profile):
        yield TokenEvent(text=f"Answer to: {question} [S1]")
        yield DoneEvent()

    monkeypatch.setattr(pipeline_adapter, "has_api_key", lambda: True)
    monkeypatch.setattr(pipeline_adapter, "live_status", lambda: (True, ""))
    monkeypatch.setattr(pipeline_adapter, "run_pipeline", fake_run)


def _clip(seconds: float) -> bytes:
    from expat import speech

    return speech.pcm_to_wav(b"\x00\x00" * int(16000 * seconds), 16000)


def test_voice_question_is_transcribed_and_answered_like_a_typed_one(monkeypatch):
    from expat import speech

    _live_with_fake_pipeline(monkeypatch)
    monkeypatch.setattr(
        speech, "transcribe", lambda audio: speech.Transcript("Do I need an Anmeldung?", 3.0, 0.0002, "stt-model")
    )
    at = _home()
    at.session_state.pending_audio = _clip(3)  # what the hero composer stores for a recording
    at.run()
    assert not at.exception, at.exception

    conv = at.session_state.conversations[at.session_state.current]
    assert conv["messages"][0]["content"] == "Do I need an Anmeldung?"
    assert conv["messages"][0]["voice"] == {"seconds": 3.0, "model": "stt-model", "cost_usd": 0.0002}
    assert conv["messages"][1]["content"] == "Answer to: Do I need an Anmeldung? [S1]"
    assert "pending_audio" not in at.session_state  # the recording is not kept
    assert any("Voice question" in c.value for c in at.caption)


def test_too_long_recording_is_refused_before_any_paid_call(monkeypatch):
    from expat import speech

    def must_not_run(audio):
        raise AssertionError("transcribe must not be called")

    _live_with_fake_pipeline(monkeypatch)
    monkeypatch.setattr(speech, "transcribe", must_not_run)
    at = _home()
    at.session_state.pending_audio = _clip(60)
    at.run()
    assert not at.exception, at.exception
    assert any("60 seconds long" in w.value for w in at.warning)
    assert not at.session_state.conversations[at.session_state.current]["messages"]


def test_failed_or_empty_transcription_asks_to_try_again(monkeypatch):
    from expat import speech

    _live_with_fake_pipeline(monkeypatch)
    monkeypatch.setattr(speech, "transcribe", lambda audio: speech.Transcript("...", 2.0, None, "stt-model"))
    at = _home()
    at.session_state.pending_audio = _clip(2)
    at.run()
    assert not at.exception, at.exception
    assert any("couldn't hear a question" in w.value for w in at.warning)
    assert not at.session_state.conversations[at.session_state.current]["messages"]


def test_typed_questions_still_work_when_the_microphone_is_on(monkeypatch):
    _live_with_fake_pipeline(monkeypatch)
    at = _home()
    at.chat_input[0].set_value("How do I register?").run()
    assert not at.exception, at.exception
    conv = at.session_state.conversations[at.session_state.current]
    assert conv["messages"][0] == {"role": "user", "content": "How do I register?"}


def test_listen_reads_the_answer_without_citation_markers_and_caches_the_clip(monkeypatch):
    from expat import speech

    spoken: list[str] = []

    def fake_synthesize(text):
        spoken.append(text)
        return speech.Speech(_clip(1), "audio/wav", len(text), "tts-model")

    _live_with_fake_pipeline(monkeypatch)
    monkeypatch.setattr(speech, "synthesize", fake_synthesize)
    at = _home()
    at.chat_input[0].set_value("How do I register?").run()
    next(b for b in at.button if b.key and b.key.startswith("listen-")).click().run()
    assert not at.exception, at.exception

    assert spoken == ["Answer to: How do I register?"]  # "[S1]" is not read aloud
    assert at.session_state.tts_clip["mime"] == "audio/wav"
    assert not [b for b in at.button if b.key and b.key.startswith("listen-")]  # the player replaced the button
    at.run()
    assert len(spoken) == 1  # a rerun shows the cached clip, no second paid call


def test_no_microphone_or_listen_button_in_demo_mode():
    at = _home()
    at.chat_input[0].set_value("simulate error").run()  # any question; Demo mode is forced by the fixture
    assert not at.exception, at.exception
    assert not [b for b in at.button if b.key and b.key.startswith("listen-")]
    assert not at.chat_input[0].proto.accept_audio
