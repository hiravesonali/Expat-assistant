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
