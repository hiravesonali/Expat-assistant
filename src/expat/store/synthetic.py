"""A tiny hand-written corpus for offline tests and smoke runs (no ingestion, no API key needed).

Each record is chosen to exercise one retrieval behaviour:
* two Absätze of § 573c BGB share one parent           -> parent dedupe
* "Kündigungsfrist" (singular) only in § 573c Abs. 2   -> German stemming in BM25
* a Munich and a Berlin Anmeldung procedure             -> city hard filter
* an expired Bavarian regulation                        -> validity hard filter
* a Kindergeld FAQ for families                         -> audience soft boost
"""

from __future__ import annotations

import hashlib
from datetime import date

from expat.schemas import ChunkMetadata, ChunkRecord, ParentRecord

VERIFIED = date(2026, 11, 18)


def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def make_chunk(
    *,
    doc_key: str,
    idx: int,
    text: str,
    header: str,
    parent_id: str | None = None,
    doc_version: str = "v1",
    **meta: object,
) -> ChunkRecord:
    """Build a valid ChunkRecord with deterministic ids, mirroring what ingestion produces."""
    source_id = doc_key.split("#")[0]
    defaults: dict[str, object] = {
        "domain": "tenancy",
        "source_type": "law",
        "source_name": "Gesetze im Internet",
        "source_url": f"https://example.org/{doc_key}",
        "title": doc_key,
        "language": "de",
        "jurisdiction": "federal",
        "last_verified": VERIFIED,
    }
    defaults.update(meta)
    metadata = ChunkMetadata(
        chunk_id=_sha(f"{source_id}|{doc_key}|{idx}"),
        parent_id=parent_id or doc_key,
        doc_id=_sha(source_id),
        doc_key=doc_key,
        doc_version=doc_version,
        content_hash=_sha(text, 40),
        source_id=source_id,
        **defaults,  # type: ignore[arg-type]
    )
    return ChunkRecord(text=text, embed_text=f"{header} {text}", metadata=metadata)


def synthetic_chunks() -> list[ChunkRecord]:
    return [
        make_chunk(
            doc_key="bgb#573c",
            idx=0,
            header="[BGB › § 573c Kündigungsfristen › Abs. 1] [tenancy]",
            text=(
                "(1) Die Kündigung ist spätestens am dritten Werktag eines Kalendermonats zum Ablauf "
                "des übernächsten Monats zulässig."
            ),
            legal_reference="§ 573c Abs. 1 BGB",
            title="§ 573c Kündigungsfristen",
        ),
        make_chunk(
            doc_key="bgb#573c",
            idx=1,
            header="[BGB › § 573c › Abs. 2] [tenancy]",
            text="(2) Bei Wohnraum zu nur vorübergehendem Gebrauch kann eine kürzere Kündigungsfrist vereinbart werden.",  # noqa: E501
            legal_reference="§ 573c Abs. 2 BGB",
            title="§ 573c Kündigungsfristen",
        ),
        make_chunk(
            doc_key="bgb#573",
            idx=0,
            header="[BGB › § 573 Ordentliche Kündigung des Vermieters] [tenancy]",
            text="Der Vermieter kann nur kündigen, wenn er ein berechtigtes Interesse hat, etwa Eigenbedarf.",
            legal_reference="§ 573 Abs. 1 BGB",
            title="§ 573 Ordentliche Kündigung des Vermieters",
        ),
        make_chunk(
            doc_key="muc-anmeldung#documents",
            idx=0,
            header="[Wohnsitz anmelden › Unterlagen] [bureaucracy]",
            text="Für die Anmeldung benötigen Sie Ihren Reisepass und die Wohnungsgeberbestätigung des Vermieters.",
            parent_id="muc-anmeldung",
            domain="bureaucracy",
            source_type="procedure",
            section_kind="documents",
            source_name="Landeshauptstadt München",
            title="Wohnsitz anmelden",
            jurisdiction="city",
            state="BY",
            city="munich",
        ),
        make_chunk(
            doc_key="ber-anmeldung#documents",
            idx=0,
            header="[Anmeldung einer Wohnung › Unterlagen] [bureaucracy]",
            text="Für die Anmeldung in Berlin benötigen Sie Ihren Reisepass und die Wohnungsgeberbestätigung.",
            parent_id="ber-anmeldung",
            domain="bureaucracy",
            source_type="procedure",
            section_kind="documents",
            source_name="Berlin.de",
            title="Anmeldung einer Wohnung",
            jurisdiction="city",
            state="BE",
            city="berlin",
        ),
        make_chunk(
            doc_key="fp-kindergeld#faq-hoehe",
            idx=0,
            header="[Kindergeld › FAQ] [family]",
            text="Wie hoch ist das Kindergeld? Das Kindergeld beträgt 259 Euro pro Monat für jedes Kind.",
            domain="family",
            source_type="faq",
            source_name="Familienportal",
            title="Kindergeld FAQ",
            language="de",
            applies_to=["family"],
        ),
        make_chunk(
            doc_key="by-mieterschutzv#1",
            idx=0,
            header="[Mieterschutzverordnung Bayern › § 1] [tenancy]",
            text="Die Gemeinde München ist ein Gebiet mit angespanntem Wohnungsmarkt (alte Fassung).",
            source_type="regulation",
            source_name="Verkündungsplattform Bayern",
            jurisdiction="state",
            state="BY",
            valid_from=date(2020, 1, 1),
            valid_until=date(2025, 12, 31),
        ),
    ]


def synthetic_parents() -> list[ParentRecord]:
    def parent(parent_id: str, text: str, title: str, language: str = "de") -> ParentRecord:
        return ParentRecord(
            parent_id=parent_id,
            doc_key=parent_id,
            text=text,
            title=title,
            source_url=f"https://example.org/{parent_id}",
            source_name="synthetic",
            language=language,
            last_verified=VERIFIED,
            token_count=len(text) // 4,
        )

    chunks = synthetic_chunks()
    by_parent: dict[str, list[str]] = {}
    for c in chunks:
        by_parent.setdefault(c.metadata.parent_id, []).append(c.text)
    return [parent(pid, "\n".join(texts), title=pid) for pid, texts in by_parent.items()]
