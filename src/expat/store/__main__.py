"""CLI: `uv run python -m expat.store [--collection-model <slug>] [--rebuild]`.

Examples:
    uv run python -m expat.store                                  # index with EMBEDDING_MODEL
    uv run python -m expat.store --collection-model baai/bge-m3   # bake-off: second collection
    uv run python -m expat.store --rebuild                        # drop + re-embed everything
    uv run python -m expat.store --fake-embeddings                # offline smoke run, no API key
    uv run expat-index --publish                                  # index, then upload (ADR-0010)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chromadb
from langchain_core.embeddings import DeterministicFakeEmbedding

from expat.config import get_settings
from expat.llm import EmbeddingAdapter, get_embeddings
from expat.schemas import ChunkRecord, ParentRecord
from expat.store.docstore import ParentDocstore
from expat.store.index import index_corpus, read_jsonl
from expat.store.vectorstore import ChunkVectorStore

FAKE_MODEL = "fake/deterministic-embedding"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m expat.store", description=__doc__.splitlines()[0])
    parser.add_argument("--collection-model", help="embedding model slug (default: settings.embedding_model)")
    parser.add_argument("--rebuild", action="store_true", help="delete the collection first and re-embed all")
    parser.add_argument("--embeddings-backend", choices=["openai", "httpx"], default="openai")
    parser.add_argument("--fake-embeddings", action="store_true", help="offline: deterministic hash vectors")
    parser.add_argument("--chunks", type=Path, help="default: data/processed/chunks.jsonl")
    parser.add_argument("--parents", type=Path, help="default: data/processed/parents.jsonl")
    parser.add_argument("--publish", action="store_true", help="afterwards, upload the index to INDEX_REPO")
    args = parser.parse_args(argv)

    settings = get_settings()
    model = FAKE_MODEL if args.fake_embeddings else (args.collection_model or settings.embedding_model)
    # The collection name is derived from the model, so a bake-off model gets its own collection.
    settings = settings.model_copy(update={"embedding_model": model})

    chunks_path = args.chunks or settings.processed_dir / "chunks.jsonl"
    parents_path = args.parents or settings.processed_dir / "parents.jsonl"
    for path in (chunks_path, parents_path):
        if not path.exists():
            print(f"Missing {path}. Run ingestion first.", file=sys.stderr)
            return 1

    if args.rebuild:
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        if settings.collection_name in {c.name for c in client.list_collections()}:
            client.delete_collection(settings.collection_name)

    embeddings = (
        EmbeddingAdapter(DeterministicFakeEmbedding(size=256), FAKE_MODEL)
        if args.fake_embeddings
        else get_embeddings(settings, backend=args.embeddings_backend)
    )
    summary = index_corpus(
        chunks=read_jsonl(chunks_path, ChunkRecord),
        parents=read_jsonl(parents_path, ParentRecord),
        vector_store=ChunkVectorStore(embeddings, settings=settings),
        docstore=ParentDocstore(settings.docstore_path),
        bm25_dir=settings.bm25_dir,
    )
    print(summary.render())
    if args.publish:
        if args.fake_embeddings or model != get_settings().embedding_model:
            print("Refusing to publish: only the production embedding model is deployed.", file=sys.stderr)
            return 1
        from expat.store.bundle import publish_bundle

        url = publish_bundle(settings, chunks=summary.collection_count, parents=summary.docstore_count)
        print(f"Published the index to {settings.index_repo}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
