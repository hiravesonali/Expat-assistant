"""A scripted, offline stand-in for `expat.rag.pipeline` (Demo mode).

Why this exists: the UI is built against the EVENT CONTRACT (`expat.schemas.events`), not against the
real pipeline. This module yields the same typed events, in the same order, with small sleeps so the
streaming UI looks and feels like the real thing without an API key, an index or the internet.

Two entry points mirror the real code:
- `demo_run(question, history, profile)` -> Iterator[PipelineEvent]   (like `pipeline.run(...)`)
- `demo_analyze(question)` -> RetrievalPlan and `DemoRetriever().retrieve(plan, profile, config)`
  -> RetrievalResult (like query analysis + `HybridRetriever`), used by the Retrieval Debugger page.

Event order (also asserted in tests/app/test_demo_pipeline.py):
    step(query_analysis started/completed) -> step(retrieval started/completed)
    -> [tool_call -> tool_result]* -> step(generation started) -> token* -> step(generation completed)
    -> citations -> answer_meta -> done
or, on failure, an `error` event as the last event.

Step `detail` payloads (the UI renders these, the real pipeline should emit the same shape):
- query_analysis completed: `RetrievalPlan.model_dump(mode="json")` + optional "intent"
- retrieval completed: {"sub_results": [SubQuestionResult.model_dump(mode="json"), ...]}
"""

from __future__ import annotations

import calendar
import re
import time
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from expat.schemas import (
    AnswerMetaEvent,
    ChunkMetadata,
    Citation,
    CitationsEvent,
    ContextSource,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    RankedHit,
    RetrievalConfig,
    RetrievalPlan,
    RetrievalResult,
    StepEvent,
    SubQuery,
    SubQuestionResult,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)
from expat.schemas.chunks import Domain, SectionKind

VERIFIED = date(2026, 11, 18)
STALE_VERIFIED = date(2026, 6, 2)  # > 90 days old: exercises the staleness banner

# --------------------------------------------------------------------------------------------------
# A tiny fake corpus (realistic metadata, short texts). Keywords drive the toy retrieval scoring.
# --------------------------------------------------------------------------------------------------

