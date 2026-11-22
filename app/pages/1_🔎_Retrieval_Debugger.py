"""Retrieval Debugger: query -> analysis plan -> per-sub-question fused hits, with every RetrievalConfig flag.

This is the same `retrieve()` code path the chat and the evals use (docs/PLAN.md), so what you see here
is exactly what the answer model would get as context.
"""

import time
from typing import Any

import _bootstrap  # noqa: F401  (must be first)
import streamlit as st
import ui
from _admin import require_admin
from pipeline_adapter import LIVE, get_retrieval_backend, live_status

from expat.schemas import RetrievalConfig, RetrievalResult, UserProfile

st.set_page_config(page_title="Retrieval Debugger · Ankommen", page_icon="🔎", layout="wide")
ui.inject_css()
require_admin()

st.title(":material/manage_search: Retrieval Debugger")
st.caption("Query analysis → hybrid retrieval (dense + BM25, RRF) → parent expansion. No answer generation.")

BOOL_FLAGS = [name for name, f in RetrievalConfig.model_fields.items() if f.annotation is bool]
INT_FIELDS = [name for name, f in RetrievalConfig.model_fields.items() if f.annotation is int]
FLAG_HELP = {
    "use_german_rewrite": "R1: add German rewrites of each sub-question (cross-lingual retrieval).",
    "use_multi_query": "R2: add English paraphrases (multi-query).",
    "use_decomposition": "R3: retrieve per sub-question instead of one merged question.",
    "use_bm25": "R4: add BM25 lists to the fusion (exact tokens like '§ 573c').",
    "use_filters": "R5: Chroma `where` filters from profile + question.",
    "use_rerank": "R6 (stretch): cross-encoder reranking.",
    "use_hyde": "R7 (stretch): hypothetical document embeddings.",
    "use_step_back": "Add the step-back question for specific legal questions.",
}


def _apply_preset(config: RetrievalConfig) -> None:
    """on_click callback: writes widget values into session_state BEFORE the widgets are drawn again."""
    for name in BOOL_FLAGS + INT_FIELDS:
        st.session_state[f"cfg_{name}"] = getattr(config, name)


# Seed widget state once (keyed widgets read their value from session_state).
if "cfg_use_bm25" not in st.session_state:
    _apply_preset(RetrievalConfig())

# --- Sidebar: config ------------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Retrieval config")
    c1, c2 = st.columns(2)
    c1.button("R0 baseline", on_click=_apply_preset, args=(RetrievalConfig.baseline(),), width="stretch")
    c2.button("Default", on_click=_apply_preset, args=(RetrievalConfig(),), width="stretch", type="primary")
    for name in BOOL_FLAGS:
        st.checkbox(name.removeprefix("use_").replace("_", " "), key=f"cfg_{name}", help=FLAG_HELP.get(name))
    with st.expander("k / RRF parameters"):
        for name in INT_FIELDS:
            st.number_input(name, min_value=1, max_value=200, step=1, key=f"cfg_{name}")
    config = RetrievalConfig(**{n: st.session_state[f"cfg_{n}"] for n in BOOL_FLAGS + INT_FIELDS})

    st.divider()
    available, reason = live_status()
    use_live = st.toggle("Live retriever", value=available, disabled=not available, help=reason or None)

# --- Main: query + profile ------------------------------------------------------------------------
question = st.text_area(
    "Question",
    value="I rent a flat in Munich since 2021. If I give notice today, when does my tenancy end?",
    height=80,
)
chat_profile: UserProfile = st.session_state.get("profile", UserProfile())
with st.expander(f":material/person: Profile · {chat_profile.summary()}"):
    st.caption("Taken from the chat sidebar. Edit the JSON to test profile-driven filters.")
    raw_profile = st.text_area("Profile JSON", value=chat_profile.model_dump_json(indent=2), height=260)
try:
    profile = UserProfile.model_validate_json(raw_profile)
except ValueError as exc:
    st.error(f"Invalid profile: {exc}")
    st.stop()

