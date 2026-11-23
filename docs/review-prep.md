# Review prep

> Live app: https://expat-assistant.streamlit.app/ (open it 5 minutes early: the free tier sleeps).
> Practise each answer out loud in ≤ 60 s: **decision → alternative considered → evidence (a number)**.

## 1. The 60-second pitch
"**Ankommen** helps expats settle in Germany: registration, permits, renting, family benefits, health
insurance, taxes, citizenship and driving licences. Federal rules everywhere plus local details for six cities
(Berlin, Hamburg, Munich, Cologne, Frankfurt, Stuttgart). You ask in English or German; it answers **only from
official sources** (federal laws, state gazettes, BAMF, Familienportal, city portals) with a citation behind every claim, and it
**calculates** deadlines and amounts with tested tools instead of guessing. Under the hood: one structured
query-analysis call (English ↔ German rewrites, sub-questions, filters), hybrid search (Chroma vectors +
German BM25, fused with RRF), metadata filters from the question and the user profile, and a LangChain
agent with five tools. I evaluated it on a golden set of 85 questions: on **32 held-out questions, correct
answers went from 86% (naive RAG) to 96%, with valid citations throughout, at the same cost of about half a
cent per answer**. Expanding to six cities, I measured that naive search pulls another city's rules into two out of
three answers; with per-question location filters that dropped to zero."

## 2. Demo script (5 minutes)
| # | Do | Point out |
|---|---|---|
| 1 | Start screen | Brand, topic cards, "knows its limits" promises; disclaimer |
| 2 | Card **"End my lease"** | Tool card (Tenancy notice calculator), exact end date, chips `§ 573c BGB` + `T1`; open a chip → quote + "verified" date |
| 3 | Open **"How I got this answer"** | Standalone question, English + **German rewrites**, top hits table with scores, tool input/output, tokens + **≈ $ cost** |
| 4 | Ask: *"My landlord gave me notice after 10 years because he needs the flat for his daughter. How long is my notice period?"* | **9 months** (landlord side, 3+3+3) – a bug the evals found and I fixed |
| 5 | Ask in German: *"Wie viel Kindergeld bekomme ich für zwei Kinder?"* | Answers in German, top source § 66 EStG |
| 6 | Ask: *"Got caught on the U-Bahn without a ticket, now a letter from the police. Will this kill my Blue Card?"* | Safety pre-check → lawyer + migration counselling, no legal guessing |
| 7 | **Personalise answers** → set Blue Card + 2 kids, ask *"What do we need for the Anmeldung?"* | Profile changes retrieval (audience boost) and the checklist tool |
| 7a | Ask: *"We forgot to apply for Kindergeld; our baby was born in January. Do we get it back-paid?"* | Deadline tool: the loss-free date has passed, but applying now still pays 6 months (§ 70 EStG); the judge-calibration story |
| 7b | Ask: *"Do I need a driving test to swap my Japanese licence?"* | Nationwide topic, answered from the FeV country table (Anlage 11); does **not** ask for the city |
| 8 | **Export chat** → Markdown | Sources and calculations travel with the answer |
| 9 | (optional) Settings → Evaluation results page | Ablation + answer-quality tables, LangSmith experiment names |

Backup if the app is slow (cold start or slow embeddings): show the README screenshots and the eval report.

## 3. Requirements → where they are
| Task requirement | Implementation | Code / doc |
|---|---|---|
| Knowledge base, embeddings, chunking, similarity search | 1531 chunks from 78 official sources (laws incl. annex tables, ministries, state gazettes, 6 city portals); §/Absatz- and section-aware chunking, parent expansion; Qwen3-Embedding-8B (bake-off) | `src/expat/ingestion/`, `docs/vector-db-design.md`, ADR-0001/0002 |
| Advanced RAG: query translation + structured retrieval | One structured call: standalone question, EN/DE rewrites, multi-query, step-back, decomposition, domain/section/§ hints; hard + soft metadata filters | `rag/query_analysis.py`, `rag/filters.py`, ADR-0005 |
| ≥ 3 tools | 5: tenancy notice, deadlines, family benefits, document checklist, Schengen 90/180 | `src/expat/tools/`, `docs/tools.md` |
| Domain prompts + security | Safety pre-check (emergency, asylum, court cases, police letters, medical, tax forms), sources as data (injection hygiene), § tripwire | `safety.py`, `rag/prompts.py`, `rag/context.py` |
| LangChain + OpenRouter, error handling | `create_agent` + middleware, `ChatOpenRouter`; errors become events with Retry; transient retries | `rag/generate.py`, `rag/pipeline.py` |
| Input validation | Length/empty/control-char check, per-session + daily limits; Pydantic tool schemas | `guards.py`, `tools/*` |
| UI: context, sources, tool results, progress | Citation chips + dialog, tool cards, live step status, "How I got this answer" | `app/Home.py`, `app/ui.py` |
| **Hard** optional | Hybrid search · RAG evaluation (LangSmith + LLM judge) · multi-language (EN/DE) | ADR-0004, `evals/`, `docs/evaluation-plan.md` |
| **Medium** optional | Prompt-injection protection · personalisation · token + cost display · rate limiting/key management · logging/monitoring (LangSmith) · conversation export | see above |