_CORPUS_SPEC: list[dict[str, Any]] = [
    {
        "doc_key": "bgb#573c",
        "source_id": "bgb",
        "title": "§ 573c Fristen der ordentlichen Kündigung",
        "heading_path": "BGB › Buch 2 › Abschnitt 8 › Titel 5 › Untertitel 2 › § 573c",
        "legal_reference": "§ 573c Abs. 1 BGB",
        "source_url": "https://www.gesetze-im-internet.de/bgb/__573c.html",
        "domain": "tenancy",
        "source_type": "law",
        "section_kind": "deadlines",
        "language": "de",
        "jurisdiction": "federal",
        "text": (
            "(1) Die Kündigung ist spätestens am dritten Werktag eines Kalendermonats zum Ablauf des "
            "übernächsten Monats zulässig. Die Kündigungsfrist für den Vermieter verlängert sich nach fünf "
            "und acht Jahren seit der Überlassung des Wohnraums um jeweils drei Monate."
        ),
        "keywords": "notice period kündigung kündigungsfrist frist tenant landlord terminate end tenancy "
        "lease mieter vermieter months werktag move out",
    },
    {
        "doc_key": "bgb#573",
        "source_id": "bgb",
        "title": "§ 573 Ordentliche Kündigung des Vermieters",
        "heading_path": "BGB › Buch 2 › Abschnitt 8 › Titel 5 › Untertitel 2 › § 573",
        "legal_reference": "§ 573 Abs. 2 BGB",
        "source_url": "https://www.gesetze-im-internet.de/bgb/__573.html",
        "domain": "tenancy",
        "source_type": "law",
        "section_kind": "legal_basis",
        "language": "de",
        "jurisdiction": "federal",
        "text": (
            "(1) Der Vermieter kann nur kündigen, wenn er ein berechtigtes Interesse an der Beendigung des "
            "Mietverhältnisses hat. (2) Ein berechtigtes Interesse liegt insbesondere vor, wenn ... der "
            "Vermieter die Räume als Wohnung für sich, seine Familienangehörigen ... benötigt."
        ),
        "keywords": "landlord terminate eigenbedarf legitimate interest kündigung vermieter own use notice",
    },
    {
        "doc_key": "bgb#568",
        "source_id": "bgb",
        "title": "§ 568 Form und Inhalt der Kündigung",
        "heading_path": "BGB › Buch 2 › Abschnitt 8 › Titel 5 › Untertitel 2 › § 568",
        "legal_reference": "§ 568 Abs. 1 BGB",
        "source_url": "https://www.gesetze-im-internet.de/bgb/__568.html",
        "domain": "tenancy",
        "source_type": "law",
        "section_kind": "requirements",
        "language": "de",
        "jurisdiction": "federal",
        "text": "(1) Die Kündigung des Mietverhältnisses bedarf der schriftlichen Form.",
        "keywords": "written form letter signed email kündigung schriftlich form notice tenant",
    },
    {
        "doc_key": "muc-mietspiegel#overview",
        "source_id": "muc-mietspiegel",
        "title": "Mietspiegel für München 2025",
        "heading_path": "Stadt München › Wohnen › Mietspiegel",
        "legal_reference": "",
        "source_url": "https://stadt.muenchen.de/infos/mietspiegel.html",
        "domain": "tenancy",
        "source_type": "guide",
        "section_kind": "overview",
        "language": "de",
        "jurisdiction": "city",
        "city": "munich",
        "state": "BY",
        "text": "Der Mietspiegel gibt einen Überblick über die ortsübliche Vergleichsmiete in München.",
        "keywords": "rent increase mietspiegel munich miete comparable rent tenancy",
    },
    {
        "doc_key": "muc-anmeldung#documents",
        "source_id": "muc-anmeldung",
        "title": "Wohnsitz anmelden – Unterlagen",
        "heading_path": "Stadt München › Bürgerservice › Wohnsitz anmelden › Unterlagen",
        "legal_reference": "",
        "source_url": "https://stadt.muenchen.de/service/info/wohnsitz-anmelden/",
        "domain": "bureaucracy",
        "source_type": "procedure",
        "section_kind": "documents",
        "language": "de",
        "jurisdiction": "city",
        "city": "munich",
        "state": "BY",
        "text": (
            "Benötigt werden: gültiger Pass oder Personalausweis, die Wohnungsgeberbestätigung des "
            "Vermieters und das ausgefüllte Anmeldeformular."
        ),
        "keywords": "anmeldung register registration address documents passport wohnungsgeberbestätigung "
        "moved munich bürgerbüro",
    },
    {
        "doc_key": "bmg#17",
        "source_id": "bmg",
        "title": "§ 17 Anmeldung, Abmeldung",
        "heading_path": "BMG › Abschnitt 4 › § 17",
        "legal_reference": "§ 17 Abs. 1 BMG",
        "source_url": "https://www.gesetze-im-internet.de/bmg/__17.html",
        "domain": "bureaucracy",
        "source_type": "law",
        "section_kind": "deadlines",
        "language": "de",
        "jurisdiction": "federal",
        "text": (
            "(1) Wer eine Wohnung bezieht, hat sich innerhalb von zwei Wochen nach dem Einzug bei der "
            "Meldebehörde anzumelden."
        ),
        "keywords": "anmeldung register registration deadline two weeks moved einzug meldebehörde",
    },
    {
        "doc_key": "muc-niederlassung-blaue-karte#requirements",
        "source_id": "muc-niederlassung-blaue-karte",
        "title": "Niederlassungserlaubnis für Inhaber der Blauen Karte EU",
        "heading_path": "Stadt München › Ausländerbehörde › Niederlassungserlaubnis Blaue Karte",
        "legal_reference": "§ 18c Abs. 2 AufenthG",
        "source_url": "https://stadt.muenchen.de/service/info/niederlassungserlaubnis-blaue-karte/",
        "domain": "bureaucracy",
        "source_type": "procedure",
        "section_kind": "requirements",
        "language": "de",
        "jurisdiction": "city",
        "city": "munich",
        "state": "BY",
        "text": (
            "Nach 27 Monaten (bzw. 21 Monaten mit Deutschkenntnissen B1) kann eine Niederlassungserlaubnis "
            "erteilt werden."
        ),
        "keywords": "blue card blaue karte settlement permit niederlassungserlaubnis permanent residence months",
        "verified": STALE_VERIFIED,
    },
    {
        "doc_key": "fp-kindergeld#hoehe",
        "source_id": "fp-kindergeld",
        "title": "Kindergeld – Höhe",
        "heading_path": "Familienportal › Kindergeld › Höhe",
        "legal_reference": "§ 66 EStG",
        "source_url": "https://familienportal.de/familienportal/familienleistungen/kindergeld",
        "domain": "family",
        "source_type": "guide",
        "section_kind": "fees",
        "language": "de",
        "jurisdiction": "federal",
        "text": "Das Kindergeld beträgt für jedes Kind monatlich 259 Euro.",
        "keywords": "kindergeld child benefit amount children baby family money",
    },
]


