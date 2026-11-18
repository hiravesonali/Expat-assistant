"""Polite fetching with on-disk snapshots.

Rules we follow (docs/data-sources.md, "Ingestion policy"):
- robots.txt is checked for every URL (`urllib.robotparser`), with our own User-Agent.
- At least 1 s between two requests to the same host; a larger `Crawl-delay` wins.
- Conditional requests (ETag / If-Modified-Since): an unchanged page costs the server a 304.
- Every response body is saved under `data/raw/<source_id>/<url_hash>/<timestamp>.<ext>`, so
  development and evals can re-parse with `--offline` and never hit the sites again.

Snapshot layout per URL directory:
    meta.json            -> SnapshotMeta (latest file, ETag, Last-Modified, content hash, fetched_at)
    20261117T120501Z.xml -> one file per *distinct* body; an identical body is not stored twice
"""

from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

USER_AGENT = "ExpatAssistantBot/0.1 (educational project)"
MIN_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0


class FetchError(RuntimeError):
    """Raised when a URL cannot be fetched (robots.txt disallow, HTTP error, missing snapshot)."""


class SnapshotMeta(BaseModel):
    """What we remember about the last fetch of one URL (stored as meta.json)."""

    url: str
    final_url: str
    file: str  # file name of the latest snapshot, relative to the URL directory
    content_sha1: str
    content_type: str = ""
    etag: str = ""
    last_modified: str = ""
    fetched_at: datetime  # last time we asked the server (bumped on 304 / identical body)


class FetchResult(BaseModel):
    """A snapshot on disk plus how we got it."""

    url: str
    final_url: str
    path: Path
    fetched_at: datetime
    changed: bool  # False if the server said 304 or returned an identical body
    from_network: bool


def url_hash(url: str) -> str:
    """Short stable directory name for a URL (URLs contain characters Windows paths reject)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _extension(url: str, content_type: str) -> str:
    path = urlsplit(url).path.lower()
    if path.endswith(".zip") or "zip" in content_type:
        return "zip"
    if path.endswith(".pdf") or "pdf" in content_type:
        return "pdf"
    if path.endswith(".xml") or ("xml" in content_type and "html" not in content_type):
        return "xml"
    return "html"


class SnapshotStore:
    """Reads and writes raw snapshots below `data/raw/`."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir

    def url_dir(self, source_id: str, url: str) -> Path:
        return self.raw_dir / source_id / url_hash(url)

    def read_meta(self, source_id: str, url: str) -> SnapshotMeta | None:
        meta_path = self.url_dir(source_id, url) / "meta.json"
        if not meta_path.exists():
            return None
        return SnapshotMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))

    def write_meta(self, source_id: str, meta: SnapshotMeta) -> None:
        directory = self.url_dir(source_id, meta.url)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    def latest(self, source_id: str, url: str) -> FetchResult:
        """The newest snapshot of a URL, used by `--offline` runs."""
        meta = self.read_meta(source_id, url)
        if meta is None:
            raise FetchError(f"no snapshot for {url} (run once without --offline)")
        return FetchResult(
            url=url,
            final_url=meta.final_url,
            path=self.url_dir(source_id, url) / meta.file,
            fetched_at=meta.fetched_at,
            changed=False,
            from_network=False,
        )


