"""Ingestion Status: per-source status from data/processed/manifest.json.

The manifest format belongs to the ingestion module; this page accepts the common shapes:
    {"sources": [{"source_id": ..., "status": ..., ...}, ...]}   (list under a key)
    {"bgb": {"status": ..., ...}, "bmg": {...}}                 (dict keyed by source_id)
    [{"source_id": ..., ...}, ...]                               (bare list)
"""

import json
from typing import Any

import _bootstrap  # noqa: F401  (must be first)
import pandas as pd
import streamlit as st
import ui
from _admin import require_admin

from expat.config import get_settings

st.set_page_config(page_title="Ingestion Status", page_icon="⚙️", layout="wide")
ui.inject_css()
require_admin()

st.title(":material/settings_suggest: Ingestion status")
MANIFEST = get_settings().processed_dir / "manifest.json"

STATUS_ICON = {
    "ok": "✅",
    "success": "✅",
    "done": "✅",
    "skipped": "⏭️",
    "unchanged": "⏭️",
    "failed": "❌",
    "error": "❌",
}


def normalise(manifest: Any) -> list[dict[str, Any]]:
    if isinstance(manifest, dict):
        for key in ("sources", "items", "entries"):
            if isinstance(manifest.get(key), list):
                return manifest[key]
        return [{"source_id": k, **v} for k, v in manifest.items() if isinstance(v, dict)]
    if isinstance(manifest, list):
        return [m for m in manifest if isinstance(m, dict)]
    return []


if not MANIFEST.exists():
    st.info(
        "**Nothing ingested yet.** The ingestion CLI writes `data/processed/manifest.json` with one entry per "
        "source (status, chunk count, fetch time, errors).\n\nRun `uv run expat-ingest` and reload this page.",
        icon=":material/cloud_download:",
    )
    st.stop()

try:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    st.error(f"Could not read the manifest: {exc}")
    st.stop()

rows = normalise(raw)
if not rows:
    st.warning("The manifest has no source entries.")
    st.json(raw, expanded=False)
    st.stop()

df = pd.DataFrame(rows)
if "status" in df:
    df.insert(0, "", df["status"].astype(str).str.lower().map(STATUS_ICON).fillna("•"))

failed = df["status"].astype(str).str.lower().isin(["failed", "error"]).sum() if "status" in df else 0
chunk_col = next((c for c in ("chunks", "chunk_count", "n_chunks") if c in df), None)
m = st.columns(4)
m[0].metric("Sources", len(df))
m[1].metric("Failed", int(failed))
m[2].metric("Chunks", f"{int(df[chunk_col].fillna(0).sum()):,}" if chunk_col else "—")
time_col = next((c for c in ("fetched_at", "last_fetched", "last_verified", "updated_at") if c in df), None)
m[3].metric("Last run", str(df[time_col].dropna().max())[:16] if time_col else "—")

preferred = ["", "source_id", "status", chunk_col, "parents", "language", time_col, "content_hash", "error"]
cols = [c for c in preferred if c and c in df] + [c for c in df.columns if c not in preferred]
st.dataframe(df[cols], hide_index=True, width="stretch")

with st.expander("Raw manifest"):
    st.json(raw, expanded=False)
st.caption(f"Read from `{MANIFEST}` · modified {pd.Timestamp(MANIFEST.stat().st_mtime, unit='s'):%Y-%m-%d %H:%M} UTC")
