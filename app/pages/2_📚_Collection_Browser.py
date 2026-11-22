"""Collection Browser: search and filter the ingested chunks (data/processed/chunks.jsonl)."""

import json
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401  (must be first)
import pandas as pd
import streamlit as st
import ui
from _admin import require_admin

from expat.config import get_settings

st.set_page_config(page_title="Collection Browser · Ankommen", page_icon="📚", layout="wide")
ui.inject_css()
require_admin()

st.title(":material/library_books: Collection Browser")
CHUNKS = get_settings().processed_dir / "chunks.jsonl"
MAX_ROWS = 1000


@st.cache_data(show_spinner="Reading chunks…")
def load_chunks(path: str, mtime: float) -> pd.DataFrame:
    """Cached by (path, mtime): re-ingesting changes the mtime, which invalidates the cache automatically.

    `st.cache_data` stores the return value (copied per caller), like memoising a fetch.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            meta = rec.get("metadata", {})
            rows.append({**meta, "text": rec.get("text", ""), "embed_text": rec.get("embed_text", "")})
    return pd.DataFrame(rows)


if not CHUNKS.exists():
    st.info(
        f"**No chunks yet.** This page reads `{CHUNKS.relative_to(get_settings().data_dir.parent)}`, "
        "which the ingestion pipeline writes.\n\n"
        "Run the ingestion first, e.g. `uv run expat-ingest`, then reload this page.",
        icon=":material/inventory_2:",
    )
    st.stop()

df = load_chunks(str(CHUNKS), CHUNKS.stat().st_mtime)
if df.empty:
    st.warning("chunks.jsonl is empty.")
    st.stop()

# --- Filters -------------------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Filters")
    filters: dict[str, list[str]] = {}
    for col in ("source_id", "domain", "source_type", "language", "section_kind"):
        if col in df:
            options = sorted(df[col].dropna().astype(str).unique())
            filters[col] = st.multiselect(col.replace("_", " "), options, key=f"f_{col}")
search = st.text_input("Search text, title or § reference", placeholder="e.g. Kündigungsfrist or 573c")

mask = pd.Series(True, index=df.index)
for col, selected in filters.items():
    if selected:
        mask &= df[col].astype(str).isin(selected)
if search:
    haystack = df[[c for c in ("text", "title", "legal_reference", "doc_key") if c in df]].astype(str).agg(" ".join, 1)
    mask &= haystack.str.contains(search, case=False, regex=False)
view = df[mask]

m = st.columns(4)
m[0].metric("Chunks (filtered / total)", f"{len(view):,} / {len(df):,}")
m[1].metric("Sources", view["source_id"].nunique() if "source_id" in view else "—")
m[2].metric("Parents", view["parent_id"].nunique() if "parent_id" in view else "—")
m[3].metric("Avg tokens", f"{view['token_count'].mean():.0f}" if "token_count" in view and len(view) else "—")

columns = [
    c
    for c in ("doc_key", "title", "legal_reference", "section_kind", "language", "source_type", "domain", "token_count")
    if c in view
]
if len(view) > MAX_ROWS:
    st.caption(f"Showing the first {MAX_ROWS:,} matches. Narrow the filters to see more.")
event = st.dataframe(
    view[columns].head(MAX_ROWS),
    hide_index=True,
    width="stretch",
    on_select="rerun",  # selecting a row reruns the script; the selection comes back in `event`
    selection_mode="single-row",
    height=380,
)

selected = event.selection.rows if event else []
if not selected:
    st.caption("Select a row to see its text and metadata.")
    st.stop()

row = view.head(MAX_ROWS).iloc[selected[0]]
st.subheader(row.get("title", ""))
st.caption(f"{row.get('heading_path', '')} · `{row.get('chunk_id', '')}`")
left, right = st.columns([3, 2])
with left:
    st.markdown("**Chunk text**")
    st.markdown(row.get("text", ""))
    with st.expander("embed_text (contextual header + text, used for embeddings and BM25)"):
        st.text(row.get("embed_text", ""))
with right:
    st.markdown("**Metadata**")
    # Round-trip through pandas' JSON writer: converts numpy scalars that st.json can't serialise.
    st.json(json.loads(row.drop(["text", "embed_text"], errors="ignore").to_json(force_ascii=False)), expanded=True)
    if row.get("source_url"):
        st.link_button("Open source", row["source_url"], icon=":material/open_in_new:")
