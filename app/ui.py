"""Shared UI components (think: a small React component library, but as plain functions).

Streamlit mental model for React developers
-------------------------------------------
- There is no virtual DOM you manage and no components with their own state. The WHOLE page script
  re-runs top to bottom on every interaction (button click, form submit, chat message).
- Each `st.*` call appends an element to the page during that run; Streamlit diffs the result against
  the previous run and patches the browser. So a "component" here is just a function that calls `st.*`.
- State that must survive a rerun lives in `st.session_state` (a per-browser-tab dict, like a store).
- Widgets return their current value directly (`if st.button(...)` is True only in the run triggered
  by that click). Use `on_click=` callbacks when you need to change state BEFORE the next run draws.

Everything here renders the typed pipeline events from `expat.schemas.events`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import streamlit as st

from expat.config import get_settings
from expat.guards import estimate_cost_usd
from expat.schemas import (
    AnswerMetaEvent,
    Citation,
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    StepEvent,
    ToolCallEvent,
    ToolResultEvent,
)

DISCLAIMER = "General information, not legal or tax advice. Official German texts are binding."

STEP_LABELS: dict[str, tuple[str, str]] = {
    # name: (icon, label)
    "query_analysis": (":material/manage_search:", "Understanding your question"),
    "retrieval": (":material/travel_explore:", "Searching official sources"),
    "rerank": (":material/sort:", "Re-ranking the best passages"),
    "tool_call": (":material/calculate:", "Calculating with a tool"),
    "generation": (":material/edit_note:", "Writing the answer"),
    "safety": (":material/shield:", "Safety check"),
}

TOOL_LABELS = {
    "calculate_tenancy_notice": "Tenancy notice calculator",
    "calculate_deadline": "Deadline calculator",
    "estimate_family_benefits": "Family benefits estimator",
    "document_checklist": "Document checklist",
    "check_schengen_days": "Schengen 90/180 checker",
}

_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500&display=swap");
/* ---- Page frame: a narrow reading column, no Streamlit chrome ---------------------------------- */
[data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"] { max-width: 760px; }
[data-testid="stMainBlockContainer"] { padding-top: 2.5rem; padding-bottom: 2rem; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display: none; }

/* ---- Chat messages: no avatars; user = right-aligned bubble, assistant = plain text ------------- */
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] > img { display: none; }
[data-testid="stChatMessage"] { background: transparent; padding: 0.35rem 0; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { justify-content: flex-end; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    flex: 0 1 auto; max-width: 85%;
    background: #EDEAE2; border-radius: 1.25rem; padding: 0.55rem 1.05rem;
}
[data-testid="stChatMessageContent"] p { line-height: 1.65; }

/* ---- The composer: a soft floating card -------------------------------------------------------- */
[data-testid="stChatInput"], [data-testid="stChatInput"] > div, [data-testid="stChatInputTextArea"] {
    background: #FFFFFF !important;
}
[data-testid="stChatInput"] {
    border-radius: 1.4rem;
    box-shadow: 0 1px 2px rgba(38, 37, 31, .04), 0 6px 24px rgba(38, 37, 31, .07);
}
[data-testid="stBottom"] > div { background: #FAF9F6; }

/* ---- Empty state --------------------------------------------------------------------------------- */
.st-key-hero { margin-top: 14vh; }
.st-key-hero h1, .st-key-hero h1 span {
    font-family: "Source Serif 4", Georgia, serif !important; font-weight: 400 !important;
    font-size: 2.4rem; letter-spacing: -0.01em; padding-bottom: 0.2rem;
}
.st-key-hero [data-testid="stCaptionContainer"] p { text-align: center; font-size: 0.95rem; }
.st-key-suggestions { justify-content: center; }
[class*="st-key-example-"] button {
    background: #FFFFFF; border: 1px solid #E4E1D8; color: #4A483F;
    padding: 0.3rem 0.95rem; min-height: 2.1rem; font-size: 0.88rem;
}
[class*="st-key-example-"] button:hover { border-color: #1F6F64; color: #1F6F64; }
.st-key-fineprint p { text-align: center; font-size: 0.78rem; color: #8A877C; }

/* ---- Sidebar ------------------------------------------------------------------------------------- */
.st-key-brand p { font-family: "Source Serif 4", Georgia, serif !important; font-size: 1.25rem; margin: 0; }
.st-key-brand [data-testid="stCaptionContainer"] p {
    font-family: Inter, sans-serif !important; font-size: 0.8rem; color: #8A877C;
}
.st-key-recents button, .st-key-new-chat button { justify-content: flex-start !important; text-align: left; }
.st-key-recents button > div, .st-key-new-chat button > div { justify-content: flex-start !important; }
.st-key-recents [data-testid="stBaseButton-secondary"] { background: #E6E3DA; border-color: transparent; }
[data-testid="stPopoverBody"] { width: 330px !important; max-width: 330px !important; }
.st-key-recents button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.st-key-recents button { min-height: 2rem; padding: 0.2rem 0.75rem; }
.st-key-sidebar-bottom { position: fixed; bottom: 1rem; width: calc(var(--sidebar-width, 18rem) - 2.5rem); }

/* ---- Under an answer: small source pills, quiet details ----------------------------------------- */
[class*="st-key-chips-"] button {
    background: #F2F0EA; border: none; color: #4A483F;
    padding: 0.05rem 0.7rem; min-height: 1.75rem; font-size: 0.8rem;
}
[class*="st-key-chips-"] button:hover { background: #E3EFEC; color: #1F6F64; }
[data-testid="stChatMessageContent"] [data-testid="stExpander"] details {
    border: none; background: transparent;
}
[data-testid="stChatMessageContent"] [data-testid="stExpander"] summary {
    font-size: 0.82rem; color: #8A877C; padding-left: 0;
}
</style>
"""


