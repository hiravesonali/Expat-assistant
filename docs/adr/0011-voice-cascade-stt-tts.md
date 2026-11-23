# ADR-0011: Voice as a cascade (speech-to-text → text pipeline → text-to-speech) via OpenRouter

- **Status:** Proposed (2026-11-23). Code and offline tests are in place. Both API calls were smoke-tested live
  on two synthetic sentences (see "Result"), and the microphone and Listen button were tried by hand in the
  browser on 2026-11-23 and worked. There is no measured comparison on real recordings yet.
- **Context:** Newcomers often find it easier to ask a question aloud than to type it, and to listen to an answer
  than to read it. The app is a text RAG pipeline (ADR-0008) in Streamlit (ADR-0009), paid from one OpenRouter key
  with a small budget (ADR-0006).

## Options
| Option | Pros | Cons |
|---|---|---|
| **a. Cascade: STT → existing pipeline → TTS (chosen)** | Pipeline, citations, guards, tools and evals unchanged; each stage testable and swappable; cheap | Not a "live conversation"; two extra calls |
| b. Speech-to-speech / realtime model | Natural conversation, low latency | Bypasses retrieval, citations and the citation validator; needs streaming audio that Streamlit doesn't offer; much more expensive |
| c. Audio as input to the chat model | One call | Ties the answer model to audio-capable models; retrieval still needs text first |
| d. Browser speech APIs (Web Speech) | Free | Quality depends on the device and browser; needs a custom component; German terms unreliable |

## Decision
- **Voice in:** `st.chat_input(accept_audio=True)` records a 16 kHz WAV. `expat/speech.py` sends it to
  `POST /audio/transcriptions` with `MODEL_STT` (default `openai/whisper-large-v3-turbo`) and a short vocabulary
  prompt (Anmeldung, Ausländerbehörde, …). No language is forced, so German speech on the English interface works.
  The transcript is validated and sent like a typed question, and shown as the user's message with a microphone
  marker, so a mishearing is visible.
- **Voice out:** a **Listen** button per answer calls `POST /audio/speech` with `MODEL_TTS`
  (default `google/gemini-3.8-flash-lite-tts`, voice `Kore`). It is on demand, never automatic.
- **Live mode only.** Demo mode has no microphone and no Listen button: both are paid calls.
- `Pipeline.run(question: str)` is unchanged. Voice lives in the app layer and in `expat/speech.py`.

## Why these models
- STT: needs English, German and mixed sentences ("do I need an Anmeldung?") and should accept a vocabulary prompt.
  The first choice was `openai/gpt-4o-mini-transcribe`, but the OpenRouter workspace guardrail for this key
  (Basic model list) blocks it. `openai/whisper-large-v3-turbo` is the transcription model on that list, is
  multilingual and is the cheapest option (~$0.012 per hour of audio).
- TTS: English answers contain German terms, so one multilingual voice is preferred over per-language voices.
  Gemini TTS returns raw PCM only; `speech.py` wraps it in a WAV header. Fallback: `mistralai/voxtral-mini-tts-3-0`
  (returns mp3, voices are per language).

## Result (live smoke test, 2026-11-23)
Two sentences were synthesised with Gemini TTS and transcribed back with Whisper turbo, through `speech.py`:

| Check | Outcome |
|---|---|
| TTS, English with German terms (74 characters) | 5.6 s of audio in 2.5 s; 13 characters/s at 24 kHz, a normal speaking rate |
| TTS, German (52 characters) | 3.2 s of audio in 2.2 s |
| STT, English with German terms | "Do I need an anmeldung at the Bürgeramt before I can apply for Kindergeld?" (only the capital A differs), 1.8 s, $0.00002 |
| STT, German | "Wie lange ist die Kündigungsfrist für meine Wohnung?" (exact), 1.4 s, $0.00001 |
| STT, 3 s of silence | empty text, which the app answers with "couldn't hear a question" |

Limits of this test: clean synthetic speech, not a person with an accent or background noise.

## Cost and limits (OpenRouter list prices, 2026-11-23)
| Step | Approx. cost |
|---|---|
| One Live answer (text) | $0.005 |
| Transcribing a 15 s question | about $0.00005 (measured: $0.0000033 per second) |
| Reading one answer aloud (≤ 1,200 characters) | $0.01–0.02 (the Gemini figure is an estimate from token prices) |

Reading aloud costs several times the answer itself, so it has its own limits (`LISTENS_PER_HOUR`,
`DAILY_LISTEN_CAP`), a character cap (`TTS_MAX_CHARS`), cleaned text (no citation markers, links, tables) and one
cached clip per session. Voice questions count against the normal question limits, and the clip length
(`VOICE_MAX_SECONDS`) is checked locally **before** any paid call.

## Privacy
A voice is personal data. The recording exists in server memory only for the request, is never written to
session state beyond one rerun, to disk or to LangSmith; only duration, model and cost are kept. This is stated
in the app next to the existing privacy note (ADR-0007).

## Consequences
- Two new model roles in the config; `VOICE_ENABLED=false` switches the feature off without a deploy.
- A wrong transcript produces a wrong question. Mitigation: the transcript is always shown; empty or
  punctuation-only transcripts are rejected without calling the pipeline.
- Not done: a speech-to-text comparison on recorded clips (word error rate, German terms, retrieval hit@5 on the
  transcript vs the typed question). Do this before setting the status to Accepted.