## 4. Top reviewer questions (with my numbers)

**1. "Explain how RAG works in your app."** Question → analysis (rewrite + German queries) → hybrid search over
chunks with metadata filters → expand to the full parent section → numbered sources `[S1]…` go into the
prompt → the agent answers, calls tools if needed → a validator keeps only real citations. Retrieval always
runs; the model never answers from memory alone.

**2. "English questions, German sources: how does that work, and how do you know?"** A multilingual embedding
model chosen by a bake-off on my golden set (Qwen3-8B vs OpenAI small/large), plus explicit German rewrites
in authority language. Evidence (dev, n = 25): MRR@10 0.77 (raw question) → 0.92 (full pipeline). Answer
correctness on German questions: 0.20 → 0.60 in the first run (dev).

**3. "Which query-translation techniques helped?"** Ablation R0–R5 (dev): German rewrite +0.07 MRR, multi-query
+ step-back +0.05, decomposition +0.03. Honest part: adding BM25 first *hurt* (0.92 → 0.81) because
colloquial words ("security deposit") don't occur in statutes; I fixed it with keyword headers per law
section, and filters brought R5 back to 0.92. On holdout, the no-BM25 variant still ranks best; BM25 is
insurance for exact identifiers (§ 573c, Anlage N), which my golden set under-represents.

**4. "What does structured retrieval mean here?"** Every chunk has validated metadata (domain, section kind,
jurisdiction/state/city, audience, § reference, validity dates). Hard filters only for facts that make a
chunk *wrong* (other city, expired rule, confident domain); soft boosts for audience, section, §.

**5. "How does the model choose between retrieval and tools?"** Retrieval always runs; the agent decides tool
calls from the tool descriptions and the rule "never compute dates or amounts yourself". Evals measure tool
selection (holdout 0.90 naive → 1.00). Real story: the model passed `party="tenant"` for "my landlord gave me notice", so
it got 6 instead of 9 months. Fix: the schema now says "who *sends* the notice".

**6. "How do you prevent hallucinations?"** Prompt rule (no number/§ without a source), tools for maths,
citation validator, § tripwire, and evals: faithfulness 0.92 and valid citations 1.00 on 32 holdout
questions (judge-scored). I also check what the judge flags: for a 10-month stay the app said a US licence
stays valid, but the 6-month extension must be applied for. Known issue, not tuned on holdout.

