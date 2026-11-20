# ADR-0010: Deployed index = embedded Chroma + a versioned bundle on Hugging Face

- **Status:** Accepted (2026-11-20). Resolves the open sub-decision of ADR-0009 ("where the deployed index lives").
- **Context:** Deployment on Streamlit Community Cloud is mandatory (ADR-0009). Its filesystem is ephemeral and
  starts empty, and scraped page content is not committed to git (data-sources.md). The index is three things:
  Chroma files (chunks + vectors), a SQLite file (parent texts, ADR-0001) and BM25 files (ADR-0004), ~45 MB.

## History
On 2026-11-19 we chose **Chroma Cloud** and implemented it (CloudClient, parents collection, BM25 rebuilt from the
store). On 2026-11-20 we learned that Chroma joined Replit and **Chroma Cloud is shutting down** (read-only from
22 Nov 2026, offline from 22 Dec 2026). Open-source Chroma is unaffected (Apache 2.0). The implementation was
dropped before it was committed.

## Options (re-evaluated)
| Option | Pros | Cons |
|---|---|---|
| **a. Embedded Chroma + index bundle in a private HF dataset (chosen)** | Same code and files as the laptop; never sleeps; no network hop per query; every upload is a versioned git commit; private | "A database you ship" rather than a server; ~45 MB download on cold start (seconds) |
| b. Qdrant Cloud / Pinecone / Zilliz free tier | Real hosted DB | Free clusters suspend after ~1 week unused (Qdrant: deleted after 4 weeks), so a demo opened weeks later breaks; rewrite of store + filters |
| c. Commit the index / public release asset | No account | Scraped content public / in git history |
| d. Build at first boot | Nothing to host | Slow; gov sites may block US cloud IPs; embedding cost per reboot |

## Decision
- Chroma stays **embedded** (`PersistentClient`) everywhere, like SQLite: a real database engine inside the app process.
- `uv run expat-index --publish` indexes, writes `index_manifest.json` (collection, embedding model, counts, time)
  and uploads `chroma/`, `bm25/`, `docstore.sqlite` and the manifest to the **private** dataset repo `INDEX_REPO`.
- At startup the app calls `ensure_index()` (`expat/store/bundle.py`): if the files are missing it downloads the
  bundle once (`HF_TOKEN`, optional `INDEX_REVISION` to pin a version). It refuses an index built with a different
  embedding model than `EMBEDDING_MODEL`, since query and stored vectors would not match.

## Consequences
- Local and deployed run byte-identical indexes; the eval numbers measured locally hold for the deployment.
- Updating the deployed data = re-run `expat-index --publish`, then reboot the app (or pin `INDEX_REVISION`).
- Rollback = set `INDEX_REVISION` to an earlier commit of the dataset repo.
- Read-only at runtime, which fits: users never write to the index. If users ever needed to add documents, a
  hosted DB (option b on a paid tier) would be required.
- Credentials (`HF_TOKEN`, read-only for the app) live in `.env` / Streamlit secrets, never in git.
