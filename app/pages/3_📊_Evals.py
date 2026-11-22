"""Evals: ablation table + chart from evals/results/*.json.

Expected file format (one file per experiment):
    {"experiment": "R5-filters", "config": {...RetrievalConfig...},
     "metrics": {"hit@5": 0.82, "mrr": 0.61, ...},
     "per_slice": {"tenancy": {"hit@5": 0.9, ...}, "family": {...}}}
"""

import json
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401  (must be first)
import altair as alt
import pandas as pd
import streamlit as st
import ui
from _admin import require_admin

from expat.config import REPO_ROOT

st.set_page_config(page_title="Evals · Ankommen", page_icon="📊", layout="wide")
ui.inject_css()
require_admin()

st.title(":material/monitoring: Evaluation results")
RESULTS_DIR = REPO_ROOT / "evals" / "results"
PRIMARY = "#4A6FA5"  # same muted blue as .streamlit/config.toml

SAMPLE = [
    {"experiment": "R0-baseline", "metrics": {"hit@5": 0.52, "mrr": 0.38}, "per_slice": {}},
    {"experiment": "R1-german", "metrics": {"hit@5": 0.66, "mrr": 0.47}, "per_slice": {}},
    {"experiment": "R4-bm25", "metrics": {"hit@5": 0.78, "mrr": 0.58}, "per_slice": {}},
    {"experiment": "R5-filters", "metrics": {"hit@5": 0.84, "mrr": 0.63}, "per_slice": {}},
]


@st.cache_data(show_spinner=False)
def load_results(paths_and_mtimes: tuple[tuple[str, float], ...]) -> tuple[list[dict[str, Any]], list[str]]:
    results, errors = [], []
    for path, _ in paths_and_mtimes:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data.get("metrics"), dict):
                raise ValueError("missing 'metrics' object")
            data.setdefault("experiment", Path(path).stem)
            data["_file"] = Path(path).name
            results.append(data)
        except (OSError, ValueError) as exc:
            errors.append(f"{Path(path).name}: {exc}")
    return results, errors


files = sorted(RESULTS_DIR.glob("*.json")) if RESULTS_DIR.exists() else []
results, errors = load_results(tuple((str(p), p.stat().st_mtime) for p in files))
for err in errors:
    st.warning(f"Skipped {err}", icon=":material/warning:")

if not results:
    st.info(
        "**No eval results yet.** The eval harness writes one JSON file per experiment to `evals/results/`.\n\n"
        "1. Build the index (`uv run expat-ingest`, `uv run expat-index`).\n"
        "2. Run the retrieval ablations R0–R5, e.g. `uv run expat-eval retrieval --all`.\n"
        "3. Reload this page.\n\n"
        "See `docs/evaluation-plan.md` for the golden set and metrics.",
        icon=":material/science:",
    )
    if not st.toggle("Preview with sample numbers"):
        st.stop()
    st.caption(":orange[Sample numbers for layout preview only, not real results.]")
    results = SAMPLE

# --- Ablation table ------------------------------------------------------------------------------
table = pd.DataFrame([{"experiment": r["experiment"], **r["metrics"]} for r in results]).set_index("experiment")
metric_names = list(table.columns)

st.subheader("Ablation table")
st.dataframe(table.style.format("{:.3f}").highlight_max(color="#dbe5f3"), width="stretch")

# --- Chart: one metric at a time (one hue, one axis, values on hover + in the table above) -------
metric = st.segmented_control("Metric", metric_names, default=metric_names[0], key="eval_metric") or metric_names[0]
chart_df = table[[metric]].reset_index().rename(columns={metric: "value"})
order = list(chart_df["experiment"])  # keep run order (R0 → R5) instead of sorting by value
bars = (
    alt.Chart(chart_df)
    .mark_bar(color=PRIMARY, cornerRadiusEnd=4, size=28)
    .encode(
        y=alt.Y("experiment:N", sort=order, title=None),
        x=alt.X("value:Q", title=metric, scale=alt.Scale(domain=[0, max(1.0, chart_df["value"].max())])),
        tooltip=[alt.Tooltip("experiment:N"), alt.Tooltip("value:Q", title=metric, format=".3f")],
    )
)
labels = bars.mark_text(align="left", dx=4, color="#3d4752").encode(text=alt.Text("value:Q", format=".2f"))
st.altair_chart((bars + labels).properties(height=max(160, 44 * len(chart_df))), width="stretch")

# --- Config per experiment -----------------------------------------------------------------------
with st.expander("Configs per experiment"):
    configs = pd.DataFrame([{"experiment": r["experiment"], **r.get("config", {})} for r in results])
    st.dataframe(configs.set_index("experiment"), width="stretch")

# --- Per-slice table -----------------------------------------------------------------------------
slice_rows = [
    {"experiment": r["experiment"], "slice": name, **vals}
    for r in results
    for name, vals in (r.get("per_slice") or {}).items()
    if isinstance(vals, dict)
]
st.subheader("Per slice")
if slice_rows:
    slices = pd.DataFrame(slice_rows)
    pivot = slices.pivot_table(index="slice", columns="experiment", values=metric) if metric in slices else None
    if pivot is not None:
        st.caption(f"`{metric}` by slice (rows) and experiment (columns)")
        st.dataframe(pivot[[c for c in order if c in pivot.columns]].style.format("{:.3f}"), width="stretch")
    with st.expander("All slice metrics"):
        st.dataframe(slices, hide_index=True, width="stretch")
else:
    st.caption("No per-slice metrics in these results.")
