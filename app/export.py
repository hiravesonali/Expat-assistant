"""Conversation export as Markdown (to read / share) and JSON (machine-readable, with sources and tool calls).

Pure functions over the session-state conversation dict, so they are unit-tested without Streamlit:
    {"title": str, "messages": [{"role": "user", "content": str}
                               | {"role": "assistant", "content": str, "events": [PipelineEvent], "mode": str}]}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
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


def filename(conv: dict[str, Any], extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", conv["title"].lower()).strip("-")[:40] or "chat"
    return f"ankommen-{slug}.{extension}"
