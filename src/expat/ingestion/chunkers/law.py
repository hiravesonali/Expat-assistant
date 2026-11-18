"""Law / regulation chunker: child = Absatz (or the whole § if short), parent = the §.

Why Absatz-level children? Citations must be exact ("§ 573c Abs. 1 BGB") and BM25 must hit the
precise provision. Why the § as parent? Absatz 2 often only makes sense next to Absatz 1
("…this period…"), so the LLM gets the whole § (docs/vector-db-design.md §3).
"""

from __future__ import annotations

import re

from expat.ingestion.chunkers.base import (
    LAW_CHILD_MAX,
    LAW_PARENT_MAX,
    LAW_WHOLE_PARAGRAPH_MAX,
    TABLE_MAX,
    ChunkDraft,
    ChunkedDocument,
    ParentDraft,
    join_path,
)
from expat.ingestion.documents import LawDocument, LawNorm
from expat.ingestion.sources import SourceConfig
from expat.ingestion.text import count_tokens, split_markdown_table, split_text
from expat.schemas import SourceType

_ABSATZ_NR_RE = re.compile(r"^\((\d+[a-z]?)\)\s")


def chunk_law(doc: LawDocument, source: SourceConfig) -> ChunkedDocument:
    abbrev = source.law_abbrev or doc.abbrev
    norms = [n for n in doc.norms if n.is_table or source.includes_paragraph(n.paragraph)]
    result = ChunkedDocument(
        doc_url=doc.url,
        doc_text="\n\n".join(_norm_text(n) for n in norms),
        title=doc.long_title or source.name,
        valid_from=doc.valid_from or source.valid_from,
        valid_until=doc.valid_until or source.valid_until,
    )
    for norm in norms:
        if norm.is_table:
            _chunk_table_norm(norm, abbrev, source, result)
        else:
            _chunk_norm(norm, abbrev, source, result)
    return result


def _norm_heading(norm: LawNorm) -> str:
    return f"{norm.enbez} {norm.title}".strip()


def _norm_text(norm: LawNorm) -> str:
    return _norm_heading(norm) + "\n\n" + "\n\n".join(norm.absaetze)


def _chunk_norm(norm: LawNorm, abbrev: str, source: SourceConfig, out: ChunkedDocument) -> None:
    domain, subtopic = source.domain_for(norm.paragraph)
    doc_key = f"{source.id}#{norm.paragraph}"
    heading_path = join_path(abbrev, *norm.gliederung[-1:], _norm_heading(norm))
    reference = f"{norm.enbez} {abbrev}"

    # Parents: normally the whole §. A huge § (some AufenthG/EStG norms) is split into groups of
    # consecutive Absätze so a parent never blows the LLM context budget.
    groups = _group_absaetze(norm.absaetze, LAW_PARENT_MAX - count_tokens(_norm_heading(norm)))
    parent_for_absatz: dict[int, str] = {}
    for g, (start, end) in enumerate(groups):
        parent_id = doc_key if g == 0 else f"{doc_key}~{g + 1}"
        out.parents.append(
            ParentDraft(
                parent_id=parent_id,
                doc_key=doc_key,
                text=_norm_heading(norm) + "\n\n" + "\n\n".join(norm.absaetze[start:end]),
                title=norm.title or norm.enbez,
                heading_path=heading_path,
                source_url=norm.url,
                legal_reference=reference,
            )
        )
        for i in range(start, end):
            parent_for_absatz[i] = parent_id

    def child(text: str, parent_id: str, path: str, child_heading_path: str, ref: str) -> ChunkDraft:
        return ChunkDraft(
            text=text,
            parent_id=parent_id,
            doc_key=doc_key,
            structural_path=path,
            title=norm.title or norm.enbez,
            heading_path=child_heading_path,
            source_type=source.source_type,
            source_url=norm.url,
            legal_reference=ref,
            domain=domain,
            subtopic=subtopic,
        )

    if count_tokens(_norm_text(norm)) < LAW_WHOLE_PARAGRAPH_MAX:
        whole = "\n\n".join(norm.absaetze)
        out.chunks.append(child(whole, parent_for_absatz[0], f"{norm.paragraph}/all", heading_path, reference))
        return

    numbered = len(norm.absaetze) > 1
    for i, absatz in enumerate(norm.absaetze):
        match = _ABSATZ_NR_RE.match(absatz)
        abs_label = f"Abs. {match.group(1)}" if (match and numbered) else ""
        ref = f"{norm.enbez} {abs_label} {abbrev}" if abs_label else reference
        for j, piece in enumerate(split_text(absatz, LAW_CHILD_MAX)):
            path = f"{norm.paragraph}/p{i}/{j}"
            out.chunks.append(child(piece, parent_for_absatz[i], path, join_path(heading_path, abs_label), ref))


def _group_absaetze(absaetze: list[str], budget: int) -> list[tuple[int, int]]:
    """Greedy [start, end) groups of consecutive Absätze whose total stays within `budget` tokens."""
    groups: list[tuple[int, int]] = []
    start, used = 0, 0
    for i, absatz in enumerate(absaetze):
        tokens = count_tokens(absatz)
        if i > start and used + tokens > budget:
            groups.append((start, i))
            start, used = i, 0
        used += tokens
    groups.append((start, len(absaetze)))
    return groups


def _chunk_table_norm(norm: LawNorm, abbrev: str, source: SourceConfig, out: ChunkedDocument) -> None:
    """An Anlage table (e.g. the MiSchuV municipality list): row groups with the header repeated.

    Each row group is its own parent as well: the full list is ~4k tokens, too big to send whole,
    and a row group is self-contained thanks to the repeated header.
    """
    domain, subtopic = source.domain_for(None)
    doc_key = f"{source.id}#{norm.paragraph}"
    heading = _norm_heading(norm)
    heading_path = join_path(abbrev, heading)
    reference = f"{norm.enbez.split(' (')[0]} {abbrev}"  # "Anlage MiSchuV"
    for i, part in enumerate(split_markdown_table(norm.absaetze[0], TABLE_MAX)):
        parent_id = doc_key if i == 0 else f"{doc_key}~{i + 1}"
        text = f"{heading}\n\n{part}"
        out.parents.append(
            ParentDraft(
                parent_id=parent_id,
                doc_key=doc_key,
                text=text,
                title=norm.title or norm.enbez,
                heading_path=heading_path,
                source_url=norm.url,
                legal_reference=reference,
            )
        )
        out.chunks.append(
            ChunkDraft(
                text=text,
                parent_id=parent_id,
                doc_key=doc_key,
                structural_path=f"{norm.paragraph}/rows{i}",
                title=norm.title or norm.enbez,
                heading_path=heading_path,
                source_type=SourceType.TABLE,
                source_url=norm.url,
                legal_reference=reference,
                domain=domain,
                subtopic=subtopic,
            )
        )