def _build_corpus() -> list[tuple[ChunkMetadata, str, str]]:
    corpus: list[tuple[ChunkMetadata, str, str]] = []
    for i, spec in enumerate(_CORPUS_SPEC):
        meta = ChunkMetadata(
            chunk_id=f"demo-{i:03d}",
            parent_id=spec["doc_key"],
            doc_id=spec["source_id"],
            doc_key=spec["doc_key"],
            doc_version="demo",
            content_hash=f"demo{i}",
            domain=spec["domain"],
            source_type=spec["source_type"],
            section_kind=spec["section_kind"],
            source_id=spec["source_id"],
            source_name="Gesetze im Internet" if spec["source_type"] == "law" else _source_name(spec["source_id"]),
            source_url=spec["source_url"],
            title=spec["title"],
            heading_path=spec["heading_path"],
            legal_reference=spec["legal_reference"],
            language=spec["language"],
            jurisdiction=spec["jurisdiction"],
            state=spec.get("state", ""),
            city=spec.get("city", ""),
            last_verified=spec.get("verified", VERIFIED),
        )
        corpus.append((meta, spec["text"], spec["keywords"]))
    return corpus


def _source_name(source_id: str) -> str:
    if source_id.startswith("muc-"):
        return "Stadt München"
    if source_id.startswith("fp-"):
        return "Familienportal"
    return source_id


CORPUS = _build_corpus()

# --------------------------------------------------------------------------------------------------
# Query analysis + retrieval (toy versions with the real contracts)
# --------------------------------------------------------------------------------------------------

_TENANCY_RE = re.compile(r"notice|kündig|terminat|landlord|lease|tenan|move out|\brent", re.IGNORECASE)
_ANMELDUNG_RE = re.compile(r"anmeld|regist|address|moved to|bürgerbüro", re.IGNORECASE)


def _topic(question: str) -> str:
    if _TENANCY_RE.search(question):
        return "tenancy"
    if _ANMELDUNG_RE.search(question):
        return "anmeldung"
    return "generic"


