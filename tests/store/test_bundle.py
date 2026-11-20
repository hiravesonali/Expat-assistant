"""Index bundle (ADR-0010): publish to / download from a Hugging Face dataset repo, tested offline."""

import json
import shutil
from pathlib import Path

import pytest

from expat.config import Settings
from expat.store.bundle import MANIFEST_FILE, IndexBundleError, ensure_index, index_present, publish_bundle

MODEL = "qwen/qwen3-embedding-8b"


def _settings(data_dir: Path, **kw) -> Settings:
    return Settings(data_dir=data_dir, embedding_model=MODEL, hf_token=None, index_revision=None, **kw)


def _fake_index(data_dir: Path) -> None:
    (data_dir / "chroma").mkdir(parents=True)
    (data_dir / "chroma" / "chroma.sqlite3").write_bytes(b"db")
    (data_dir / "bm25").mkdir()
    (data_dir / "bm25" / "records.jsonl").write_text("{}\n", encoding="utf-8")
    (data_dir / "docstore.sqlite").write_bytes(b"db")


class FakeHub:
    """Stands in for HfApi.upload_folder + snapshot_download: a 'repo' is a directory."""

    def __init__(self, root: Path) -> None:
        self.repo = root / "repo"
        self.created: list[tuple] = []

    def create_repo(self, repo_id, repo_type, private, exist_ok):
        self.created.append((repo_id, repo_type, private))

    def upload_folder(self, repo_id, repo_type, folder_path, allow_patterns, delete_patterns, commit_message):
        shutil.copytree(folder_path, self.repo, dirs_exist_ok=True)
        return type("Commit", (), {"commit_url": f"https://hf.co/{repo_id}/commit/1"})()

    def download(self, repo_id, repo_type, revision, local_dir, allow_patterns, token):
        shutil.copytree(self.repo, local_dir, dirs_exist_ok=True)


def test_local_index_is_used_without_any_download(tmp_path):
    _fake_index(tmp_path)
    status = ensure_index(_settings(tmp_path, index_repo=None), download=pytest.fail)
    assert status.source == "local"


def test_missing_index_without_repo_explains_what_to_do(tmp_path):
    with pytest.raises(IndexBundleError, match="INDEX_REPO"):
        ensure_index(_settings(tmp_path / "empty", index_repo=None))


def test_publish_then_download_round_trip(tmp_path):
    laptop, server = tmp_path / "laptop", tmp_path / "server"
    _fake_index(laptop)
    hub = FakeHub(tmp_path)
    url = publish_bundle(_settings(laptop, index_repo="me/expat-index"), chunks=941, parents=442, api=hub)
    assert url.endswith("/commit/1")
    assert hub.created == [("me/expat-index", "dataset", True)]  # always a PRIVATE repo

    assert not index_present(_settings(server))
    status = ensure_index(_settings(server, index_repo="me/expat-index"), download=hub.download)
    assert status.source == "downloaded"
    assert status.manifest["chunks"] == 941 and status.manifest["embedding_model"] == MODEL


def test_index_built_with_another_embedding_model_is_rejected(tmp_path):
    _fake_index(tmp_path)
    (tmp_path / MANIFEST_FILE).write_text(json.dumps({"embedding_model": "openai/text-embedding-3-small"}))
    with pytest.raises(IndexBundleError, match="text-embedding-3-small"):
        ensure_index(_settings(tmp_path))


def test_publish_refuses_without_a_built_index(tmp_path):
    with pytest.raises(IndexBundleError, match="build the index first"):
        publish_bundle(_settings(tmp_path, index_repo="me/x"), chunks=0, parents=0, api=object())