def inject_css() -> None:
    """Visual polish. Streamlit exposes `.st-key-<key>` classes on keyed elements and stable `data-testid`
    attributes on its own elements; the CSS above targets only those, so it survives Streamlit updates."""
    st.html(_CSS)


def disclaimer_footer() -> None:
    with st.container(key="fineprint"):
        st.caption(f"Answers cite official German sources. {DISCLAIMER}")


# ------------------------------------------------------------------------------------------------
# Formatting helpers (pure functions: unit-testable, no Streamlit calls)
# ------------------------------------------------------------------------------------------------


def format_date(iso: str) -> str:
    """'2026-11-18' -> '18 Nov 2026' (falls back to the raw string)."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{d.day} {d.strftime('%b %Y')}"


def citation_label(c: Citation) -> str:
    """Full label, used as the hover text: '[S1] § 573c BGB · Gesetze im Internet · verified 18 Nov 2026'."""
    parts = [f"[{c.id}]", c.legal_reference or c.title]
    if c.source_name:
        parts.append(c.source_name)
    if c.last_verified:
        parts.append(f"verified {format_date(c.last_verified)}")
    return " · ".join([parts[0] + " " + parts[1], *parts[2:]])


def chip_label(c: Citation, max_len: int = 34) -> str:
    """Short pill text: 'S1 · § 573c BGB' or 'S3 · Wohnsitzanmeldung'. Details live in the dialog."""
    name = TOOL_LABELS.get(c.title, c.title) if c.kind == "tool" else (c.legal_reference or c.title or c.source_name)
    if len(name) > max_len:
        name = name[: max_len - 1].rstrip() + "…"
    return f"{c.id} · {name}"


_MARKER_RE = re.compile(r"\[(S|T)(\d+)\]")


def decorate_markers(text: str) -> str:
    """Turn plain `[S1]` / `[T1]` markers into Streamlit markdown badges (blue = source, orange = tool).

    The markdown stays portable (the pipeline emits plain `[S1]`); this is a render-time concern only.
    """
    return _MARKER_RE.sub(lambda m: f":{'blue' if m[1] == 'S' else 'orange'}-badge[{m[1]}{m[2]}]", text)


# ------------------------------------------------------------------------------------------------
# Step timeline ("How I got this answer")
# ------------------------------------------------------------------------------------------------


def hit_row(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    """Flatten a RankedHit dump (nested `metadata`) or an already-flat hit dict into one table row."""
    meta = hit.get("metadata", hit)
    return {
        "rank": rank,
        "score": hit.get("fused_score", hit.get("score")),
        "source": meta.get("source_name", ""),
        "§ / title": meta.get("legal_reference") or meta.get("title", ""),
        "doc_key": meta.get("doc_key", ""),
        "section": meta.get("section_kind", ""),
        "lang": meta.get("language", ""),
    }


def render_step(event: StepEvent) -> None:
    """Render one COMPLETED/FAILED step inside the current container (the st.status box)."""
    icon, label = STEP_LABELS.get(event.name, (":material/circle:", event.name))
    if event.status == "failed":
        st.markdown(f"{icon} **{label}** · :red[failed]")
        if event.detail:
            st.json(event.detail, expanded=False)
        return

    st.markdown(f"{icon} **{label}**")
    d = event.detail
    if event.name == "query_analysis" and d:
        _render_query_analysis(d)
    elif event.name == "retrieval" and d:
        _render_retrieval(d)
    elif event.name == "tool_call" and d.get("name"):
        st.caption(f"Used `{d['name']}`, see the tool card below.")
    elif d:
        st.json(d, expanded=False)


def _render_query_analysis(d: dict[str, Any]) -> None:
    if d.get("standalone_question"):
        st.caption(f"Standalone question: *{d['standalone_question']}*")
    subs = d.get("sub_queries", [])
    for i, sq in enumerate(subs, start=1):
        domain = f" · `{sq['domain']}`" if sq.get("domain") else ""
        st.markdown(f"**{i}. {sq.get('text', '')}**{domain}" if len(subs) > 1 else f"**{sq.get('text', '')}**{domain}")
        cols = st.columns(2)
        with cols[0]:
            st.caption("English rewrites")
            for q in sq.get("queries_en") or ["—"]:
                st.markdown(f"- {q}")
        with cols[1]:
            st.caption("German rewrites 🇩🇪")
            for q in sq.get("queries_de") or ["—"]:
                st.markdown(f"- {q}")
        if sq.get("step_back"):
            st.caption(f"Step-back question: *{sq['step_back']}*")
        if sq.get("legal_references"):
            st.caption("Legal references: " + ", ".join(f"`{r}`" for r in sq["legal_references"]))


def _render_retrieval(d: dict[str, Any], top_n: int = 5) -> None:
    for sub in d.get("sub_results", []):
        st.caption(f"Top hits for: *{sub.get('sub_question', '')}*")
        rows = [hit_row(h, i) for i, h in enumerate(sub.get("hits", [])[:top_n], start=1)]
        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                column_config={"score": st.column_config.NumberColumn(format="%.4f")},
            )
        else:
            st.caption("No hits.")


def _tool_state(result: ToolResultEvent | None) -> str:
    if result is None:
        return ":material/hourglass_top: running…"
    if result.error:
        return ":red[:material/error: failed]"
    return ":green[:material/check_circle: done]"


def render_tool_line(call: ToolCallEvent, result: ToolResultEvent | None) -> None:
    """One quiet line while the answer streams: 'Family benefits estimator · done'."""
    st.caption(f":material/calculate: {TOOL_LABELS.get(call.name, call.name)} · {_tool_state(result)}")


def render_tool_card(call: ToolCallEvent, result: ToolResultEvent | None) -> None:
    """A tool card: args -> result. Rendered inside the "How I got this answer" fold (no nested expander)."""
    title = TOOL_LABELS.get(call.name, call.name)
    with st.container(border=True):
        st.markdown(f":material/calculate: **{title}** · {_tool_state(result)}")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Input")
            st.json(call.args)
        with c2:
            st.caption("Result")
            if result is None:
                st.caption("Waiting for the tool…")
            elif result.error:
                st.error(result.error)
            else:
                st.json(result.result)


# ------------------------------------------------------------------------------------------------
# Citations, meta, done, error
# ------------------------------------------------------------------------------------------------


@st.dialog("Source details", width="large")
def citation_dialog(c: Citation) -> None:
    """A modal. Streamlit runs this function as an isolated fragment while the dialog is open."""
    badge = "orange" if c.kind == "tool" else "blue"
    st.markdown(f":{badge}-badge[{c.id}] **{c.legal_reference or c.title}**")
    if c.legal_reference and c.title:
        st.caption(c.title)
    meta_cols = st.columns(3)
    meta_cols[0].metric("Source", c.source_name or "—")
    meta_cols[1].metric("Verified", format_date(c.last_verified) if c.last_verified else "—")
    meta_cols[2].metric("Type", "Tool result" if c.kind == "tool" else "Official source")
    if c.heading_path:
        st.caption(f":material/account_tree: {c.heading_path}")
    if c.quote:
        st.markdown("> " + c.quote.replace("\n", "\n> "))
    if c.source_url:
        st.link_button("Open the official source", c.source_url, icon=":material/open_in_new:")
    if c.kind == "source":
        st.caption("The official German text is binding. Translations and summaries are for orientation only.")


def render_citations(citations: list[Citation], key_prefix: str) -> None:
    if not citations:
        return
    # A horizontal flex container: the pills wrap like inline tags. Click = source details dialog.
    with st.container(horizontal=True, gap="small", key=f"chips-{key_prefix}"):
        for c in citations:
            icon = ":material/calculate:" if c.kind == "tool" else ":material/description:"
            if st.button(chip_label(c), key=f"{key_prefix}-{c.id}", icon=icon, help=citation_label(c)):
                citation_dialog(c)


def render_answer_meta(meta: AnswerMetaEvent) -> None:
    if meta.confidence == "insufficient":
        st.warning(
            "I couldn't find enough in my official sources to answer this reliably. "
            "Please check with the responsible authority.",
            icon=":material/search_off:",
        )
    elif meta.confidence == "partial":
        st.info("Parts of this answer are not covered by my sources.", icon=":material/info:")
    if meta.stale_sources:
        st.warning(
            f"Some sources were last verified a while ago ({', '.join(meta.stale_sources)}). "
            "Rules may have changed; check the official page.",
            icon=":material/history:",
        )
    if meta.unverified_refs:
        st.caption(
            ":orange[:material/report: Mentions not found in the cited sources: "
            + ", ".join(meta.unverified_refs)
            + "]"
        )


def render_done(done: DoneEvent, mode: str) -> None:
    secs = done.latency_ms / 1000
    tokens = f"{done.input_tokens:,} → {done.output_tokens:,} tokens"
    bits = [f":material/timer: {secs:.1f} s", tokens, mode]
    if mode == "Live" and (done.input_tokens or done.output_tokens):
        s = get_settings()
        cost = estimate_cost_usd(done.input_tokens, done.output_tokens, s.price_in_per_mtok, s.price_out_per_mtok)
        bits.insert(2, f"≈ ${cost:.4f}")  # analysis + answer model; embeddings are a fraction of a cent
    if done.run_id:
        bits.append(f"run `{done.run_id}`")
    st.caption(" · ".join(bits))


def render_error(err: ErrorEvent) -> None:
    st.error(f"**Something went wrong** ({err.code}): {err.message}", icon=":material/error:")


# ------------------------------------------------------------------------------------------------
# Replaying a stored assistant message (used for the chat history)
# ------------------------------------------------------------------------------------------------


def split_events(events: list[PipelineEvent]) -> dict[str, Any]:
    """Group a finished event list by type, so a stored message can be re-rendered in one go."""
    out: dict[str, Any] = {"steps": [], "calls": [], "results": {}, "citations": [], "meta": None, "done": None}
    for ev in events:
        if isinstance(ev, StepEvent) and ev.status != "started":
            out["steps"].append(ev)
        elif isinstance(ev, ToolCallEvent):
            out["calls"].append(ev)
        elif isinstance(ev, ToolResultEvent):
            out["results"][ev.call_id] = ev
        elif isinstance(ev, CitationsEvent):
            out["citations"] = ev.citations
        elif isinstance(ev, AnswerMetaEvent):
            out["meta"] = ev
        elif isinstance(ev, DoneEvent):
            out["done"] = ev
        elif isinstance(ev, ErrorEvent):
            out["error"] = ev
    return out


def timeline_label(n_steps: int, done: DoneEvent | None) -> str:
    label = f"How I got this answer · {n_steps} steps"
    if done:
        label += f" · {done.latency_ms / 1000:.1f} s"
    return label


def render_assistant_message(events: list[PipelineEvent], content: str, key_prefix: str, mode: str) -> None:
    """Render a stored assistant turn. The answer is the hero; everything technical is folded away.

    Order: answer -> warnings -> source pills -> one quiet "How I got this answer" fold that holds the
    step timeline, tool inputs/outputs and the latency/token numbers (for curious users and reviewers).
    """
    parts = split_events(events)
    if content:
        st.markdown(decorate_markers(content))
    if parts.get("error"):
        render_error(parts["error"])
    if parts["meta"]:
        render_answer_meta(parts["meta"])
    render_citations(parts["citations"], key_prefix)
    if parts["steps"] or parts["calls"]:
        with st.expander(timeline_label(len(parts["steps"]), parts["done"]), icon=":material/manage_search:"):
            for step in parts["steps"]:
                render_step(step)
            for call in parts["calls"]:
                render_tool_card(call, parts["results"].get(call.call_id))
            if parts["done"]:
                render_done(parts["done"], mode)


def pretty_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
