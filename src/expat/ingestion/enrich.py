"""Drafts -> validated ChunkRecord / ParentRecord (docs/vector-db-design.md §4-5).

The chunkers decide structure; this module adds everything that is the same for every chunk type:
deterministic ids and hashes, source-level metadata (jurisdiction, audience, validity), token
counts and the contextual header that is embedded and BM25-indexed together with the text.

Invalid drafts are not dropped silently: they are returned as quarantine entries so the run
report shows them (a validation error usually means a parser picked up the wrong element).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

from expat.ingestion.chunkers.base import ChunkDraft, ChunkedDocument, short_hash
from expat.ingestion.sources import SourceConfig
from expat.ingestion.text import count_tokens
from expat.schemas import ChunkMetadata, ChunkRecord, ParentRecord


def contextual_header(draft: ChunkDraft, domain: str) -> str:
    """`[BGB › § 573c Kündigungsfristen › Abs. 1] [tenancy]`.

    The heading path tells the embedding model *which* law/page/section a short Absatz belongs to;
    the legal reference is added only when the path does not already contain it.
    """
    path = draft.heading_path or draft.title
    if draft.legal_reference and draft.legal_reference not in path:
        path = f"{path} ({draft.legal_reference})"
    return f"[{path}] [{domain}]"


@dataclass
class EnrichResult:
    chunks: list[ChunkRecord] = field(default_factory=list)
    parents: list[ParentRecord] = field(default_factory=list)
    quarantine: list[dict[str, str]] = field(default_factory=list)


def enrich(doc: ChunkedDocument, source: SourceConfig, verified: date) -> EnrichResult:
    doc_id = short_hash(doc.doc_url)
    doc_version = short_hash(doc.doc_text, length=12)
    result = EnrichResult()

    for p in doc.parents:
        result.parents.append(
            ParentRecord(
                parent_id=p.parent_id,
                doc_key=p.doc_key,
                text=p.text,
                title=p.title,
                heading_path=p.heading_path,
                source_url=p.source_url,
                source_name=source.name,
                legal_reference=p.legal_reference,
                language=source.language,
                last_verified=verified,
                token_count=count_tokens(p.text),
            )
        )

    for draft in doc.chunks:
        domain, subtopic = (draft.domain, draft.subtopic) if draft.domain else source.domain_for(None)
        header = contextual_header(draft, domain.value)
        try:
            metadata = ChunkMetadata(
                chunk_id=short_hash(doc_id, draft.structural_path),
                parent_id=draft.parent_id,
                doc_id=doc_id,
                doc_key=draft.doc_key,
                doc_version=doc_version,
                content_hash=short_hash(draft.text),
                domain=domain,
                subtopic=subtopic or source.subtopic,
                source_type=draft.source_type,
                section_kind=draft.section_kind,
                source_id=source.id,
                source_name=source.name,
                source_url=draft.source_url,
                title=draft.title,
                heading_path=draft.heading_path,
                legal_reference=draft.legal_reference,
                language=source.language,
                alt_lang_url=draft.alt_lang_url,
                is_machine_translated=source.is_machine_translated,
                jurisdiction=source.jurisdiction,
                state=source.state,
                city=source.city,
                applies_to=source.applies_to,
                last_verified=verified,
                valid_from=doc.valid_from,
                valid_until=doc.valid_until,
                token_count=count_tokens(draft.text),
            )
        except ValidationError as exc:
            result.quarantine.append(
                {"source_id": source.id, "doc_key": draft.doc_key, "path": draft.structural_path, "error": str(exc)}
            )
            continue
        result.chunks.append(ChunkRecord(text=draft.text, embed_text=f"{header}\n{draft.text}", metadata=metadata))
    return result


def deduplicate(chunks: list[ChunkRecord]) -> tuple[list[ChunkRecord], int]:
    """Drop exact duplicate texts (same content_hash) and duplicate ids; keep the first occurrence.

    The same sentence can appear on several pages (e.g. a BayernPortal and a city page). Embedding
    it twice only fills the top-k with copies.
    """
    seen_hash: set[str] = set()
    seen_id: set[str] = set()
    kept: list[ChunkRecord] = []
    for chunk in chunks:
        m = chunk.metadata
        if m.content_hash in seen_hash or m.chunk_id in seen_id:
            continue
        seen_hash.add(m.content_hash)
        seen_id.add(m.chunk_id)
        kept.append(chunk)
    return kept, len(chunks) - len(kept)
