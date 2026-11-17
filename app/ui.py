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
/* Compact citation chips: Streamlit buttons inside a container with the `citation-chips` key. */
.st-key-citation-chips button, [class*="st-key-chips-"] button {
    border-radius: 999px;
    padding: 0.1rem 0.75rem;
    min-height: 1.9rem;
    font-size: 0.82rem;
}
/* Sticky-ish footer caption for the disclaimer. */
.st-key-disclaimer-footer p { font-size: 0.8rem; color: #6b7785; text-align: center; }
/* Example prompt cards on the empty state. */
[class*="st-key-example-"] button {
    min-height: 5.2rem;
    text-align: left;
    justify-content: flex-start;
    align-items: flex-start;
    white-space: normal;
}
</style>
"""


def inject_css() -> None:
    """Small CSS touch-ups. Streamlit exposes `.st-key-<key>` classes on keyed elements, which we target."""
    st.html(_CSS)


def disclaimer_footer() -> None:
    with st.container(key="disclaimer-footer"):
        st.caption(f":material/gavel: {DISCLAIMER}")


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
    """'[S1] § 573c BGB · Gesetze im Internet · verified 18 Nov 2026'."""
    parts = [f"[{c.id}]", c.legal_reference or c.title]
    if c.source_name:
        parts.append(c.source_name)
    if c.last_verified:
        parts.append(f"verified {format_date(c.last_verified)}")
    return " · ".join([parts[0] + " " + parts[1], *parts[2:]])


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


def render_tool_card(call: ToolCallEvent, result: ToolResultEvent | None) -> None:
    """A tool card: args -> result. Collapsed by default so the answer stays the hero."""
    title = TOOL_LABELS.get(call.name, call.name)
    if result is None:
        state = ":material/hourglass_top: running…"
    elif result.error:
        state = ":red[:material/error: failed]"
    else:
        state = ":green[:material/check_circle: done]"
    with st.expander(f":material/calculate: **{title}** · {state}", expanded=False):
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
    st.caption("Sources")
    # A horizontal flex container: the chips wrap like inline tags.
    with st.container(horizontal=True, gap="small", key=f"chips-{key_prefix}"):
        for c in citations:
            icon = ":material/calculate:" if c.kind == "tool" else ":material/menu_book:"
            if st.button(citation_label(c), key=f"{key_prefix}-{c.id}", icon=icon, help=c.title):
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
    bits = [f":material/timer: {secs:.1f} s", f"{done.input_tokens:,} → {done.output_tokens:,} tokens", mode]
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
    """Render a stored assistant turn: timeline, tool cards, answer, citations, banners."""
    parts = split_events(events)
    if parts["steps"]:
        with st.status(timeline_label(len(parts["steps"]), parts["done"]), state="complete", expanded=False):
            for step in parts["steps"]:
                render_step(step)
    for call in parts["calls"]:
        render_tool_card(call, parts["results"].get(call.call_id))
    if content:
        st.markdown(decorate_markers(content))
    if parts.get("error"):
        render_error(parts["error"])
    render_citations(parts["citations"], key_prefix)
    if parts["meta"]:
        render_answer_meta(parts["meta"])
    if parts["done"]:
        render_done(parts["done"], mode)


def pretty_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
