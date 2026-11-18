"""Chunkers for web pages: guide, procedure and faq (docs/vector-db-design.md §3).

| type      | child                                         | parent                                  |
|-----------|-----------------------------------------------|-----------------------------------------|
| guide     | 200-400 tok paragraph windows, 50 tok overlap | the H2 section                          |
| procedure | one section_kind block (Unterlagen, Kosten…)  | the whole page if <= 2000 tok, else the section |
| faq       | one question + answer                         | the same Q+A                            |
| checklist | a whole document list (<= 700 tok)            | as procedure                            |
| table     | a whole table (row groups + header if large)  | the section                             |

FAQ accordion items found on guide/procedure pages are always emitted as faq chunks: a
question-shaped chunk matches question-shaped user queries much better than a paragraph window.
"""

from __future__ import annotations

from dataclasses import dataclass

from expat.ingestion.chunkers.base import (
    CHECKLIST_MAX,
    FAQ_CHILD_MAX,
    GUIDE_CHILD_MAX,
    GUIDE_OVERLAP,
    GUIDE_PARENT_MAX,
    PROCEDURE_CHILD_MAX,
    PROCEDURE_PAGE_PARENT_MAX,
    TABLE_MAX,
    ChunkDraft,
    ChunkedDocument,
    ParentDraft,
    join_path,
    section_kind_for,
    short_hash,
)
from expat.ingestion.documents import Block, BlockKind, Section, WebDocument
from expat.ingestion.sources import PageConfig, SourceConfig
from expat.ingestion.text import count_tokens, slugify, split_markdown_table, split_text, tail_tokens
from expat.schemas import SectionKind, SourceType


def render_blocks(blocks: list[Block]) -> str:
    """Blocks -> markdown. Used for parent texts and doc_version hashing."""
    parts: list[str] = []
    for block in blocks:
        if block.kind == BlockKind.HEADING:
            parts.append(f"### {block.text}")
        elif block.kind == BlockKind.FAQ:
            parts.append(f"**{block.question}**\n\n{block.text}")
        else:
            parts.append(block.text)
    return "\n\n".join(parts)


def render_page(doc: WebDocument) -> str:
    parts = [f"# {doc.title}"]
    for section in doc.sections:
        if section.heading:
            parts.append(f"## {section.heading}")
        parts.append(render_blocks(section.blocks))
    return "\n\n".join(parts)


@dataclass
class _Ctx:
    """What every chunk of one page shares."""

    doc: WebDocument
    source: SourceConfig
    page: PageConfig
    out: ChunkedDocument

    def heading_path(self, section: Section, *extra: str) -> str:
        return join_path(self.doc.title, *section.context, section.heading, *extra)

    def parent_id(self, path: str) -> str:
        return short_hash(self.doc.url, "parent", path)

    def add_parent(self, path: str, doc_key: str, text: str, title: str, heading_path: str) -> str:
        parent_id = self.parent_id(path)
        self.out.parents.append(
            ParentDraft(
                parent_id=parent_id,
                doc_key=doc_key,
                text=text,
                title=title,
                heading_path=heading_path,
                source_url=self.doc.url,
            )
        )
        return parent_id

    def add_chunk(
        self,
        text: str,
        parent_id: str,
        doc_key: str,
        path: str,
        heading_path: str,
        source_type: SourceType,
        section_kind: SectionKind = SectionKind.OTHER,
        title: str = "",
    ) -> None:
        self.out.chunks.append(
            ChunkDraft(
                text=text,
                parent_id=parent_id,
                doc_key=doc_key,
                structural_path=path,
                title=title or self.doc.title,
                heading_path=heading_path,
                source_type=source_type,
                source_url=self.doc.url,
                section_kind=section_kind,
                alt_lang_url=self.page.alt_lang_url,
            )
        )


def chunk_web(doc: WebDocument, source: SourceConfig, page: PageConfig) -> ChunkedDocument:
    """Dispatch on the page's source_type (page override > source default)."""
    source_type = page.source_type or source.source_type
    out = ChunkedDocument(
        doc_url=doc.url,
        doc_text=render_page(doc),
        title=doc.title,
        valid_from=source.valid_from,
        valid_until=source.valid_until,
    )
    ctx = _Ctx(doc=doc, source=source, page=page, out=out)
    if source_type == SourceType.PROCEDURE:
        _chunk_procedure(ctx)
    elif source_type == SourceType.FAQ:
        _chunk_faq_page(ctx)
    else:  # guide, checklist, table pages are chunked like guides; their blocks keep their own type
        _chunk_guide(ctx)
    return out


# --- FAQ ---------------------------------------------------------------------------------------