class PoliteFetcher:
    """HTTP fetcher that respects robots.txt, rate limits per host and stores snapshots.

    `client`, `clock` and `sleep` are injectable so tests can run against `httpx.MockTransport`
    without real waiting.
    """

    def __init__(
        self,
        store: SnapshotStore,
        client: httpx.Client | None = None,
        min_delay: float = MIN_DELAY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.store = store
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        self.min_delay = min_delay
        self._clock = clock
        self._sleep = sleep
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- politeness -------------------------------------------------------------------------

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        """Fetch and cache robots.txt per host.

        We download it with our own client (same User-Agent, same rate limit) instead of
        `RobotFileParser.read()`, which uses urllib with a generic agent. Status handling
        mirrors the standard library: 401/403 -> everything disallowed, other 4xx -> everything
        allowed, 5xx or network error -> everything disallowed (be conservative).
        """
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host in self._robots:
            return self._robots[host]
        parser = urllib.robotparser.RobotFileParser(f"{host}/robots.txt")
        try:
            self._wait_for_host(parts.netloc, delay=self.min_delay)
            response = self.client.get(f"{host}/robots.txt")
            if response.status_code in (401, 403):
                parser.disallow_all = True  # type: ignore[attr-defined]
            elif 400 <= response.status_code < 500:
                parser.allow_all = True  # type: ignore[attr-defined]
            elif response.status_code >= 500:
                parser.disallow_all = True  # type: ignore[attr-defined]
            else:
                text = response.text
                # Some servers answer /robots.txt with an HTML page (no rules at all).
                parser.parse([] if text.lstrip().startswith("<") else text.splitlines())
        except httpx.HTTPError:
            parser.disallow_all = True  # type: ignore[attr-defined]
        self._robots[host] = parser
        return parser

    def _delay_for(self, url: str) -> float:
        crawl_delay = self._robots_for(url).crawl_delay(USER_AGENT)
        return max(self.min_delay, float(crawl_delay or 0))

    def _wait_for_host(self, netloc: str, delay: float) -> None:
        last = self._last_request.get(netloc)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[netloc] = self._clock()

    # --- fetching ---------------------------------------------------------------------------

    def fetch(self, source_id: str, url: str) -> FetchResult:
        """Fetch one URL (conditionally) and return the snapshot that is now current."""
        robots = self._robots_for(url)
        if not robots.can_fetch(USER_AGENT, url):
            raise FetchError(f"robots.txt disallows {url}")
        delay = self._delay_for(url)

        previous = self.store.read_meta(source_id, url)
        headers: dict[str, str] = {}
        if previous is not None:
            if previous.etag:
                headers["If-None-Match"] = previous.etag
            if previous.last_modified:
                headers["If-Modified-Since"] = previous.last_modified

        self._wait_for_host(urlsplit(url).netloc, delay)
        try:
            response = self.client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {exc}") from exc
        now = datetime.now(UTC).replace(microsecond=0)

        if response.status_code == 304 and previous is not None:
            self.store.write_meta(source_id, previous.model_copy(update={"fetched_at": now}))
            return self._result(source_id, url, previous, now, changed=False)
        if response.status_code != 200:
            raise FetchError(f"{url}: HTTP {response.status_code}")

        body = response.content
        sha1 = hashlib.sha1(body).hexdigest()
        content_type = response.headers.get("content-type", "")
        if previous is not None and previous.content_sha1 == sha1:
            file_name, changed = previous.file, False  # identical body: don't store a duplicate
        else:
            file_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}.{_extension(url, content_type)}"
            directory = self.store.url_dir(source_id, url)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / file_name).write_bytes(body)
            changed = True

        meta = SnapshotMeta(
            url=url,
            final_url=str(response.url),
            file=file_name,
            content_sha1=sha1,
            content_type=content_type,
            etag=response.headers.get("etag", ""),
            last_modified=response.headers.get("last-modified", ""),
            fetched_at=now,
        )
        self.store.write_meta(source_id, meta)
        return self._result(source_id, url, meta, now, changed=changed)

    def _result(self, source_id: str, url: str, meta: SnapshotMeta, now: datetime, changed: bool) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=meta.final_url,
            path=self.store.url_dir(source_id, url) / meta.file,
            fetched_at=now,
            changed=changed,
            from_network=True,
        )


def read_manual(source_id: str, url: str, path: Path) -> FetchResult:
    """A manually saved page (sites with bot protection). The file's mtime is its 'fetch' time."""
    if not path.exists():
        raise FetchError(f"{source_id}: manual file missing: {path} (save {url} there by hand)")
    fetched_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).replace(microsecond=0)
    return FetchResult(url=url, final_url=url, path=path, fetched_at=fetched_at, changed=False, from_network=False)