if st.button("Retrieve", type="primary", icon=":material/search:"):
    analyze, retriever, backend = get_retrieval_backend(LIVE if use_live else "Demo")
    t0 = time.perf_counter()
    plan = analyze(question)
    t1 = time.perf_counter()
    result = retriever.retrieve(plan, profile, config)
    t2 = time.perf_counter()
    # Persist across reruns: any later click (e.g. a checkbox) re-runs the script from the top.
    st.session_state.debug_run = {
        "plan": plan,
        "result": result,
        "backend": backend,
        "config": config,
        "timings": (t1 - t0, t2 - t1),
    }

run: dict[str, Any] | None = st.session_state.get("debug_run")
if not run:
    st.info("Enter a question and press **Retrieve**. Works offline on demo data.", icon=":material/info:")
    st.stop()

result: RetrievalResult = run["result"]
plan = run["plan"]

# --- Summary ------------------------------------------------------------------------------------
m = st.columns(5)
m[0].metric("Backend", run["backend"])
m[1].metric("Sub-questions", len(result.sub_results))
m[2].metric("Hits", sum(len(s.hits) for s in result.sub_results))
m[3].metric("Parents (context)", len(result.parents))
m[4].metric("Analysis / retrieval", f"{run['timings'][0] * 1000:.0f} / {run['timings'][1] * 1000:.0f} ms")
flags_on = [n.removeprefix("use_") for n in BOOL_FLAGS if getattr(run["config"], n)]
st.caption("Flags on: " + (", ".join(f"`{f}`" for f in flags_on) or "none (R0)"))

# --- Plan ---------------------------------------------------------------------------------------
st.subheader("1 · Query analysis plan")
st.markdown(f"**Standalone question:** {plan.standalone_question}")
st.dataframe(
    [
        {
            "#": i,
            "sub-question": sq.text,
            "domain": sq.domain.value if sq.domain else "",
            "confidence": sq.domain_confidence,
            "EN rewrites": " | ".join(sq.queries_en),
            "DE rewrites": " | ".join(sq.queries_de),
            "step-back": sq.step_back or "",
            "section kinds": ", ".join(s.value for s in sq.section_kinds),
            "legal refs": ", ".join(sq.legal_references),
        }
        for i, sq in enumerate(plan.sub_queries, start=1)
    ],
    hide_index=True,
    width="stretch",
)

# --- Hits per sub-question ----------------------------------------------------------------------
st.subheader("2 · Fused hits per sub-question")
tabs = st.tabs([f"Q{i}: {s.sub_question[:50]}" for i, s in enumerate(result.sub_results, start=1)])
for tab, sub in zip(tabs, result.sub_results, strict=True):
    with tab:
        left, right = st.columns([2, 1])
        with left:
            st.caption(f"{len(sub.queries)} query variants")
            for i, q in enumerate(sub.queries):
                st.markdown(f"`{i}` {q}")
        with right:
            st.caption("Chroma `where` filter")
            if sub.where:
                st.json(sub.where)
            else:
                st.code("None  (no filters)", language="text")
        list_names = sorted({name for h in sub.hits for name in h.ranks})
        rows = []
        for rank, h in enumerate(sub.hits, start=1):
            md = h.metadata
            row: dict[str, Any] = {
                "rank": rank,
                "fused": h.fused_score,
                "doc_key": md.doc_key,
                "section_kind": md.section_kind.value,
                "lang": md.language,
                "legal_reference": md.legal_reference,
                "title": md.title,
            }
            row |= {name: h.ranks.get(name) for name in list_names}  # one column per ranked list
            rows.append(row)
        st.caption("Per-list columns show the rank of the chunk in that list (empty = not retrieved).")
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "fused": st.column_config.ProgressColumn(
                    "fused (RRF)",
                    format="%.4f",
                    min_value=0.0,
                    max_value=max((h.fused_score for h in sub.hits), default=1.0),
                )
            },
        )

# --- Parents -------------------------------------------------------------------------------------
st.subheader("3 · Context handed to the answer model")
for p in result.parents:
    label = (
        f"[{p.source_id}] {p.legal_reference or p.title} · {p.source_name} · verified {ui.format_date(p.last_verified)}"
    )
    with st.expander(label):
        st.caption(f"{p.heading_path} · `{p.doc_key}` · lang `{p.language}` · chunks {', '.join(p.chunk_ids)}")
        st.markdown(p.text)
        st.link_button("Open source", p.source_url, icon=":material/open_in_new:")
