"""Fetcher behaviour against a fake server (httpx.MockTransport): no network, no real sleeping."""

import httpx
import pytest

from expat.ingestion.fetch import USER_AGENT, FetchError, PoliteFetcher, SnapshotStore, read_manual

ROBOTS = "User-agent: *\nDisallow: /private\nCrawl-delay: 3\n"


class FakeServer:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.body = b"<html><body><h1>Hallo</h1></body></html>"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if request.headers.get("if-none-match") == '"v1"' and self.body.startswith(b"<html>"):
            return httpx.Response(304)
        return httpx.Response(200, content=self.body, headers={"etag": '"v1"', "content-type": "text/html"})


@pytest.fixture
def setup(tmp_path):
    server = FakeServer()
    sleeps: list[float] = []
    clock = iter(range(0, 10_000))  # every call advances "time" by 1 s
    client = httpx.Client(transport=httpx.MockTransport(server), headers={"User-Agent": USER_AGENT})
    fetcher = PoliteFetcher(
        SnapshotStore(tmp_path / "raw"), client=client, clock=lambda: float(next(clock)), sleep=sleeps.append
    )
    return fetcher, server, sleeps


def test_fetch_stores_snapshot_and_meta(setup):
    fetcher, server, _ = setup
    result = fetcher.fetch("demo", "https://example.org/page")
    assert result.changed
    assert result.path.read_bytes() == server.body
    assert server.requests[-1].headers["user-agent"] == USER_AGENT


def test_conditional_request_returns_cached_snapshot(setup):
    fetcher, server, _ = setup
    first = fetcher.fetch("demo", "https://example.org/page")
    second = fetcher.fetch("demo", "https://example.org/page")
    assert server.requests[-1].headers["if-none-match"] == '"v1"'
    assert not second.changed
    assert second.path == first.path


def test_robots_disallow_raises(setup):
    fetcher, _, _ = setup
    with pytest.raises(FetchError, match="robots"):
        fetcher.fetch("demo", "https://example.org/private/x")


def test_crawl_delay_is_honoured(setup):
    fetcher, _, sleeps = setup
    fetcher.fetch("demo", "https://example.org/a")
    fetcher.fetch("demo", "https://example.org/b")
    # Crawl-delay 3 > our 1 s minimum; the fake clock advanced ~1-2 s, so we must have slept.
    assert sleeps and max(sleeps) >= 1


def test_offline_reads_latest_snapshot(setup, tmp_path):
    fetcher, _, _ = setup
    online = fetcher.fetch("demo", "https://example.org/page")
    offline = SnapshotStore(tmp_path / "raw").latest("demo", "https://example.org/page")
    assert offline.path == online.path
    assert not offline.from_network


def test_manual_file_missing_is_a_clear_error(tmp_path):
    with pytest.raises(FetchError, match="manual file missing"):
        read_manual("miig-blue-card", "https://example.org", tmp_path / "nope.html")
