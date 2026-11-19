"""Fast retrieval experiments: compare many RetrievalConfig settings on the golden set in seconds.

Why this exists next to `expat-eval retrieval`: a full ablation re-runs query analysis (an LLM call)
and re-embeds every query, ~13 min per run. Here both are cached on disk, so the ONLY thing that
changes between rows is the retrieval config. That makes the comparison fair (same plans for every
row) and cheap enough to try ideas. Final numbers for the report still come from `expat-eval`.

    uv run python scripts/retrieval_bench.py                 # dev split, built-in experiment grid
    uv run python scripts/retrieval_bench.py --split all     # dev + holdout
    uv run python scripts/retrieval_bench.py --show bur-005  # print the ranked lists for one question

Cache: data/_bench/ (plans.json, query_embeddings.json). Delete it after changing the analysis prompt.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from expat.config import get_settings
from expat.evals.dataset import load_golden
from expat.evals.retrieval_eval import ablation_variants, needs_query_analysis, retrieval_examples, score_retrieval
from expat.rag.pipeline import build_default_pipeline
from expat.schemas import RetrievalConfig, RetrievalPlan

R5 = RetrievalConfig()
EXPERIMENTS: dict[str, RetrievalConfig] = {
    **ablation_variants(),
    "R5 bm25=german": R5.model_copy(update={"bm25_queries": "german"}),
    "R5 bm25 w=0.5": R5.model_copy(update={"bm25_weight": 0.5}),
    "R5 bm25 w=0.3": R5.model_copy(update={"bm25_weight": 0.3}),
    "R5 german+w0.5": R5.model_copy(update={"bm25_queries": "german", "bm25_weight": 0.5}),
    "R5 german+refs": R5.model_copy(update={"bm25_queries": "german", "bm25_legal_refs": True}),
    "R5 german+refs+w0.5": R5.model_copy(
        update={"bm25_queries": "german", "bm25_legal_refs": True, "bm25_weight": 0.5}
    ),
    "R5 german+refs+w0.3": R5.model_copy(
        update={"bm25_queries": "german", "bm25_legal_refs": True, "bm25_weight": 0.3}
    ),
    "R5 w0.3 no-decomp": R5.model_copy(update={"bm25_weight": 0.3, "use_decomposition": False}),
    "R5 german+refs no-decomp": R5.model_copy(
        update={"bm25_queries": "german", "bm25_legal_refs": True, "use_decomposition": False}
    ),
}


class CachedEmbeddings:
    """Wraps the query embedder; persists vectors so reruns make no embedding API calls."""

    def __init__(self, inner, path: Path) -> None:
        self.inner, self.path = inner, path
        self.model_name = inner.model_name
        self.cache: dict[str, list[float]] = json.loads(path.read_text()) if path.exists() else {}
        self.dirty = False

    def embed_query(self, text: str) -> list[float]:
        if text not in self.cache:
            self.cache[text] = self.inner.embed_query(text)
            self.dirty = True
        return self.cache[text]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)

    def save(self) -> None:
        if self.dirty:
            self.path.write_text(json.dumps(self.cache))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--show", help="golden id: print variants and ranked lists for R5")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cache_dir = get_settings().data_dir / "_bench"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pipeline = build_default_pipeline()
    retriever = pipeline.retriever
    emb = CachedEmbeddings(retriever.vector_store.embeddings, cache_dir / "query_embeddings.json")
    retriever.vector_store.embeddings = emb

    examples = retrieval_examples(load_golden(split=None if args.split == "all" else args.split))
    plans_path = cache_dir / "plans.json"
    plans: dict[str, dict] = json.loads(plans_path.read_text(encoding="utf-8")) if plans_path.exists() else {}
    for ex in examples:
        if ex.id not in plans:
            print(f"analysing {ex.id} …", flush=True)
            plans[ex.id] = pipeline.analyze(ex.question, (), ex.profile).model_dump(mode="json")
            plans_path.write_text(json.dumps(plans, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.show:
        ex = next(e for e in examples if e.id == args.show)
        dbg = retriever.retrieve_debug(RetrievalPlan.model_validate(plans[ex.id]), ex.profile, R5)
        print(ex.question, "\nexpected:", ex.required_doc_keys)
        for sq in dbg.sub_questions:
            print("\n## sub-question:", sq.sub_question)
            for lst in sq.lists:
                keys = [dbg_key(dbg, cid) for cid in lst.chunk_ids[:5]]
                print(f"  {lst.name:16} {lst.query[:60]!r}\n      {keys}")
        print("\nfinal:", dbg.result.all_doc_keys()[:10])
        emb.save()
        return 0

    rows = []
    per_q: dict[str, dict[str, float]] = {}
    for name, cfg in EXPERIMENTS.items():
        scores = []
        for ex in examples:
            # Same rule as expat-eval: R0 gets the RAW question (no analysis), every other row the cached plan.
            plan = (
                RetrievalPlan.model_validate(plans[ex.id])
                if needs_query_analysis(cfg)
                else RetrievalPlan.from_raw(ex.question)
            )
            result = retriever.retrieve(plan, ex.profile, cfg)
            s = score_retrieval(ex, result.all_doc_keys())
            scores.append(s)
            per_q.setdefault(ex.id, {})[name] = s["mrr@10"] or 0.0
        avg = {m: statistics.mean(s[m] or 0.0 for s in scores) for m in ("hit@5", "recall@10", "mrr@10")}
        rows.append((name, avg))
        print(f"{name:22} hit@5 {avg['hit@5']:.2f}  recall@10 {avg['recall@10']:.2f}  MRR@10 {avg['mrr@10']:.2f}")
    emb.save()
    (cache_dir / "last_bench.json").write_text(json.dumps({"rows": rows, "per_question_mrr": per_q}, indent=1))
    return 0


def dbg_key(dbg, chunk_id: str) -> str:
    for sub in dbg.result.sub_results:
        for h in sub.hits:
            if h.chunk_id == chunk_id:
                return h.metadata.doc_key
    return chunk_id[:8]


if __name__ == "__main__":
    raise SystemExit(main())
