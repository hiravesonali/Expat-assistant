import csv
import io
import json
from datetime import datetime

import export

from expat.schemas import Citation, CitationsEvent, DoneEvent, ToolCallEvent, ToolResultEvent

CONV = {
    "title": "End my lease?",
    "messages": [
        {"role": "user", "content": "How much notice do I give?"},
        {
            "role": "assistant",
            "content": "Three months [S1][T1].",
            "mode": "Live",
            "events": [
                ToolCallEvent(call_id="c1", name="calculate_tenancy_notice", args={"party": "tenant"}),
                ToolResultEvent(call_id="c1", name="calculate_tenancy_notice", result={"months": 3}),
                CitationsEvent(
                    citations=[
                        Citation(
                            id="S1",
                            title="Kündigungsfristen",
                            legal_reference="§ 573c BGB",
                            source_url="https://www.gesetze-im-internet.de/bgb/__573c.html",
                            last_verified="2026-11-18",
                            quote="long quote",
                        ),
                        Citation(id="T1", kind="tool", title="Tenancy notice calculator"),
                    ]
                ),
                DoneEvent(latency_ms=1200, input_tokens=10_000, output_tokens=1_000),
            ],
        },
    ],
}
NOW = datetime(2026, 11, 22, 10, 0)


def test_markdown_has_turns_sources_and_disclaimer():
    md = export.to_markdown(CONV, 0.40, 1.60, now=NOW)
    assert md.startswith("# End my lease?")
    assert "not legal or tax advice" in md
    assert "## You\n\nHow much notice do I give?" in md
    assert "- [S1] § 573c BGB · Kündigungsfristen – https://www.gesetze-im-internet.de/bgb/__573c.html" in md
    assert "(verified 2026-11-18)" in md and "`calculate_tenancy_notice`" in md


def test_json_contains_tools_sources_and_cost_but_not_quotes():
    data = json.loads(export.to_json(CONV, 0.40, 1.60, now=NOW))
    answer = data["messages"][1]
    assert answer["tools"] == [
        {"name": "calculate_tenancy_notice", "args": {"party": "tenant"}, "result": {"months": 3}, "error": None}
    ]
    assert [s["id"] for s in answer["sources"]] == ["S1", "T1"] and "quote" not in answer["sources"][0]
    assert answer["usage"]["estimated_cost_usd"] == 0.0056


def test_filename_is_a_safe_slug():
    assert export.filename(CONV, "md") == "ankommen-end-my-lease.md"
    assert export.filename({"title": "§§ ??"}, "json") == "ankommen-chat.json"


def _rows(conv) -> list[dict[str, str]]:
    raw = export.to_csv(conv, 0.40, 1.60)
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: Excel then reads umlauts and § as UTF-8
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def test_csv_has_one_row_per_message_with_sources_tools_and_cost():
    question, answer = _rows(CONV)
    assert (question["turn"], question["role"], question["content"]) == ("1", "user", "How much notice do I give?")
    assert answer["sources"] == "[S1] § 573c BGB · Kündigungsfristen; [T1] Tenancy notice calculator"
    assert answer["source_urls"] == "https://www.gesetze-im-internet.de/bgb/__573c.html"
    assert answer["tools"] == "calculate_tenancy_notice"
    assert (answer["input_tokens"], answer["estimated_cost_usd"], answer["mode"]) == ("10000", "0.0056", "Live")


def test_csv_neutralises_spreadsheet_formulas_and_keeps_multiline_answers():
    conv = {
        "title": "x",
        "messages": [
            {"role": "user", "content": '=HYPERLINK("http://evil.example","click")', "voice": {"seconds": 2.0}},
            {"role": "assistant", "content": "Line one\nLine two, with a comma", "events": []},
        ],
    }
    question, answer = _rows(conv)
    assert question["content"].startswith("'=") and question["voice"] == "yes"
    assert answer["content"] == "Line one\nLine two, with a comma"


def test_html_escapes_chat_text_and_renders_markdown():
    conv = {
        "title": "<Lease>",
        "messages": [
            {"role": "user", "content": "<script>alert(1)</script>"},
            {"role": "assistant", "content": "**Three** months <img src=x>\n\n- one\n- two", "events": []},
        ],
    }
    html = export.to_html(conv, 0.40, 1.60, now=NOW)
    assert "<h1>&lt;Lease&gt;</h1>" in html and "<script>" not in html and "<img" not in html
    assert "<strong>Three</strong>" in html and "<li>one</li>" in html


def test_pdf_contains_the_chat_and_clickable_source_links():
    import pymupdf

    data = export.to_pdf(CONV, 0.40, 1.60, now=NOW)
    assert data.startswith(b"%PDF")
    doc = pymupdf.open(stream=data, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    assert "End my lease?" in text and "Three months [S1][T1]." in text and "§ 573c BGB" in text
    assert "not legal or tax advice" in text
    links = [link.get("uri") for page in doc for link in page.get_links()]
    assert "https://www.gesetze-im-internet.de/bgb/__573c.html" in links


def test_pdf_flows_long_chats_over_several_pages():
    import pymupdf

    long = {"title": "Long", "messages": [{"role": "assistant", "content": "A sentence. " * 1500, "events": []}]}
    assert pymupdf.open(stream=export.to_pdf(long, 0.40, 1.60), filetype="pdf").page_count > 1