**7. "How did you evaluate? Why trust an LLM judge?"** 85 golden questions (53 dev / 32 holdout; grew from 40
with the cities and the nationwide topics), retrieval
metrics (hit@5, recall@10, MRR) and answer metrics (faithful, correct, citations, tool selection, refusal).
Judge = Claude Haiku 4.5, a different family than the answer model (GPT-4.1-mini); binary rubrics,
reasoning first. I read every failure: one was a judge mistake (it failed a correct answer as "too
specific"), one was unfair (it couldn't see the user profile – fixed). Calibration sheet: 15
answers with the verdicts hidden (`evals/calibration/`). A second-model check (labelled by Claude Opus, an LLM;
3 items confirmed by a human, including one disagreement) agreed with the judge on **12/15 (kappa 0.44)**. The judge was **too lenient twice**: it
passed an answer that wrongly denied the Kindergeld back-payment, and one that missed documents a foreign family
needs. So I treat judge scores as a trend signal and read the failures myself. The Kindergeld case became a code
fix: the deadline tool now says from which month a late application is still paid, and the eval confirms it.
The judge also errs the other way: it failed a correct licence answer because my reference missed § 31 (1a)
FeV, so I fixed the reference.

**8. "Error scenarios and edge cases?"** Analysis model down → falls back to the raw question (R0 quality, no
crash). Provider timeouts → retries, then an error card with Retry. Empty retrieval → "insufficient
context" instead of guessing. Over-long or empty input → validation message. Abuse → per-session and daily
limits. Blocked judge model → eval pre-flight fails in seconds. Stale sources → "verified" dates + warning.

**9. "Security?"** No accounts, profile = coarse enums in the browser session only; secrets in Streamlit
secrets, never in git; no tracebacks to visitors; sensitive topics redirected; retrieved text treated as data
(delimiters neutralised); admin pages behind a password; spending capped (limits + OpenRouter key limit).

**10a. "How do you make sure a Berlin user never gets Munich rules?"** Every chunk carries jurisdiction / state /
city metadata. Per question I resolve the location (cities named in the question, incl. "Köln"/"München" and
"moving from Berlin to Hamburg" -> both; else the profile; else *unknown* = nationwide sources only) and filter
hard on it. If the answer depends on the city and none is known, the assistant asks "Which city do you live
in?" with one-click buttons and then answers the original question. Evidence: leak@10 0.54–0.56 (naive) ->
0.00 (dev and holdout, 85 questions); clarification accuracy 100%. It once over-asked ("Which city?" for a
federal driving-licence question, because a local office handles it); the prompt rule now keeps federal rules
city-independent.

**10. "Privacy, copyright, liability?"** Statutes are public domain (§ 5 UrhG); portal content: robots.txt
respected, chunks + attribution + deep links, scraped corpus not in git (shipped as a private versioned
bundle). Persistent disclaimer.

## 5. Real stories (reviewers like these)
- **Chroma Cloud shut down mid-sprint** (Replit acquisition, read-only from 22 Nov). Switched to embedded
  Chroma + a versioned index bundle on Hugging Face; free hosted DBs sleep after a week, which kills a demo.
- **A LangSmith decorator ate my config:** `@traceable` treats any argument called `config` as LangChain's
  RunnableConfig, so every non-default retrieval setting crashed – only the eval runner used them.
- **The OpenRouter guardrail blocked my judge** (Sonnet 4.5) → first eval run scored nothing; added a judge
  pre-flight ping and per-metric error isolation.
- **Saturday is not a working day** for the notice deadline (BGH VIII ZR 291/09) – exactly the kind of rule an
  LLM gets wrong, hence a tested tool.
- **OpenRouter reserved credit for 64k output tokens per judge call** (no `max_tokens`) and started rejecting
  calls with "402 payment required" while real spend was tiny – now every role has an output cap.
- **Wrong-city answers are worse than none:** naive search mixed in other cities' rules for ~2/3 of questions.
- **Streamlit Cloud kept old modules in memory** after a push → reboot after changes to `src/`.
- **An official page was out of date:** BAMF's English naturalisation page still offers the 3-year fast track,
  which was abolished on 30 Oct 2025 (StAG § 10 Abs. 3 "weggefallen"). I excluded it and used the current
  German page plus the law, so the bot doesn't repeat outdated rules.
- **Evals cost more than I estimated:** with 85 questions and a judge per metric, a full answer eval of both
  splits used about $4.80 and hit the key limit; the failed run is kept out of the report, not averaged in.

## 6. Known limitations and what I would improve (reflection)
- Golden set still small (85; 6–8 per new topic): one question moves a topic score by 0.12–0.17. → more and harder questions, especially
  exact-identifier and German ones.
- Citation style varies between runs (law named in text instead of `[S1]`). → map bracketed § to sources.
- Latency 10–20 s on slow-embedding days. → cache query embeddings, faster provider, streaming earlier.
- Local coverage: 6 cities in detail; other cities get federal + state rules. Gaps: Frankfurt Anmeldung page
  (frankfurt.de blocks bots), Baden-Württemberg law PDFs (expiring links; the ministry explainer is used).
- Dev answer eval after the last prompt fix covers 10 questions (the full rerun hit the key limit); holdout and
  retrieval evals are complete. Licence extension (6 + 6 months) is not a tool yet (holdout `bur-032`).
- Production: scheduled ingestion, reranker, user feedback loop, Postgres/pgvector or Qdrant if users need
  to write data.
