"""Conversation export: Markdown and PDF to read or share, JSON and CSV for machines (sources, tools, costs).

Pure functions over the session-state conversation dict, so they are unit-tested without Streamlit:
    {"title": str, "messages": [{"role": "user", "content": str}
                               | {"role": "assistant", "content": str, "events": [PipelineEvent], "mode": str}]}
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from html import escape
from typing import Any

from expat.guards import estimate_cost_usd
from expat.schemas import CitationsEvent, DoneEvent, ErrorEvent, ToolCallEvent, ToolResultEvent

DISCLAIMER = "General information from official German sources, not legal or tax advice."


def _of(events: list[Any], kind: type) -> list[Any]:
    return [e for e in events if isinstance(e, kind)]


def _assistant_record(msg: dict[str, Any], price_in: float, price_out: float) -> dict[str, Any]:
    events = msg.get("events", [])
    citations = [c for ev in _of(events, CitationsEvent) for c in ev.citations]
    results = {r.call_id: r for r in _of(events, ToolResultEvent)}
    done = next(iter(_of(events, DoneEvent)), None)
    error = next(iter(_of(events, ErrorEvent)), None)
    record: dict[str, Any] = {
        "role": "assistant",
        "content": msg["content"],
        "mode": msg.get("mode"),
        "sources": [c.model_dump(exclude={"quote"}) for c in citations],
        "tools": [
            {
                "name": call.name,
                "args": call.args,
                "result": results[call.call_id].result if call.call_id in results else None,
                "error": results[call.call_id].error if call.call_id in results else None,
            }
            for call in _of(events, ToolCallEvent)
        ],
    }
    if done:
        record["usage"] = {
            "latency_ms": done.latency_ms,
            "input_tokens": done.input_tokens,
            "output_tokens": done.output_tokens,
            "estimated_cost_usd": round(
                estimate_cost_usd(done.input_tokens, done.output_tokens, price_in, price_out), 6
            ),
        }
    if error:
        record["error"] = f"{error.code}: {error.message}"
    return record


def to_records(conv: dict[str, Any], price_in: float, price_out: float) -> list[dict[str, Any]]:
    return [
        _assistant_record(m, price_in, price_out)
        if m["role"] == "assistant"
        else {"role": "user", "content": m["content"], **({"voice": m["voice"]} if m.get("voice") else {})}
        for m in conv["messages"]
    ]


def to_json(conv: dict[str, Any], price_in: float, price_out: float, now: datetime | None = None) -> str:
    payload = {
        "title": conv["title"],
        "exported_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "messages": to_records(conv, price_in, price_out),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def to_markdown(conv: dict[str, Any], price_in: float, price_out: float, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    lines = [f"# {conv['title']}", "", f"_Exported from Ankommen on {stamp}. {DISCLAIMER}_", ""]
    for rec in to_records(conv, price_in, price_out):
        if rec["role"] == "user":
            lines += ["## You (voice question)" if rec.get("voice") else "## You", "", rec["content"], ""]
            continue
        lines += ["## Assistant", "", rec["content"] or f"_({rec.get('error', 'no answer')})_", ""]
        if rec["tools"]:
            lines.append("**Calculations:** " + ", ".join(f"`{t['name']}`" for t in rec["tools"]))
            lines.append("")
        if rec["sources"]:
            lines.append("**Sources:**")
            for s in rec["sources"]:
                label = " · ".join(x for x in (s["legal_reference"], s["title"]) if x) or s["id"]
                link = f" – {s['source_url']}" if s["source_url"] else ""
                verified = f" (verified {s['last_verified']})" if s["last_verified"] else ""
                lines.append(f"- [{s['id']}] {label}{link}{verified}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


CSV_COLUMNS = ("turn", "role", "content", "mode", "voice", "sources", "source_urls", "tools",
               "input_tokens", "output_tokens", "estimated_cost_usd", "latency_ms", "error")  # fmt: skip
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    """Spreadsheets run a cell that starts with = + - @ as a formula. Chat text is untrusted, so quote it."""
    return "'" + value if isinstance(value, str) and value.startswith(_FORMULA_START) else value


def to_csv(conv: dict[str, Any], price_in: float, price_out: float) -> bytes:
    """One row per message, for a spreadsheet. UTF-8 with a BOM, so Excel shows umlauts and § correctly."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for i, rec in enumerate(to_records(conv, price_in, price_out), start=1):
        sources = rec.get("sources", [])
        usage = rec.get("usage", {})
        row = {
            "turn": i,
            "role": rec["role"],
            "content": rec["content"],
            "mode": rec.get("mode") or "",
            "voice": "yes" if rec.get("voice") else "",
            "sources": "; ".join(
                f"[{s['id']}] " + (" · ".join(x for x in (s["legal_reference"], s["title"]) if x) or s["id"])
                for s in sources
            ),
            "source_urls": " ".join(s["source_url"] for s in sources if s["source_url"]),
            "tools": "; ".join(t["name"] for t in rec.get("tools", [])),
            "input_tokens": usage.get("input_tokens", ""),
            "output_tokens": usage.get("output_tokens", ""),
            "estimated_cost_usd": usage.get("estimated_cost_usd", ""),
            "latency_ms": usage.get("latency_ms", ""),
            "error": rec.get("error", ""),
        }
        writer.writerow({k: _cell(v) for k, v in row.items()})
    return ("﻿" + out.getvalue()).encode("utf-8")