def _emit_faq(ctx: _Ctx, question: str, answer: str, section: Section, path: str) -> None:
    """One Q+A = one parent. Long answers are split; every child repeats the question."""
    doc_key = f"{ctx.source.id}#{slugify(question)}"
    full = f"{question}\n\n{answer}"
    heading_path = ctx.heading_path(section, question) if section.heading != question else ctx.heading_path(section)
    parent_id = ctx.add_parent(path, doc_key, full, question, heading_path)
    pieces = split_text(answer, FAQ_CHILD_MAX - count_tokens(question)) or [answer]
    for i, piece in enumerate(pieces):
        ctx.add_chunk(
            f"{question}\n\n{piece}", parent_id, doc_key, f"{path}/{i}", heading_path, SourceType.FAQ, title=question
        )


def _emit_faq_blocks(ctx: _Ctx, section: Section, s_idx: int) -> list[Block]:
    """Emit the section's FAQ blocks; return the remaining (non-FAQ) blocks."""
    rest: list[Block] = []
    for b_idx, block in enumerate(section.blocks):
        if block.kind == BlockKind.FAQ:
            _emit_faq(ctx, block.question, block.text, section, f"s{s_idx}/faq{b_idx}")
        else:
            rest.append(block)
    return rest


def _chunk_faq_page(ctx: _Ctx) -> None:
    """FAQ pages come in two shapes, told apart by the page title:

    - the title is itself a question ("Was ist Kindergeld?", familienportal): the whole body,
      including its H2 sub-sections, is ONE answer;
    - otherwise ("Students and Apprentices", rundfunkbeitrag) every H2 is a question, and
      accordion items anywhere on the page are questions too.
    """
    sections = ctx.doc.sections
    if ctx.doc.title.rstrip().endswith("?"):
        answer = "\n\n".join((f"## {s.heading}\n\n" if s.heading else "") + render_blocks(s.blocks) for s in sections)
        if answer.strip():
            _emit_faq(ctx, ctx.doc.title, answer.strip(), Section(heading=""), "page")
        return
    for s_idx, section in enumerate(sections):
        rest = _emit_faq_blocks(ctx, section, s_idx)
        if any(b.kind != BlockKind.HEADING for b in rest):
            question = section.heading or ctx.doc.title
            _emit_faq(ctx, question, render_blocks(rest), section, f"s{s_idx}")


# --- procedure ---------------------------------------------------------------------------------


def _chunk_procedure(ctx: _Ctx) -> None:
    """One child per section_kind block. The whole page is the parent if it fits (most do), because
    "what do I need and what does it cost" questions span sections of the same page."""
    page_text = render_page(ctx.doc)
    page_parent = ""
    if count_tokens(page_text) <= PROCEDURE_PAGE_PARENT_MAX:
        page_parent = ctx.add_parent("page", ctx.source.id, page_text, ctx.doc.title, ctx.doc.title)

    for s_idx, section in enumerate(ctx.doc.sections):
        rest = _emit_faq_blocks(ctx, section, s_idx)
        if not any(b.kind != BlockKind.HEADING for b in rest):
            continue
        kind = section_kind_for(section.heading)
        doc_key = f"{ctx.source.id}#{kind.value}"
        heading_path = ctx.heading_path(section)
        text = render_blocks(rest)
        parent_id = page_parent or ctx.add_parent(
            f"s{s_idx}",
            doc_key,
            f"## {section.heading}\n\n{text}".strip(),
            section.heading or ctx.doc.title,
            heading_path,
        )
        content_kinds = {b.kind for b in rest} - {BlockKind.HEADING}
        if kind == SectionKind.DOCUMENTS and BlockKind.LIST in content_kinds:
            source_type, limit = SourceType.CHECKLIST, CHECKLIST_MAX  # keep "you need ALL of these" intact
        elif content_kinds == {BlockKind.TABLE}:
            source_type, limit = SourceType.TABLE, TABLE_MAX
        else:
            source_type, limit = SourceType.PROCEDURE, PROCEDURE_CHILD_MAX
        pieces = split_markdown_table(text, limit) if source_type == SourceType.TABLE else split_text(text, limit)
        for i, piece in enumerate(pieces):
            ctx.add_chunk(
                piece,
                parent_id,
                doc_key,
                f"s{s_idx}/{kind.value}/{i}",
                heading_path,
                source_type,
                kind,
                title=section.heading or ctx.doc.title,
            )


# --- guide -------------------------------------------------------------------------------------


@dataclass
class _Unit:
    """A packing unit: a paragraph, or a list/table together with its lead-in and sub-heading."""

    text: str
    kind: BlockKind


