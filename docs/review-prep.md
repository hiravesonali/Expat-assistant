# Review Prep: Top 10 Reviewer Questions

> Practise answering these out loud in ≤ 60 seconds each. The best answers follow **decision → alternative considered → evidence (a number from your evals)**. Fill in the numbers after Day 9.

### 1. "Why one vector collection instead of one per domain?"
Multi-domain questions are the norm for expats. With one collection, routing is a *filter*, so a wrong route degrades gracefully: I drop the filter or use a soft boost. With per-domain collections it's zero recall. I also avoid duplicating content that spans domains (Kindergeld is family and tax). Evidence: R5 vs R4, and filter precision. → ADR-0001

### 2. "Your users write English but your sources are German. How does retrieval work across languages, and how do you know it works?"
Two layers. A multilingual embedding model chosen by a bake-off on my own golden set, which also measured the *cross-lingual gap* (EN vs DE query hit@5). Plus explicit EN→DE query rewriting in authority language, which also makes BM25 useful on German text. Evidence: R0→R1 hit@5 jump. → ADR-0002, ADR-0005

### 3. "Which query-translation techniques did you use, and which actually helped?"
Cross-lingual rewriting, multi-query with RRF, decomposition (multi-domain only), step-back (legal only). All are generated in **one** structured-output call for latency, cost and consistency. HyDE was deliberately excluded, or tested as R7: a hallucinated legal answer can pull in wrong-but-similar passages. Show the ablation table. Say honestly if something didn't help ("decomposition only helped the multi-domain slice, so I gate it").

### 4. "What does 'structured retrieval' mean in your system?"
A Pydantic-validated metadata schema (domain, source_type, `section_kind`, jurisdiction/state/city, audience, `legal_reference`, validity dates) and filters built from **two sources**: the user profile (deterministic: city, state, validity) and the question (LLM: domain, section kind, § reference). Hard vs soft filters avoid over-filtering. It generalises LangChain's self-query retriever. Also: structure-aware chunking (§/Absatz, procedure sections) plus small-to-big parent expansion.

### 5. "Why hybrid search? Isn't the embedding enough?"
Expat questions contain exact identifiers (§ 573c, Anlage N, Steuerklasse III, § 18g AufenthG) that embeddings blur. BM25 with a German stemmer catches them, and RRF fuses rankings without comparing incomparable scores. Local Chroma has no built-in hybrid (it's Cloud-only), and the LangChain BM25 retriever sits in the sunset community package, so I wrote a small, tested BM25 + RRF layer. Evidence: R4 gain on the `legal_lookup` slice. → ADR-0004

### 6. "How do you prevent hallucinated amounts, deadlines or legal references?"
Defence in depth:
- (a) **Prompt rule:** no number, date or § unless it's in a cited source or tool result.
- (b) **Tools:** date and benefit maths happen in unit-tested Python, with constants in a versioned rules file that records source and `last_verified`.
- (c) **Post-checks:** a citation validator plus a **§ tripwire** that flags any § not present in the cited sources.
- (d) **Evals:** faithfulness judge, `must_include` checks, citation correctness.

Evidence: faithfulness score, and the number of tripwire hits on the eval set.

### 7. "How does the model decide between retrieving and calling a tool?"
Retrieval always runs (except out-of-scope), because even calculations need legal context to explain the result, and deterministic retrieval keeps evals reproducible. The answer agent (`create_agent` with a capped loop) decides *autonomously* whether to call tools, guided by tool descriptions and the "never compute yourself" rule. It asks the user when inputs are missing. Evidence: tool-selection accuracy. In Sprint 3, retrieval becomes a tool in a full agent. → ADR-0008

### 8. "How did you evaluate the system? Why should I trust an LLM judge?"
A golden set of N bilingual questions with expected sources at the *section* level (`doc_key`, stable across re-chunking), split dev/holdout. Retrieval metrics are deterministic (hit@5, MRR, recall@10). For answers: an LLM judge from a **different model family**, binary rubrics, and **calibration against 15 hand labels** (agreement X/15). Everything runs as LangSmith experiments, and I report holdout numbers to show I didn't overfit.

### 9. "How do you handle freshness? Rules change every January."
Every chunk has `last_verified`, `valid_from` and `valid_until`. Ingestion is idempotent with content hashes, so a re-run re-embeds only changed chunks and bumps `last_verified` on unchanged ones. Each source has a refresh cadence (laws weekly via `builddate`, portals monthly, a January sweep for amounts). Tool constants live in `rules/2026.yaml` with validity windows, and a `pending_changes` list covers things like the Elterngeld reform and the Rundfunkbeitrag 2027 proposal. The UI shows "verified <date>" and warns when a source is stale.

### 10. "What about privacy, copyright and liability?"
- **Privacy:** a stateless backend. The profile is coarse enums kept in the browser, with no name, address or income. LangSmith runs in the EU region with enum-only metadata.
- **Copyright:** statutes are public domain under § 5 UrhG. For portal content I respected robots.txt and the terms: I *excluded* sources that forbid storage (DRV, Arbeitsagentur) and the copyrighted English law translations. I store chunks with attribution and deep links, and the scraped corpus is not committed.
- **Liability:** a persistent disclaimer, sensitive topics (asylum, eviction suits) redirected to professionals, and "check with the authority" when the context is insufficient.

---

### Bonus questions to be ready for
- *"What would you change for production?"* Postgres + pgvector (hybrid via tsvector) or Qdrant; a scheduled ingestion job; user accounts with consent; a reranker; caching QueryAnalysis for frequent questions; online feedback evals.
- *"What was the hardest bug / biggest surprise?"* Keep a running note during the sprint. Reviewers love real stories (e.g. "Saturday doesn't count as a Werktag for the notice grace period").
- *"Why FastAPI + Next.js instead of just Streamlit?"* Product vs internal tools, streaming UX, and the step timeline as a frontend showcase. → ADR-0003
- *"What does one answer cost and how long does it take?"* Have p50/p95 latency and $/answer from LangSmith ready.
- *"Chunk size: why those numbers?"* Structural boundaries first, token targets second, validated by child-only vs parent-expanded faithfulness.
