"""ai.rag.retriever — 벡터 검색 (Chroma + KURE-v1 Dense Retrieval).

    from ai.rag.retriever import retrieve

    hits = retrieve(question, top_k=5, document_id=selected_document_id)

Chroma 컬렉션과 embedder는 첫 호출 때 한 번만 로드되어 모듈 전역에 캐시된다
(ai.rag.chain.load_model() 과 동일한 패턴). 색인은 미리
`python -m ai.scripts.build_index` 로 구축돼 있어야 한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import chromadb

from ai.embeddings.embedder import KureEmbedder

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]  # ai/

COLLECTION_NAME = os.environ.get("AI_RETRIEVER_COLLECTION", "rfp_chunks")
PERSIST_DIR = os.environ.get(
    "AI_RETRIEVER_PERSIST_DIR", str(_PACKAGE_ROOT / "data" / "vector_store")
)
EMBEDDER_DEVICE = os.environ.get("AI_RETRIEVER_DEVICE", "cuda")

DEFAULT_TOP_K = 5

# ---------------------------------------------------------------------------
# 컬렉션 / embedder 전역 캐시 — 첫 호출 때만 로드한다
# ---------------------------------------------------------------------------

_collection: Any | None = None
_embedder: Any | None = None


def load_retriever() -> None:
    """Chroma 컬렉션과 embedder를 로드한다. 이미 로드돼 있으면 아무것도 안 한다.

    retrieve()가 첫 호출 때 자동으로 부르므로 직접 부를 필요는 없다.
    backend 기동 시 첫 요청 지연을 없애고 싶을 때만 미리 호출한다.
    """
    global _collection, _embedder
    if _collection is not None:
        return
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    _collection = client.get_collection(COLLECTION_NAME)
    _embedder = KureEmbedder(device=EMBEDDER_DEVICE)


def is_retriever_loaded() -> bool:
    return _collection is not None


def retrieve(question: str, top_k: int = DEFAULT_TOP_K, *, document_id: str) -> list[dict]:
    """P0 Selected-document scope: document_id는 필수이며 Hard Filter로 적용된다.
    (Similarity Score보다 우선 — 다른 문서 결과가 섞이면 RETRIEVAL_SCOPE_ERROR)

    Returns
    -------
    list[dict]
        각 dict는 {"chunk_id", "document_id", "score", "text", "section_path",
        "requirement_ids"} 를 가진다 (ai.rag.chain.generate_answer 의 hits 입력 계약).
    """
    if not document_id:
        raise ValueError("document_id is required (Selected-document scope, P0)")

    if _collection is None:
        load_retriever()

    q_vector = _embedder.embed_query(question)

    results = _collection.query(
        query_embeddings=[q_vector],
        n_results=top_k,
        where={"document_id": document_id},
    )

    hits = []
    for i, chunk_id in enumerate(results["ids"][0]):
        metadata = results["metadatas"][0][i]
        assert metadata["document_id"] == document_id, "RETRIEVAL_SCOPE_ERROR"
        hits.append(
            {
                "chunk_id": chunk_id,
                "document_id": metadata["document_id"],
                "score": 1 - results["distances"][0][i],  # cosine distance -> similarity
                "text": results["documents"][0][i],
                "section_path": json.loads(metadata.get("section_path", "[]")),
                "requirement_ids": json.loads(metadata.get("requirement_ids", "[]")),
            }
        )
    return hits