def demo_analyze(question: str) -> RetrievalPlan:
    """What the single-call QueryAnalysis would return for the scripted topics."""
    topic = _topic(question)
    if topic == "tenancy":
        return RetrievalPlan(
            standalone_question=question,
            sub_queries=[
                SubQuery(
                    text="What is the notice period when a tenant terminates an unlimited lease in Germany?",
                    queries_en=["tenant notice period residential lease Germany", "how many months notice tenant"],
                    queries_de=["Kündigungsfrist Mieter Wohnraum", "Kündigung spätestens dritter Werktag"],
                    step_back="How can a residential lease be terminated in Germany?",
                    domain=Domain.TENANCY,
                    domain_confidence=0.94,
                    section_kinds=[SectionKind.DEADLINES],
                    legal_references=["§ 573c BGB"],
                ),
                SubQuery(
                    text="What form must a tenant's notice of termination have?",
                    queries_en=["written form notice of termination tenancy"],
                    queries_de=["Schriftform Kündigung Mietverhältnis"],
                    domain=Domain.TENANCY,
                    domain_confidence=0.88,
                    section_kinds=[SectionKind.REQUIREMENTS],
                    legal_references=["§ 568 BGB"],
                ),
            ],
        )
    if topic == "anmeldung":
        return RetrievalPlan(
            standalone_question=question,
            sub_queries=[
                SubQuery(
                    text="Which documents do I need to register my address (Anmeldung) in Munich?",
                    queries_en=["documents for address registration Munich"],
                    queries_de=["Wohnsitz anmelden Unterlagen München", "Wohnungsgeberbestätigung"],
                    domain=Domain.BUREAUCRACY,
                    domain_confidence=0.91,
                    section_kinds=[SectionKind.DOCUMENTS],
                ),
                SubQuery(
                    text="What is the deadline for the Anmeldung after moving in?",
                    queries_en=["registration deadline after moving in Germany"],
                    queries_de=["Anmeldung Frist zwei Wochen Einzug"],
                    domain=Domain.BUREAUCRACY,
                    domain_confidence=0.9,
                    section_kinds=[SectionKind.DEADLINES],
                    legal_references=["§ 17 BMG"],
                ),
            ],
        )
    return RetrievalPlan.from_raw(question)


_WORD_RE = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD_RE.findall(text) if len(t) > 2}


