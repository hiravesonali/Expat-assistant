"""Voice in and out: speech-to-text for spoken questions, text-to-speech for "Listen" (ADR-0011).

The design is a cascade: audio -> text -> the unchanged RAG pipeline -> text -> audio. The pipeline never sees
audio, so citations, guards, tools and evals work exactly as for typed questions.

Both calls go to OpenRouter's audio endpoints with plain `httpx` (like `OpenRouterEmbeddings` in `llm.py`), so
they are unit-tested offline with `httpx.MockTransport`. No Streamlit imports and no tracing here: audio and
transcripts of it are never sent to LangSmith; callers log duration, model and cost only.

    POST /audio/transcriptions  JSON {"model", "input_audio": {"data": <base64>, "format": "wav"}, "prompt"}
                                -> JSON {"text", "usage": {"seconds", "cost"}}
    POST /audio/speech          JSON {"model", "input", "voice", "response_format": "pcm" | "mp3"}
                                -> raw audio bytes (audio/pcm or audio/mpeg)
"""

from __future__ import annotations

import base64
import io
import re
import wave
from dataclasses import dataclass
from typing import Any

import httpx

from expat.config import Settings, get_settings
from expat.llm import APP_TITLE, _require_key

# Context for the transcriber, not an instruction: German administrative words that English speakers use
# mid-sentence ("do I need an Anmeldung?") and that a speech model otherwise writes as English lookalikes.
STT_VOCABULARY = (
    "Expected vocabulary: Anmeldung, Bürgeramt, Ausländerbehörde, Aufenthaltstitel, Blue Card, Blaue Karte, "
    "Niederlassungserlaubnis, Kindergeld, Elterngeld, Kita, Mietvertrag, Kündigung, Mietpreisbremse, "
    "Mietspiegel, Wohnungsgeberbestätigung, Rundfunkbeitrag, Steuerklasse, Krankenkasse."
)

MIN_CLIP_SECONDS = 0.4  # shorter clips are accidental taps on the microphone
# Models that only return raw PCM (a 400 for mp3). Everything else is asked for mp3, which is ~6x smaller.
_PCM_ONLY_MODELS = ("gemini", "heygen")


class SpeechError(RuntimeError):
    """A speech call failed. The message carries the provider text, so budget errors stay recognisable."""


@dataclass(frozen=True)
class ClipCheck:
    seconds: float
    reason: str | None  # None = usable; otherwise "invalid" | "too_short" | "too_long" (the UI translates)


@dataclass(frozen=True)
class Transcript:
    text: str
    seconds: float | None
    cost_usd: float | None
    model: str


@dataclass(frozen=True)
class Speech:
    audio: bytes
    mime: str  # "audio/wav" or "audio/mpeg", ready for st.audio
    chars: int
    model: str


# ------------------------------------------------------------------------------------------- audio


def wav_duration(data: bytes) -> float:
    """Length of a WAV clip in seconds, read from its header (no decoding). Raises ValueError if not WAV."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / rate if rate else 0.0
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a WAV recording: {exc}") from exc


def check_clip(data: bytes, max_seconds: float) -> ClipCheck:
    """Validate a recording BEFORE it is sent anywhere: transcription is paid per second of audio."""
    try:
        seconds = wav_duration(data)
    except ValueError:
        return ClipCheck(0.0, "invalid")
    if seconds < MIN_CLIP_SECONDS:
        return ClipCheck(seconds, "too_short")
    if seconds > max_seconds:
        return ClipCheck(seconds, "too_long")
    return ClipCheck(seconds, None)


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV header so a browser can play it."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buffer.getvalue()


# -------------------------------------------------------------------------------------------- text

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_MARKERS = re.compile(r"\s*\[(?:[ST]\d+)(?:\s*,\s*[ST]\d+)*\]")  # citation markers: [S1], [T2], [S1, S3]
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_LINE_PREFIX = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+)", re.MULTILINE)  # headings, quotes, bullets
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|`)(.+?)\1")
_SENTENCE_END = re.compile(r"[.!?:](?=\s|$)")


def speakable_text(markdown: str, max_chars: int) -> str:
    """Turn an answer into text worth reading aloud: no citation markers, links, tables or markdown syntax.

    Text-to-speech is priced per character and is the most expensive call in a turn, so the result is cut at
    the last sentence end within `max_chars`. Numbered list markers ("1.") are kept: they read naturally.
    """
    text = _CODE_BLOCK.sub(" ", markdown)
    text = _TABLE_ROW.sub("", text)
    text = _MARKERS.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _LINE_PREFIX.sub("", text)
    text = _EMPHASIS.sub(r"\2", _EMPHASIS.sub(r"\2", text))  # twice: bold around italics
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    ends = [m.end() for m in _SENTENCE_END.finditer(cut)]
    return cut[: ends[-1]] if ends and ends[-1] > max_chars // 2 else cut.rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------------------------- API


def _post(client: httpx.Client | None, settings: Settings, path: str, body: dict[str, Any]) -> httpx.Response:
    key = _require_key(settings).get_secret_value()
    url = settings.openrouter_base_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {key}", "X-Title": APP_TITLE}
    owned = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        response = http.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise SpeechError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        if owned:
            http.close()
    if response.status_code != 200:
        raise SpeechError(f"{response.status_code}: {response.text[:500]}")
    return response


def transcribe(audio: bytes, settings: Settings | None = None, client: httpx.Client | None = None) -> Transcript:
    """Speech-to-text for one WAV clip with MODEL_STT.

    No `language` is sent: the model detects it, so someone on the English interface can ask in German (the
    pipeline detects the question language itself). The vocabulary prompt is forwarded by OpenAI-hosted
    models and ignored by providers that don't support it.
    """
    s = settings or get_settings()
    body = {
        "model": s.model_stt,
        "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": "wav"},
        "prompt": STT_VOCABULARY,
        "temperature": 0,
    }
    data = _post(client, s, "/audio/transcriptions", body).json()
    usage = data.get("usage") or {}
    return Transcript(
        text=(data.get("text") or "").strip(),
        seconds=usage.get("seconds"),
        cost_usd=usage.get("cost"),
        model=s.model_stt,
    )


def tts_format_for(model: str) -> str:
    return "pcm" if any(name in model.lower() for name in _PCM_ONLY_MODELS) else "mp3"


def synthesize(text: str, settings: Settings | None = None, client: httpx.Client | None = None) -> Speech:
    """Text-to-speech with MODEL_TTS / TTS_VOICE. `text` should come from `speakable_text` (already capped)."""
    s = settings or get_settings()
    if not text.strip():
        raise SpeechError("nothing to read aloud")
    fmt = tts_format_for(s.model_tts)
    body = {"model": s.model_tts, "input": text, "voice": s.tts_voice, "response_format": fmt}
    content = _post(client, s, "/audio/speech", body).content
    if not content:
        raise SpeechError("the speech model returned no audio")
    if fmt == "pcm":
        return Speech(pcm_to_wav(content, s.tts_pcm_sample_rate), "audio/wav", len(text), s.model_tts)
    return Speech(content, "audio/mpeg", len(text), s.model_tts)