PDF_CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.4; color: #1f2933; }
h1 { font-size: 18pt; margin-bottom: 2pt; }
h2.role { font-size: 11pt; color: #0f5c4d; margin-top: 14pt; margin-bottom: 2pt; }
h2, h3, h4 { font-size: 10.5pt; }
.meta, .sources, .tools { font-size: 8.5pt; color: #52606d; }
a { color: #0f5c4d; }
table { border-collapse: collapse; }
td, th { border: 0.5pt solid #9aa5b1; padding: 2pt 4pt; font-size: 9pt; }
code { font-family: monospace; font-size: 9pt; }
"""


def to_html(conv: dict[str, Any], price_in: float, price_out: float, now: datetime | None = None) -> str:
    """The chat as plain HTML (the PDF is rendered from this). Answers are Markdown; raw HTML in them is escaped."""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    parts = [
        f"<h1>{escape(conv['title'])}</h1>",
        f'<p class="meta">Exported from Ankommen on {stamp}. {escape(DISCLAIMER)}</p>',
    ]
    for rec in to_records(conv, price_in, price_out):
        if rec["role"] == "user":
            heading = "You (voice question)" if rec.get("voice") else "You"
            parts += [f'<h2 class="role">{heading}</h2>', f"<p>{escape(rec['content'])}</p>"]
            continue
        parts.append('<h2 class="role">Assistant</h2>')
        body = md.render(rec["content"]) if rec["content"] else f"<p>({escape(rec.get('error', 'no answer'))})</p>"
        parts.append(body)
        if rec["tools"]:
            names = ", ".join(f"<code>{escape(t['name'])}</code>" for t in rec["tools"])
            parts.append(f'<p class="tools"><b>Calculations:</b> {names}</p>')
        if rec["sources"]:
            items = []
            for s in rec["sources"]:
                label = escape(" · ".join(x for x in (s["legal_reference"], s["title"]) if x) or s["id"])
                url = s["source_url"]
                link = f' – <a href="{escape(url, quote=True)}">{escape(url)}</a>' if url else ""
                verified = f" (verified {escape(str(s['last_verified']))})" if s["last_verified"] else ""
                items.append(f"<li>[{escape(s['id'])}] {label}{link}{verified}</li>")
            parts.append(f'<div class="sources"><b>Sources:</b><ul>{"".join(items)}</ul></div>')
    return "<html><body>" + "\n".join(parts) + "</body></html>"


def to_pdf(conv: dict[str, Any], price_in: float, price_out: float, now: datetime | None = None) -> bytes:
    """A4 PDF with clickable source links, laid out by PyMuPDF (already a dependency of the ingestion)."""
    import pymupdf

    story = pymupdf.Story(html=to_html(conv, price_in, price_out, now), user_css=PDF_CSS)
    page = pymupdf.paper_rect("a4")
    content = pymupdf.Rect(page.x0 + 50, page.y0 + 50, page.x1 - 50, page.y1 - 50)  # margins
    document = story.write_with_links(lambda _rect_num, _filled: (page, content, None))
    return bytes(document.tobytes(garbage=3, deflate=True))


def filename(conv: dict[str, Any], extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", conv["title"].lower()).strip("-")[:40] or "chat"
    return f"ankommen-{slug}.{extension}"
