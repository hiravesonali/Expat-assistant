"""Ship the built index to the deployed app as one versioned bundle (ADR-0010).

The index is three things, all built locally by `expat-index`:
    data/chroma/          Chroma (embedded, open source): chunks + vectors
    data/docstore.sqlite  parent texts (ADR-0001)
    data/bm25/            BM25 index (ADR-0004)

`publish_bundle` uploads them to a PRIVATE Hugging Face dataset repo (free, never sleeps, every upload
is a git commit, so the index is versioned). `ensure_index` runs at app startup: if the files are not
on disk (Streamlit Community Cloud starts with an empty filesystem) it downloads them once. After that
the app reads the same files as on the laptop, so local and deployed behave identically.

Why not a hosted vector DB: Chroma Cloud is shutting down (Dec 2026) and the free tiers of the
alternatives suspend after ~1 week of inactivity, which breaks a demo that is opened weeks later.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from expat.config import Settings, get_settings
from expat.store.bm25 import RECORDS_FILE

MANIFEST_FILE = "index_manifest.json"
BUNDLE_PATTERNS = ["chroma/**", "bm25/**", "docstore.sqlite", MANIFEST_FILE]
REPO_TYPE = "dataset"

logger = logging.getLogger(__name__)


class IndexBundleError(RuntimeError):
    """The index is missing and cannot be downloaded, or it was built for another embedding model."""


@dataclass(frozen=True)
class IndexStatus:
    source: Literal["local", "downloaded"]
    manifest: dict[str, Any]


def index_present(settings: Settings) -> bool:
    return (
        (settings.chroma_dir / "chroma.sqlite3").exists()
        and settings.docstore_path.exists()
        and (settings.bm25_dir / RECORDS_FILE).exists()
    )


def read_manifest(settings: Settings) -> dict[str, Any]:
    path = settings.data_dir / MANIFEST_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_manifest(settings: Settings, chunks: int, parents: int) -> dict[str, Any]:
    manifest = {
        "collection_name": settings.collection_name,
        "embedding_model": settings.embedding_model,
        "schema_version": settings.schema_version,
        "chunks": chunks,
        "parents": parents,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (settings.data_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _token(settings: Settings) -> str | None:
    return settings.hf_token.get_secret_value() if settings.hf_token else None


def _check_model(settings: Settings, manifest: dict[str, Any]) -> None:
    built_with = manifest.get("embedding_model")
    if built_with and built_with != settings.embedding_model:
        raise IndexBundleError(
            f"The index was built with {built_with}, but EMBEDDING_MODEL is {settings.embedding_model}. "
            "Query vectors would not match the stored ones: fix EMBEDDING_MODEL or republish the index."
        )


def remote_manifest(settings: Settings) -> dict[str, Any]:
    """The manifest of the published bundle (one small file download)."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=settings.index_repo or "",
        filename=MANIFEST_FILE,
        repo_type=REPO_TYPE,
        revision=settings.index_revision,
        token=_token(settings),
    )
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _published_newer(settings: Settings, local: dict[str, Any], fetch_remote: Any) -> bool:
    """True if INDEX_REPO holds a bundle published AFTER the local one.

    Without this, a server that kept its files across a reboot would serve the old index forever. "Newer" (not
    "different") so an index built locally but not yet published is never overwritten. Network errors -> False
    (keep serving the local index rather than failing the app).
    """
    if not settings.index_repo:
        return False
    try:
        remote = fetch_remote(settings)
    except Exception as exc:  # offline, HF down, bad token: the local index still works
        logger.warning("Could not check the published index (%s); using the local one.", exc)
        return False
    return str(remote.get("published_at", "")) > str(local.get("published_at", ""))


def ensure_index(settings: Settings | None = None, download: Any = None, fetch_remote: Any = None) -> IndexStatus:
    """Make sure the index files are on disk and current; download the bundle if missing or a newer one was
    published. Call once per process.

    `download` / `fetch_remote` are injectable for tests (defaults: `snapshot_download` / `remote_manifest`).
    """
    s = settings or get_settings()
    if index_present(s):
        manifest = read_manifest(s)
        if not _published_newer(s, manifest, fetch_remote or remote_manifest):
            _check_model(s, manifest)
            return IndexStatus("local", manifest)
    if not s.index_repo:
        raise IndexBundleError(
            "No index on disk and INDEX_REPO is not set. Locally: run `uv run expat-index`. "
            "Deployed: set INDEX_REPO and HF_TOKEN in the Streamlit secrets."
        )
    if download is None:
        from huggingface_hub import snapshot_download as download
    s.data_dir.mkdir(parents=True, exist_ok=True)
    download(
        repo_id=s.index_repo,
        repo_type=REPO_TYPE,
        revision=s.index_revision,
        local_dir=s.data_dir,
        allow_patterns=BUNDLE_PATTERNS,
        token=_token(s),
    )
    if not index_present(s):
        raise IndexBundleError(f"Downloaded {s.index_repo}, but it does not contain a complete index.")
    manifest = read_manifest(s)
    _check_model(s, manifest)
    return IndexStatus("downloaded", manifest)


def publish_bundle(settings: Settings, chunks: int, parents: int, api: Any = None) -> str:
    """Upload the local index to the private dataset repo `INDEX_REPO`. Returns the commit URL.

    `api` is injectable for tests (defaults to `huggingface_hub.HfApi`).
    """
    if not settings.index_repo:
        raise IndexBundleError("Set INDEX_REPO (e.g. your-hf-name/expat-index) in .env to publish.")
    if not index_present(settings):
        raise IndexBundleError("Nothing to publish: build the index first with `uv run expat-index`.")
    manifest = write_manifest(settings, chunks, parents)
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=_token(settings))
    api.create_repo(settings.index_repo, repo_type=REPO_TYPE, private=True, exist_ok=True)
    commit = api.upload_folder(
        repo_id=settings.index_repo,
        repo_type=REPO_TYPE,
        folder_path=settings.data_dir,
        allow_patterns=BUNDLE_PATTERNS,
        delete_patterns=["chroma/**", "bm25/**"],  # drop files of an older build (e.g. old HNSW segments)
        commit_message=f"index: {manifest['collection_name']}, {chunks} chunks, {parents} parents",
    )
    return str(getattr(commit, "commit_url", commit))