def _units(blocks: list[Block]) -> list[_Unit]:
    """Glue sub-headings to the next block and lead-in sentences ("…folgende Unterlagen:") to the
    list or table they introduce, so packing never separates them."""
    units: list[_Unit] = []
    pending: list[str] = []
    for block in blocks:
        if block.kind == BlockKind.HEADING:
            pending.append(f"### {block.text}")
            continue
        introduces_list = (
            block.kind in (BlockKind.LIST, BlockKind.TABLE)
            and units
            and units[-1].kind == BlockKind.TEXT
            and units[-1].text.rstrip().endswith(":")
        )
        if introduces_list and not pending:
            pending.append(units.pop().text)
        units.append(_Unit("\n\n".join([*pending, block.text]), block.kind))
        pending = []
    if pending:
        units.append(_Unit("\n\n".join(pending), BlockKind.TEXT))
    return units


def _chunk_guide(ctx: _Ctx) -> None:
    for s_idx, section in enumerate(ctx.doc.sections):
        rest = _emit_faq_blocks(ctx, section, s_idx)
        if not any(b.kind != BlockKind.HEADING for b in rest):
            continue
        heading = section.heading or ctx.doc.title
        doc_key = f"{ctx.source.id}#{slugify(heading)}"
        heading_path = ctx.heading_path(section)
        kind = section_kind_for(section.heading) if section.heading else SectionKind.OVERVIEW

        # Parent = the H2 section; a very long section is split into consecutive parent parts.
        section_text = render_blocks(rest)
        parent_parts = split_text(section_text, GUIDE_PARENT_MAX)
        units = _units(rest)
        # Assign each unit to the parent part that contains its first line (parts are in order).
        part_of_unit: list[int] = []
        cursor = 0
        for unit in units:
            first_line = unit.text.split("\n", 1)[0]
            while cursor < len(parent_parts) - 1 and first_line not in parent_parts[cursor]:
                cursor += 1
            part_of_unit.append(cursor)
        parent_ids = [
            ctx.add_parent(f"s{s_idx}/p{i}", doc_key, f"## {heading}\n\n{part}", heading, heading_path)
            for i, part in enumerate(parent_parts)
        ]

        for p_idx, parent_id in enumerate(parent_ids):
            part_units = [u for u, p in zip(units, part_of_unit, strict=True) if p == p_idx]
            for c_idx, (text, source_type) in enumerate(_pack(part_units)):
                ctx.add_chunk(
                    text,
                    parent_id,
                    doc_key,
                    f"s{s_idx}/p{p_idx}/{c_idx}",
                    heading_path,
                    source_type,
                    kind,
                    title=heading,
                )


def _pack(units: list[_Unit]) -> list[tuple[str, SourceType]]:
    """Greedy windows of <= 400 tokens with ~50 tokens of overlap between consecutive text windows.

    Tables become their own chunks (row groups with header if > 600 tok). Lists up to 700 tokens
    stay whole even if that exceeds the window: splitting a list loses "all of these apply".
    """
    chunks: list[tuple[str, SourceType]] = []
    window: list[str] = []
    window_tokens = 0
    previous_text = ""  # last emitted text window, for overlap

    def flush() -> None:
        nonlocal window, window_tokens, previous_text
        if window:
            text = "\n\n".join(window)
            chunks.append((text, SourceType.GUIDE))
            previous_text = text
        window, window_tokens = [], 0

    def start_window() -> None:
        nonlocal window, window_tokens
        if previous_text:
            overlap = "…" + tail_tokens(previous_text, GUIDE_OVERLAP)
            window, window_tokens = [overlap], count_tokens(overlap)

    for unit in units:
        tokens = count_tokens(unit.text)
        if unit.kind == BlockKind.TABLE:
            flush()
            chunks.extend((part, SourceType.TABLE) for part in split_markdown_table(unit.text, TABLE_MAX))
            previous_text = ""
            continue
        if unit.kind == BlockKind.LIST and GUIDE_CHILD_MAX < tokens <= CHECKLIST_MAX:
            flush()
            chunks.append((unit.text, SourceType.GUIDE))
            previous_text = ""
            continue
        pieces = split_text(unit.text, GUIDE_CHILD_MAX) if tokens > GUIDE_CHILD_MAX else [unit.text]
        for piece in pieces:
            piece_tokens = count_tokens(piece)
            has_content = window and not (len(window) == 1 and window[0].startswith("…"))
            if has_content and window_tokens + piece_tokens > GUIDE_CHILD_MAX:
                flush()
                start_window()
            if not window:
                start_window()
            window.append(piece)
            window_tokens += piece_tokens
    if window and not (len(window) == 1 and window[0].startswith("…")):
        flush()
    return chunks
