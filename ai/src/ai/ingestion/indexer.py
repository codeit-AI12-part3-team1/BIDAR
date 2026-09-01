"""ai.ingestion.indexer - C0 청크 임베딩 + Chroma 색인 구축.

C0 Chunk(JSONL)를 읽어 embedder로 임베딩하고 Chroma PersistentClient에 색인한다.
C0는 재청킹하지 않고 그대로 사용한다 (DATA_CONTRACT_v0.1_FROZEN.md).

색인 경로 제약 - 실측(2026-09-01) 기준:

  * 경로에 ASCII 밖 문자(한글 등)가 있으면 chromadb 1.5.9 가 HNSW 색인(.bin)을
    열지 못한다. `get_collection()` 은 sqlite 를 읽으므로 성공하고,
    `count()` / `query()` 에서 "Error loading hnsw index" 로 죽는다.
    -> assert_index_path_ok() 로 색인을 만들기 전에 막는다.
  * `hnsw:sync_threshold` 를 지정하지 않으면 flush 가 늦어 `.bin` 이 아예 안 만들어진
    상태로 끝날 수 있다. 그 경우 벡터는 embeddings_queue 에 남은 것 외에는 소실된다.
    -> DEFAULT_SYNC_THRESHOLD 를 명시한다.
  * 같은 프로세스 안에서 다시 열면 Chroma 가 메모리에 든 인덱스를 재사용하므로
    색인이 디스크에 남았는지 판정할 수 없다. 판정은 반드시 별도 프로세스에서 한다
    (`ai/scripts/build_index.py` 가 그렇게 확인한다).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import chromadb

from ai.ingestion.loaders import build_document_lookup, load_jsonl

DEFAULT_COLLECTION = "rfp_chunks"
DEFAULT_BATCH_SIZE = 256
DEFAULT_SYNC_THRESHOLD = 100

# Chroma metadata 값은 str/int/float/bool만 허용 (list, None 불가) -> list는 JSON 문자열로 직렬화.
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


def non_ascii_part(path) -> str | None:
    """경로에 ASCII 밖 문자가 있으면 그 문자들을 돌려준다. 없으면 None."""
    bad = sorted({ch for ch in str(path) if ord(ch) > 127})
    return "".join(bad) if bad else None


def assert_index_path_ok(persist_dir) -> None:
    """색인 경로에 ASCII 밖 문자가 있으면 즉시 막는다."""
    bad = non_ascii_part(persist_dir)
    if bad:
        raise ValueError(
            f"색인 경로에 ASCII 밖 문자가 있다: {bad!r}\n"
            f"  경로: {persist_dir}\n"
            f"  chromadb 는 이런 경로의 HNSW 색인(.bin)을 열지 못한다"
            f" (Error loading hnsw index).\n"
            f"  색인은 ASCII 경로에 두어라. 예: C:\\bidar\\vector_store , /srv/bidar/vector_store"
        )


def chunk_to_metadata(chunk: dict, document_lookup: dict) -> dict:
    metadata: dict = {}
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
    budget = doc.get("budget_amount")
    # 예산이 0 인 문서를 -1(미상)로 바꾸지 않는다. None 일 때만 -1.
    metadata["budget_amount"] = -1 if budget is None else budget
    metadata["budget_status"] = doc.get("budget_status", "")
    return metadata


def build_index(
    chunks_path: str,
    embedder,
    documents_path: str | None = None,
    collection_name: str = DEFAULT_COLLECTION,
    persist_dir: str = "data/vector_store",
    batch_size: int = DEFAULT_BATCH_SIZE,
    sync_threshold: int = DEFAULT_SYNC_THRESHOLD,
    fresh: bool = True,
    progress: bool = True,
):
    """C0 청크를 색인한다.

    Parameters
    ----------
    fresh : bool
        True 면 persist_dir 를 통째로 비우고 시작한다. Chroma 는
        delete_collection -> create_collection 시 새 UUID 폴더를 만들기 때문에,
        비우지 않으면 옛 세그먼트 폴더가 남아 어느 쪽이 현재 색인인지 알 수 없다.
    sync_threshold : int
        HNSW 를 디스크로 내리는 임계치. 0 이면 지정하지 않는다(Chroma 기본값).
    """
    assert_index_path_ok(persist_dir)

    chunks = load_jsonl(chunks_path)
    document_lookup = build_document_lookup(documents_path) if documents_path else {}

    persist = Path(persist_dir)
    if fresh and persist.exists():
        shutil.rmtree(persist)
    persist.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    # cosine 거리로 명시 (KURE-v1/text-embedding-3-small 모두 normalize된 임베딩 기준)
    metadata = {"hnsw:space": "cosine"}
    if sync_threshold:
        metadata["hnsw:sync_threshold"] = sync_threshold
    try:
        collection = client.create_collection(collection_name, metadata=metadata)
    except Exception:
        # 이 chromadb 빌드가 sync_threshold 를 안 받으면 공간 설정만으로 만든다.
        collection = client.create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

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
        if progress:
            print(f"  {min(i + batch_size, len(chunks))}/{len(chunks)} 청크 인덱싱")

    return collection
