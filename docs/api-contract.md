# API Contract: FastAPI ↔ Next.js

> **Update 2026-11-17 (ADR-0009):** The MVP is Streamlit-primary, so this HTTP contract is now a **stretch goal**. The event types below live on as the in-process pipeline protocol in `src/expat/schemas/events.py`, which the Streamlit UI renders. Adding FastAPI later means serialising those same events as SSE.

> Status: planning draft (2026-11-17). Described, not implemented.

## Decision: SSE over WebSockets

| Option | Pros | Cons |
|---|---|---|
| **SSE (HTTP streaming, `text/event-stream`)** ✅ | One-way server→client is exactly what chat needs. Plain HTTP, so it works through proxies and Vercel. Easy to debug with `curl -N`. FastAPI has `StreamingResponse` / `sse-starlette`. | Client→server goes over separate requests (fine: one POST per message). The browser `EventSource` only does GET, so we read the stream with `fetch()` + `ReadableStream` instead. |
| WebSockets | Bidirectional. Good for presence and collaborative editing. | Connection state, reconnect logic, harder to load-balance and trace. Overkill for request/response chat. |
| Vercel AI SDK data-stream protocol on top of SSE | `useChat()` works out of the box. | Couples the backend to a frontend library's protocol version. Hides the design we want to show in the review. Possible stretch: an adapter route in Next.js. |

**Recommendation:** use SSE with our own small, typed event protocol. The Pydantic event models are the single source of truth, and TS types are generated from their JSON Schema (`pydantic` → `json-schema-to-typescript`), so frontend and backend can't drift.

## Statelessness and privacy

The backend is **stateless**: it stores no conversations and no profiles.
- The **conversation history** (sidebar) lives in the browser (IndexedDB via `idb-keyval`, or `localStorage` for the MVP).
- The **profile** is coarse enums only (no name, address or passport number). It is stored in `localStorage` and sent with every request.
- The client sends the last *N* turns (default 6) as `history`. The backend trims them to a token budget.
- LangSmith traces would contain user messages, so tracing uses metadata only for the profile, and the deployed demo can hide inputs (see `docs/PLAN.md` § Safety).

This removes the need for a database, auth and GDPR deletion endpoints in the MVP, which is a defensible scope cut.

## Endpoints

| Method | Path | Purpose | MVP |
|---|---|---|---|
| `POST` | `/api/chat` | Send a message, receive an SSE stream | ✅ |
| `GET` | `/api/health` | Liveness + Chroma collection count + model config | ✅ |
| `GET` | `/api/sources/{chunk_id}` | Full parent text + metadata for the citation panel | ✅ |
| `GET` | `/api/profile/schema` | JSON Schema of `UserProfile` (drives the onboarding form) | ✅ (nice: the form is generated) |
| `POST` | `/api/feedback` | 👍/👎 on an answer → LangSmith feedback on the `run_id` | stretch |
| `POST` | `/api/debug/retrieve` | Retrieval only, no generation (used by the Streamlit debugger if it runs against HTTP) | stretch (Streamlit imports Python directly) |

### `POST /api/chat`

Request (`application/json`):
```jsonc
{
  "conversation_id": "c_01HF…",          // client-generated (ULID); used as LangSmith thread id
  "message": "My landlord wants to raise my rent by 20%. Is that allowed?",
  "history": [                            // last N turns, client-trimmed
    {"role": "user", "content": "…"},
    {"role": "assistant", "content": "…"}
  ],
  "profile": {                            // optional; all fields optional enums
    "city": "munich",
    "citizenship": "non_eu",              // eu | non_eu | german
    "residence_status": "blue_card",      // blue_card | work_permit | student | family_reunion | settlement | eu_freedom | other | unknown
    "employment": "employee",             // employee | freelancer | self_employed | student | unemployed | unknown
    "family_status": "married",           // single | married | partnership | unknown
    "children_count": 2,                  // 0..10
    "youngest_child_age": 3,              // optional, years
    "housing": "renting",                 // renting | owning | looking | unknown
    "answer_language": "en"               // en | de
  },
  "options": {"debug": false}             // debug=true also streams retrieval chunk text
}
```

Response: `200 text/event-stream`. Each event is `event: <type>\ndata: <json>\n\n`.

### Event types (in typical order)

| `event` | `data` payload | UI use |
|---|---|---|
| `run_started` | `{run_id, conversation_id, model}` | Store the `run_id` for feedback and the LangSmith link |
| `step` | `{id, name, status: "started"\|"completed", detail}` | "How I got this answer" timeline. `name` ∈ `query_analysis`, `retrieval`, `rerank`, `tool_call`, `generation` |
| `query_analysis` | `{domains[], rewritten_queries: {en[], de[]}, sub_questions[], filters, intent}` | Expandable step detail |
| `retrieval` | `{sub_question, hits: [{chunk_id, title, heading_path, source_name, score, rank}]}` | Expandable step detail (one event per sub-question) |
| `tool_call` | `{call_id, name, args}` | Tool chip ("Calculating notice period…") |
| `tool_result` | `{call_id, name, result, error?}` | Expandable tool output |
| `token` | `{text}` | Append to the markdown buffer |
| `citations` | `{citations: [{id: "S1", chunk_id, title, source_name, source_url, heading_path, legal_reference?, last_verified, quote?}]}` | Citation chips: `[S1]` markers in the text map to these |
| `answer_meta` | `{confidence: "grounded"\|"partial"\|"insufficient", disclaimer_level, stale_sources[]}` | Banner when sources are old or the answer is a fallback |
| `done` | `{run_id, usage: {input_tokens, output_tokens, cost_usd?}, latency_ms}` | Close the stream; show the cost in the debug view |
| `error` | `{code, message, retryable}` | Toast + retry button |

Notes
- Citation markers in the answer text are plain `[S1]`, `[S2]` tokens. The frontend renders them as chips via a remark plugin, so the markdown stays portable.
- `citations` is sent **after** the tokens because the final set is known only once generation finishes. The panel can show "pending" chips for markers until then.
- Heartbeat: a `: ping` comment every 15 s to keep proxies from closing the connection.
- Cancellation: the client aborts `fetch` via `AbortController`. FastAPI detects `request.is_disconnected()` and cancels the LangChain task.

### `GET /api/sources/{chunk_id}`
```jsonc
{
  "chunk_id": "…", "parent_id": "…",
  "title": "Kündigungsfristen", "heading_path": "BGB › Buch 2 › … › § 573c",
  "source_name": "Gesetze im Internet", "source_url": "https://www.gesetze-im-internet.de/bgb/__573c.html",
  "source_type": "law", "language": "de", "legal_reference": "§ 573c BGB",
  "last_verified": "2026-11-18", "valid_from": null,
  "parent_text": "…full § text…", "chunk_text": "…the matched Absatz…"
}
```

## Error handling
- `422` for request validation errors (FastAPI default) before the stream starts.
- Errors during the stream arrive as an `error` event, followed by stream close (HTTP 200 has already been sent).
- LLM provider errors (OpenRouter 429/5xx) are retried 2× with backoff inside the backend. After that the backend emits `error {retryable: true}`.

## CORS and config
- Dev: Next.js on `:3000`, FastAPI on `:8000`, with CORS allow-list `http://localhost:3000`.
- Alternative: Next.js route handler `/api/chat` proxies to FastAPI (same origin, hides the backend URL). This is the recommended setup for deployment.
