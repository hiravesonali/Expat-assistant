# Deployment: Streamlit Community Cloud

> Status: prepared, not deployed yet (2026-11-17). Target and fallback are set in ADR-0009.

## How Community Cloud installs this repo (checked against the docs, Nov 2026)

| Question | Answer from the Streamlit docs | What we do |
|---|---|---|
| Which dependency files work? | `uv.lock`, `Pipfile`, `environment.yml`, `requirements.txt`, `pyproject.toml` (`packages.txt` is only for `apt-get` system packages) | Use `app/requirements.txt` |
| Which file wins? | Cloud looks in the **entrypoint's directory first, then the repo root**. In each directory it checks the files in the order above and **uses the first one it finds**. The docs advise using only one dependency file | `app/requirements.txt` is next to `app/Home.py`, so it is chosen before the root `uv.lock`/`pyproject.toml` |
| Is uv used? | "Community Cloud will attempt to process `requirements.txt` with `uv`, but will fall back to `pip` if needed." The docs don't say how `uv.lock`/`pyproject.toml` are installed, or whether the project itself is installed | We don't rely on undocumented behaviour (see below) |
| Python version | Select it under **Advanced settings → Python version** when deploying. 3.12 is the default | Pick **3.12** (matches `.python-version`) |
| Working directory | Cloud runs `streamlit run` from the **repo root** | `.streamlit/config.toml` at the root is picked up |
| Secrets | Paste the contents of a `secrets.toml` into **Advanced settings → Secrets** (editable later in the app settings) | See step 3 |

### Why `app/requirements.txt` and not `-e .`
Our package lives in `src/expat` (src layout). A relative `-e .` line inside a requirements file is resolved
differently by pip and uv (relative to the working directory or to the file), and the file sits in `app/`.
So we export **third-party dependencies only** and make the package importable at runtime instead:

```bash
uv export --no-hashes --no-dev --no-emit-project --format requirements-txt -o app/requirements.txt
```

`app/_bootstrap.py` (imported first by every page) adds `<repo>/src` to `sys.path` if `import expat` fails.
Locally, `uv run` has already installed the package in editable mode, so the bootstrap does nothing.

**Regenerate `app/requirements.txt` whenever `uv.lock` changes** (and commit both together). Otherwise the
deployed app silently runs older versions than your local one.

## Step by step

1. **Push** the branch to GitHub (public repo, or private with Community Cloud access granted).
2. Go to <https://share.streamlit.io> → **Create app** → *Deploy a public app from GitHub*:
   - Repository / branch: your repo, `main`
   - **Main file path: `app/Home.py`**
   - App URL: e.g. `expat-germany-assistant`
3. **Advanced settings:**
   - Python version: **3.12**
   - Secrets: paste your filled-in copy of `.streamlit/secrets.toml.example`. At minimum:
     ```toml
     OPENROUTER_API_KEY = "sk-or-..."
     ADMIN_PASSWORD = "a-long-random-string"
     ```
     Root-level keys are also copied into `os.environ` by `app/pipeline_adapter.py`, because
     `expat.config.Settings` reads environment variables.
4. **Deploy.** The first build takes a few minutes (chromadb, pymupdf and langchain are large).
5. **Smoke test** the deployed app:
   - With no index yet, the sidebar toggle stays on **Demo** and the example prompts work offline.
   - Open a citation chip, the "How I got this answer" timeline, and "simulate error" → Retry.
   - Open an admin page: it must ask for the admin password.

## Where the deployed index lives: a private Hugging Face dataset ([ADR-0010](adr/0010-deployed-index-bundle.md))

The Community Cloud filesystem is **ephemeral** (reset on reboot/redeploy), and we don't commit scraped content
(`data/` is git-ignored). Chroma Cloud was the first choice but is shutting down (Dec 2026), so Chroma runs
**embedded** in the app and its files are shipped as a versioned bundle:

1. **One-time:** create a free account at <https://huggingface.co>, then two tokens under *Settings → Access Tokens*:
   a **write** token for your laptop and a **read** token for the deployed app.
2. **Laptop `.env`:** `INDEX_REPO=<your-hf-name>/expat-index` and `HF_TOKEN=<write token>`.
3. **Publish:** `uv run expat-index --publish`. It creates the private dataset repo (first time), uploads
   `data/chroma`, `data/bm25`, `data/docstore.sqlite` + `index_manifest.json` (~45 MB). Re-run after every data change.
4. **App secrets:** `INDEX_REPO` and `HF_TOKEN` (the **read** token). On the first Live question after a (re)boot,
   `ensure_index()` downloads the bundle once (a few seconds), then everything is read locally.
5. **Pin / roll back** (optional): `INDEX_REVISION = "<commit sha of the dataset repo>"`.

The heavy objects are built **once per server process** via `st.cache_resource`
(`get_live_pipeline()` in `app/pipeline_adapter.py`).

Until the index exists in the deployment, the app runs in **Demo mode**, so the deployed URL always works.

## Admin password

- The admin pages (`app/pages/*`) call `_admin.require_admin()`.
- If `ADMIN_PASSWORD` is set in the secrets, they show a password form. A correct password unlocks all
  admin pages for that browser session.
- Locally, with no `secrets.toml` (or no `ADMIN_PASSWORD`), the pages are open.
- This is a demo-grade gate (one shared password), not user authentication. Rotate it by editing the
  secrets; the app restarts automatically.

## Local run

```bash
uv sync
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # optional; or use .env for OPENROUTER_API_KEY
uv run streamlit run app/Home.py
uv run pytest tests/app                                         # AppTest smoke tests, offline
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'expat'` | A page doesn't import `_bootstrap` first, or the main file path isn't `app/Home.py` | Add `import _bootstrap` as the first import; check the main file path in the app settings |
| `ModuleNotFoundError` for a third-party package that works locally | `app/requirements.txt` is stale | Re-run the `uv export` command above and commit |
| Cloud installs from `uv.lock` instead | `app/requirements.txt` was deleted or renamed | It must sit next to the entrypoint (`app/`) to win over root files |
| Live toggle is disabled | No `OPENROUTER_API_KEY` in secrets, or `expat.rag.pipeline` failed to import | Hover the toggle: the help text shows the reason. Check the logs (*Manage app* → logs) |
| "Loading the retrieval index…" every time / slow | Cold start after the app went to sleep or rebooted | Expected on the free tier. Keep heavy setup inside `st.cache_resource` |
| App crashes with an out-of-memory error | Large models/index in memory (the free tier has limited RAM) | Avoid local rerankers/embedding models in the deployment; use hosted APIs (ADR-0006) |
| Changes to secrets don't apply | Secrets are read at start | Save the secrets in the settings (restarts the app) or reboot it from *Manage app* |
| Admin pages open without a password | `ADMIN_PASSWORD` missing or empty in the deployed secrets | Add it under Settings → Secrets |
| Wrong Python version | Python is chosen at deploy time | Check the app settings; if it cannot be changed there, delete and redeploy with Python 3.12 under Advanced settings |
| Fallback: Community Cloud unavailable | — | Hugging Face Spaces (Streamlit SDK, or the Docker template if that SDK is no longer offered): Spaces read `requirements.txt` from the repo root (copy `app/requirements.txt` there) and `app_file: app/Home.py` from the README front matter; secrets become Space secrets (environment variables) |
