"""ai.ingestion.indexer — 임베딩 생성 + 벡터 색인 구축 (Chroma).

C0 Chunk(JSONL)를 읽어 embedder로 임베딩하고 Chroma PersistentClient에
색인한다. C0는 재청킹하지 않고 그대로 사용한다 (docs/RETRIEVAL_HANDOFF_v0.1.md 3.1).
"""

from __future__ import annotations

import json

import chromadb

from ai.ingestion.loaders import build_document_lookup, load_jsonl

# Chroma metadata 값은 str/int/float/bool만 허용 (list, None 불가) -> list는 JSON 문자열로 직렬화.
# 필드 목록은 docs/DATA_CONTRACT_v0.1_FROZEN.md 의 C0 Chunk 스키마 기준.
LIST_FIELDS = ("section_path", "block_ids", "requirement_ids")
METADATA_FIELDS = (
    "document_id",
    "split",
    "chunk_index",
    "section_path",
    "block_ids",
    "requirement_ids",
    "char_start",
    "char_end",
    "page_start",
    "page_end",
    "chunking_version",
    "source_text_version",
)


def chunk_to_metadata(chunk: dict, document_lookup: dict) -> dict:
    metadata = {}
    for field in METADATA_FIELDS:
        value = chunk.get(field)
        if field in LIST_FIELDS:
            value = json.dumps(value or [], ensure_ascii=False)
        elif value is None:
            value = ""
        metadata[field] = value

    doc = document_lookup.get(chunk["document_id"], {})
    metadata["title"] = doc.get("title", "")
    metadata["agency"] = doc.get("agency", "")
    metadata["budget_amount"] = doc.get("budget_amount") or -1
    metadata["budget_status"] = doc.get("budget_status", "")
    return metadata


def build_index(
    chunks_path: str,
    embedder,
    documents_path: str | None = None,
    collection_name: str = "rfp_chunks",
    persist_dir: str = "data/vector_store",
    batch_size: int = 64,
):
    chunks = load_jsonl(chunks_path)
    document_lookup = build_document_lookup(documents_path) if documents_path else {}

    client = chromadb.PersistentClient(path=persist_dir)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    # cosine 거리로 명시 (KURE-v1/text-embedding-3-small 모두 normalize된 임베딩 기준 유사도 비교)
    collection = client.create_collection(collection_name, metadata={"hnsw:space": "cosine"})

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        vectors = embedder.embed_texts(texts)
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=vectors,
            documents=texts,
            metadatas=[chunk_to_metadata(c, document_lookup) for c in batch],
        )
        print(f"  {min(i + batch_size, len(chunks))}/{len(chunks)} 청크 인덱싱 완료")

    return collection
