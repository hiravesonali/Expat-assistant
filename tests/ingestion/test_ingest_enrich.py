"""enrich: contextual header keywords and change detection over what is actually embedded."""

from datetime import date

from expat.ingestion.chunkers.base import ChunkDraft, ChunkedDocument, ParentDraft
from expat.ingestion.enrich import deduplicate, enrich
from expat.ingestion.sources import DomainRange, SourceConfig
from expat.schemas import SourceType

VERIFIED = date(2026, 11, 19)


def law_source(**extra) -> SourceConfig:
    return SourceConfig(
        id="bgb",
        name="BGB",
        url="https://www.gesetze-im-internet.de/bgb/xml.zip",
        source_type=SourceType.LAW,
        parser="law_xml",
        domain="tenancy",
        jurisdiction="federal",
        **extra,
    )


def doc_for(paragraph: str, text: str = "(1) Die Miete zu Beginn des Mietverhältnisses …") -> ChunkedDocument:
    doc_key = f"bgb#{paragraph}"
    return ChunkedDocument(
        doc_url="https://www.gesetze-im-internet.de/bgb/xml.zip",
        doc_text=text,
        title="BGB",
        parents=[ParentDraft(doc_key, doc_key, text, "t", "BGB › § x", "https://x")],
        chunks=[
            ChunkDraft(
                text=text,
                parent_id=doc_key,
                doc_key=doc_key,
                structural_path=f"{paragraph}/all",
                title="Zulässige Miethöhe bei Mietbeginn",
                heading_path=f"BGB › § {paragraph} Zulässige Miethöhe bei Mietbeginn",
                source_type=SourceType.LAW,
                source_url="https://x",
                legal_reference=f"§ {paragraph} BGB",
            )
        ],
    )


RENT_CAP = DomainRange(range="556d-556g", domain="tenancy", keywords=["Mietpreisbremse", "rent cap"])


def test_range_keywords_go_into_the_embedded_header_only_for_matching_paragraphs():
    source = law_source(domain_map=[RENT_CAP])
    inside = enrich(doc_for("556d"), source, VERIFIED).chunks[0]
    outside = enrich(doc_for("573c"), source, VERIFIED).chunks[0]
    assert inside.embed_text.splitlines()[0].endswith("[Mietpreisbremse, rent cap]")
    assert "Mietpreisbremse" not in outside.embed_text
    assert "Mietpreisbremse" not in inside.text  # the citable text stays the official wording


def test_adding_keywords_changes_content_hash_so_the_indexer_re_embeds():
    plain = enrich(doc_for("556d"), law_source(), VERIFIED).chunks[0]
    with_kw = enrich(doc_for("556d"), law_source(domain_map=[RENT_CAP]), VERIFIED).chunks[0]
    assert plain.metadata.chunk_id == with_kw.metadata.chunk_id  # same chunk ...
    assert plain.metadata.content_hash != with_kw.metadata.content_hash  # ... new vector needed


def test_deduplicate_compares_text_not_header():
    a = enrich(doc_for("556d", "gleicher Text"), law_source(domain_map=[RENT_CAP]), VERIFIED).chunks[0]
    b = enrich(doc_for("557", "gleicher Text"), law_source(), VERIFIED).chunks[0]
    kept, dropped = deduplicate([a, b])
    assert dropped == 1 and kept == [a]