class DemoRetriever:
    """Implements the `Retriever` protocol over the fake corpus, honouring the RetrievalConfig flags.

    Scoring is deliberately simple (keyword overlap), but the OUTPUT is shaped exactly like the real
    hybrid retriever's: per-list ranks ("dense:en:0", "bm25:de:1", ...), RRF fused scores, a Chroma-style
    `where` filter and parent expansion into numbered ContextSources.
    """

    def retrieve(
        self,
        plan: RetrievalPlan,
        profile: UserProfile | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult:
        config = config or RetrievalConfig()
        profile = profile or UserProfile()

        sub_queries = plan.sub_queries if config.use_decomposition else [SubQuery(text=plan.standalone_question)]
        if not config.use_decomposition:
            # Without decomposition we still keep the rewrites, merged into one retrieval unit.
            merged = sub_queries[0]
            for sq in plan.sub_queries:
                merged.queries_en += sq.queries_en
                merged.queries_de += sq.queries_de
                merged.step_back = merged.step_back or sq.step_back
                merged.domain = merged.domain or sq.domain

        sub_results: list[SubQuestionResult] = []
        for sq in sub_queries:
            variants: list[tuple[str, str]] = [("en", sq.text)]
            if config.use_multi_query:
                variants += [("en", q) for q in sq.queries_en]
            if config.use_german_rewrite:
                variants += [("de", q) for q in sq.queries_de]
            if config.use_step_back and sq.step_back:
                variants.append(("en", sq.step_back))

            where = self._where(sq, profile) if config.use_filters else None
            candidates = [c for c in CORPUS if self._passes(c[0], where)]

            fused: dict[str, float] = {}
            ranks: dict[str, dict[str, int]] = {}
            retrievers = ["dense", "bm25"] if config.use_bm25 else ["dense"]
            for v_idx, (lang, query) in enumerate(variants):
                q_tokens = _tokens(query)
                for retriever in retrievers:
                    scored = []
                    for meta, text, keywords in candidates:
                        overlap = len(q_tokens & _tokens(keywords + " " + text + " " + meta.title))
                        if retriever == "bm25":
                            # BM25 loves exact legal tokens like "573c".
                            overlap += 3 * sum(
                                ref.split()[1] in text + meta.legal_reference for ref in sq.legal_references
                            )
                        if overlap:
                            scored.append((overlap, meta.chunk_id))
                    scored.sort(key=lambda s: (-s[0], s[1] if retriever == "dense" else s[1][::-1]))
                    for rank, (_, chunk_id) in enumerate(scored[: config.k_dense], start=1):
                        list_name = f"{retriever}:{lang}:{v_idx}"
                        ranks.setdefault(chunk_id, {})[list_name] = rank
                        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (config.rrf_c + rank)

            by_id = {c[0].chunk_id: c for c in CORPUS}
            top = sorted(fused, key=lambda cid: -fused[cid])[: config.k_final]
            hits = [
                RankedHit(
                    chunk_id=cid,
                    text=by_id[cid][1],
                    metadata=by_id[cid][0],
                    fused_score=round(fused[cid], 5),
                    ranks=ranks[cid],
                )
                for cid in top
            ]
            sub_results.append(
                SubQuestionResult(sub_question=sq.text, queries=[q for _, q in variants], where=where, hits=hits)
            )

        return RetrievalResult(
            standalone_question=plan.standalone_question,
            sub_results=sub_results,
            parents=self._parents(sub_results),
        )

    @staticmethod
    def _where(sq: SubQuery, profile: UserProfile) -> dict[str, Any]:
        # The scripted demo corpus is Munich-only, so an unset profile location means Munich here.
        clauses: list[dict[str, Any]] = [
            {"city": {"$in": [profile.city or "munich", ""]}},
            {"state": {"$in": [profile.state or "BY", ""]}},
        ]
        if sq.domain and sq.domain_confidence >= 0.7:
            clauses.append({"domain": sq.domain.value})
        return {"$and": clauses}

    @staticmethod
    def _passes(meta: ChunkMetadata, where: dict[str, Any] | None) -> bool:
        if not where:
            return True
        for clause in where["$and"]:
            ((field, cond),) = clause.items()
            value = getattr(meta, field)
            value = value.value if hasattr(value, "value") else value
            if isinstance(cond, dict) and "$in" in cond:
                if value not in cond["$in"]:
                    return False
            elif value != cond:
                return False
        return True

    @staticmethod
    def _parents(sub_results: list[SubQuestionResult]) -> list[ContextSource]:
        parents: dict[str, ContextSource] = {}
        for sub in sub_results:
            for hit in sub.hits:
                m = hit.metadata
                if m.parent_id in parents:
                    parents[m.parent_id].chunk_ids.append(hit.chunk_id)
                    continue
                parents[m.parent_id] = ContextSource(
                    source_id=f"S{len(parents) + 1}",
                    parent_id=m.parent_id,
                    chunk_ids=[hit.chunk_id],
                    doc_key=m.doc_key,
                    title=m.title,
                    heading_path=m.heading_path,
                    source_name=m.source_name,
                    source_url=m.source_url,
                    legal_reference=m.legal_reference,
                    language=m.language,
                    last_verified=m.last_verified.isoformat(),
                    text=hit.text,
                )
        return list(parents.values())


# --------------------------------------------------------------------------------------------------
# Tool (toy implementation of calculate_tenancy_notice, see docs/tools.md)
# --------------------------------------------------------------------------------------------------


def _third_working_day(year: int, month: int) -> date:
    """3rd working day (Mon-Fri; Saturdays don't count, BGH VIII ZR 291/09). Ignores holidays in the demo."""
    d, count = date(year, month, 1), 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == 3:
                return d
        d += timedelta(days=1)


def _add_months_end(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def demo_tenancy_notice(notice_date: date, tenancy_start: date, party: str = "tenant") -> dict[str, Any]:
    years = (notice_date - tenancy_start).days / 365.25
    period = 3 if party == "tenant" else (9 if years >= 8 else 6 if years >= 5 else 3)
    deadline = _third_working_day(notice_date.year, notice_date.month)
    in_time = notice_date <= deadline
    end = _add_months_end(notice_date, period - 1 if in_time else period)
    return {
        "notice_period_months": period,
        "receipt_deadline_this_month": deadline.isoformat(),
        "received_in_time_for_this_month": in_time,
        "tenancy_end_date": end.isoformat(),
        "legal_basis": "§ 573c Abs. 1 BGB",
        "source_url": "https://www.gesetze-im-internet.de/bgb/__573c.html",
        "rules_version": "2026.1-demo",
        "caveats": [
            "The notice must be a signed letter; email or WhatsApp is not enough (§ 568 BGB).",
            "Check your contract for a waiver of termination (Kündigungsverzicht).",
        ],
    }


# --------------------------------------------------------------------------------------------------
# The scripted run
# --------------------------------------------------------------------------------------------------


def _fmt(d: str) -> str:
    parsed = date.fromisoformat(d)
    return f"{parsed.day} {parsed.strftime('%B %Y')}"  # "%-d" is not portable to Windows


def _stream_text(text: str, delay: float) -> Iterator[TokenEvent]:
    # Real LLMs stream ~3-4 characters per token; we stream word by word (keeping the whitespace).
    for piece in re.findall(r"\S+\s*|\s+", text):
        yield TokenEvent(text=piece)
        _sleep(delay * 0.15)


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _cite(source: ContextSource, sid: str, quote: str = "") -> Citation:
    return Citation(
        id=sid,
        kind="source",
        title=source.title,
        source_name=source.source_name,
        source_url=source.source_url,
        heading_path=source.heading_path,
        legal_reference=source.legal_reference,
        last_verified=source.last_verified,
        quote=quote or source.text,
    )


def demo_run(
    question: str,
    history: list[dict[str, str]] | None = None,
    profile: UserProfile | None = None,
    *,
    delay: float = 0.35,
    today: date | None = None,
) -> Iterator[PipelineEvent]:
    """Yield a realistic event sequence for `question`. `delay=0` makes it instant (tests).

    Type "simulate error" in the question to see the ErrorEvent + retry path.
    """
    started = time.perf_counter()
    profile = profile or UserProfile()
    today = today or date.today()
    topic = _topic(question)

    yield StepEvent(name="query_analysis", status="started")
    _sleep(delay * 2)
    plan = demo_analyze(question)
    intent = "procedural" if topic == "anmeldung" else "info"
    yield StepEvent(
        name="query_analysis",
        status="completed",
        detail={**plan.model_dump(mode="json"), "intent": intent, "history_turns_used": len(history or [])},
    )

    if "simulate error" in question.lower():
        _sleep(delay)
        yield ErrorEvent(
            code="llm_unavailable",
            message="The language model provider did not respond (simulated in Demo mode).",
            retryable=True,
        )
        return

    yield StepEvent(name="retrieval", status="started")
    _sleep(delay * 2)
    result = DemoRetriever().retrieve(plan, profile)
    yield StepEvent(
        name="retrieval",
        status="completed",
        detail={"sub_results": [s.model_dump(mode="json") for s in result.sub_results]},
    )
    by_key = {p.doc_key: p for p in result.parents}

    if topic == "tenancy":
        tenancy_start = date(2021, 3, 1)
        args = {"party": "tenant", "tenancy_start": tenancy_start.isoformat(), "notice_date": today.isoformat()}
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        yield StepEvent(name="tool_call", status="started", detail={"name": "calculate_tenancy_notice"})
        yield ToolCallEvent(call_id=call_id, name="calculate_tenancy_notice", args=args)
        _sleep(delay * 2)
        tool = demo_tenancy_notice(today, tenancy_start)
        yield ToolResultEvent(call_id=call_id, name="calculate_tenancy_notice", result=tool)
        yield StepEvent(name="tool_call", status="completed", detail={"name": "calculate_tenancy_notice"})

        on_time = (
            f"If your letter **arrives by {_fmt(tool['receipt_deadline_this_month'])}** (the 3rd working day "
            f"of this month), your tenancy ends on **{_fmt(tool['tenancy_end_date'])}** [T1]."
            if tool["received_in_time_for_this_month"]
            else f"The 3rd working day of this month has passed, so a letter sent now counts from next month and "
            f"your tenancy ends on **{_fmt(tool['tenancy_end_date'])}** [T1]."
        )
        answer = (
            f"**Short answer:** as a tenant you have a **{tool['notice_period_months']}-month notice period** "
            f"(Kündigungsfrist), no matter how long you have lived in the flat [S1]. {on_time}\n\n"
            "**Details**\n"
            "- The notice counts from the day the landlord *receives* it, not the day you send it [S1].\n"
            "- Only the landlord's notice period grows with the length of the tenancy (to 6 and 9 months) [S1].\n"
            "- The notice must be in **written form**: a signed paper letter (Schriftform), not an email [S2].\n\n"
            "**Your next steps**\n"
            "1. Check your contract for a waiver of termination (Kündigungsverzicht) [T1].\n"
            "2. Sign the letter by hand and send it by registered mail (Einschreiben) or hand it over with a witness.\n"
            "3. Arrange the handover date and the return of your deposit (Kaution) with your landlord.\n"
        )
        s1, s2 = by_key.get("bgb#573c"), by_key.get("bgb#568")
        citations = [c for c in [s1 and _cite(s1, "S1"), s2 and _cite(s2, "S2")] if c]
        citations.append(
            Citation(
                id="T1",
                kind="tool",
                title="calculate_tenancy_notice",
                source_name="Tenancy notice calculator",
                source_url=tool["source_url"],
                legal_reference=tool["legal_basis"],
                last_verified=VERIFIED.isoformat(),
                quote=f"Notice period {tool['notice_period_months']} months; ends {tool['tenancy_end_date']}.",
            )
        )
        meta = AnswerMetaEvent(confidence="grounded")
    elif topic == "anmeldung":
        answer = (
            "**Short answer:** you must register your new address (Anmeldung) **within two weeks** of moving "
            "in [S2].\n\n"
            "**What to bring** [S1]\n"
            "- A valid passport or ID card\n"
            "- The landlord's confirmation (Wohnungsgeberbestätigung)\n"
            "- The completed registration form (Anmeldeformular)\n\n"
            "**Your next steps**\n"
            "1. Ask your landlord for the Wohnungsgeberbestätigung now.\n"
            "2. Book an appointment at a Munich Bürgerbüro; if none is free within two weeks, book the earliest "
            "slot and keep proof.\n"
        )
        s1, s2 = by_key.get("muc-anmeldung#documents"), by_key.get("bmg#17")
        citations = [c for c in [s1 and _cite(s1, "S1"), s2 and _cite(s2, "S2")] if c]
        meta = AnswerMetaEvent(confidence="grounded")
    else:
        answer = (
            "I couldn't find this in my official sources, so I won't guess.\n\n"
            "**Demo mode** only has scripted answers for two topics. Try one of these:\n"
            "- *“I rent a flat in Munich since 2021. If I give notice today, when does my tenancy end?”*\n"
            "- *“I just moved to Munich. What do I need for the Anmeldung, and by when?”*\n\n"
            "Switch to **Live** mode in the sidebar (needs an OpenRouter API key) for real answers."
        )
        citations = []
        meta = AnswerMetaEvent(confidence="insufficient")

    stale = [c.id for c in citations if c.kind == "source" and c.last_verified < "2026-08-01"]
    meta.stale_sources = stale

    yield StepEvent(name="generation", status="started")
    _sleep(delay)
    yield from _stream_text(answer, delay)
    yield StepEvent(name="generation", status="completed")
    yield CitationsEvent(citations=citations)
    yield meta
    yield DoneEvent(
        run_id=f"demo-{uuid.uuid4().hex[:12]}",
        latency_ms=int((time.perf_counter() - started) * 1000),
        input_tokens=2100 + 40 * len(question.split()),
        output_tokens=len(answer.split()) * 4 // 3,
    )
