"""Voice helpers (expat/speech.py): offline, the OpenRouter audio endpoints are faked with httpx.MockTransport."""

import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from expat import speech
from expat.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(openrouter_api_key=SecretStr("sk-test"), **overrides)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _wav(seconds: float, rate: int = 16000) -> bytes:
    return speech.pcm_to_wav(b"\x00\x00" * int(seconds * rate), rate)


# ------------------------------------------------------------------------------------------- clips


def test_wav_duration_roundtrip():
    assert speech.wav_duration(_wav(2.5)) == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("data", "reason"),
    [(_wav(3), None), (_wav(0.1), "too_short"), (_wav(50), "too_long"), (b"not audio", "invalid"), (b"", "invalid")],
)
def test_check_clip(data, reason):
    assert speech.check_clip(data, max_seconds=45).reason == reason


# -------------------------------------------------------------------------------------------- text


def test_speakable_text_strips_citations_links_and_markdown():
    answer = (
        "## Notice period\n"
        "You can give **three months'** notice [S1, T1]. See the [official page](https://example.org/x) "
        "or https://example.org/y.\n\n"
        "- Send it *in writing* [S2]\n"
        "1. Keep a copy\n\n"
        "| Rule | Value |\n|---|---|\n| Notice | 3 months |\n"
    )
    text = speech.speakable_text(answer, 1000)
    assert "three months' notice." in text
    assert "official page" in text
    assert "Send it in writing" in text
    assert "1. Keep a copy" in text
    for unwanted in ("[S1", "[S2]", "http", "**", "##", "|", "- Send"):
        assert unwanted not in text


def test_speakable_text_is_cut_at_a_sentence_end():
    text = speech.speakable_text("First sentence here. Second sentence here. Third sentence is cut off.", 50)
    assert text == "First sentence here. Second sentence here."


# ------------------------------------------------------------------------------------- transcribe


def test_transcribe_sends_base64_wav_and_reads_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"text": " Do I need an Anmeldung? ", "usage": {"seconds": 3.0, "cost": 0.0002}}
        )

    clip = _wav(3)
    result = speech.transcribe(clip, settings=_settings(model_stt="openai/whisper-large-v3"), client=_client(handler))

    assert result == speech.Transcript("Do I need an Anmeldung?", 3.0, 0.0002, "openai/whisper-large-v3")
    assert seen["url"] == "https://openrouter.ai/api/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "openai/whisper-large-v3"
    assert seen["body"]["input_audio"] == {"data": base64.b64encode(clip).decode(), "format": "wav"}
    assert "Anmeldung" in seen["body"]["prompt"]
    assert "language" not in seen["body"]  # auto-detect: German speech on the English interface must work


def test_transcribe_error_keeps_the_provider_message():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "Key limit exceeded (total limit)."}})

    with pytest.raises(speech.SpeechError, match="Key limit exceeded"):
        speech.transcribe(_wav(1), settings=_settings(), client=_client(handler))


def test_network_failure_becomes_a_speech_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(speech.SpeechError, match="ConnectError"):
        speech.transcribe(_wav(1), settings=_settings(), client=_client(handler))


# ------------------------------------------------------------------------------------- synthesize


def test_synthesize_wraps_pcm_in_a_wav_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"\x01\x00" * 24000, headers={"Content-Type": "audio/pcm"})

    result = speech.synthesize("Hallo.", settings=_settings(), client=_client(handler))

    assert seen["body"] == {
        "model": "google/gemini-3.8-flash-lite-tts",
        "input": "Hallo.",
        "voice": "Kore",
        "response_format": "pcm",
    }
    assert result.mime == "audio/wav"
    assert speech.wav_duration(result.audio) == pytest.approx(1.0)  # 24,000 samples at 24 kHz
    assert result.chars == 6


def test_synthesize_asks_other_models_for_mp3_and_passes_it_through():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"ID3-mp3-bytes", headers={"Content-Type": "audio/mpeg"})

    s = _settings(model_tts="mistralai/voxtral-mini-tts-3-0", tts_voice="en_paul_neutral")
    result = speech.synthesize("Hello.", settings=s, client=_client(handler))

    assert seen["body"]["response_format"] == "mp3"
    assert seen["body"]["voice"] == "en_paul_neutral"
    assert (result.audio, result.mime) == (b"ID3-mp3-bytes", "audio/mpeg")


def test_synthesize_rejects_empty_text_without_calling_the_api():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    with pytest.raises(speech.SpeechError):
        speech.synthesize("   ", settings=_settings(), client=_client(handler))
