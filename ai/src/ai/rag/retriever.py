"""ai.rag.retriever - 벡터 검색 (Chroma + KURE-v1 Dense Retrieval).

    from ai.rag.retriever import retrieve

    hits = retrieve(question, top_k=5, document_id=selected_document_id)

Chroma 컬렉션과 embedder는 첫 호출 때 한 번만 로드되어 모듈 전역에 캐시된다
(ai.rag.chain.load_model() 과 동일한 패턴). 색인은 미리
`python -m ai.scripts.build_index` 로 구축돼 있어야 한다.

색인 경로에 ASCII 밖 문자(한글 등)가 있으면 chromadb 가 HNSW 색인을 못 연다.
load_retriever() 가 그 경우를 먼저 걸러 에러 메시지로 알린다 (2026-09-01 실측).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import chromadb

from ai.embeddings.embedder import KureEmbedder
from ai.ingestion.indexer import DEFAULT_COLLECTION, assert_index_path_ok
from ai.rag.sparse import build_from_collection, reciprocal_rank_fusion

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]  # ai/

COLLECTION_NAME = os.environ.get("AI_RETRIEVER_COLLECTION", DEFAULT_COLLECTION)
PERSIST_DIR = os.environ.get(
    "AI_RETRIEVER_PERSIST_DIR", str(_PACKAGE_ROOT / "data" / "vector_store")
)
EMBEDDER_DEVICE = os.environ.get("AI_RETRIEVER_DEVICE", "cuda")

DEFAULT_TOP_K = 5

# BM25 를 섞을지 여부. 기본은 끔.
#
# 조건형 질문을 살리려고 넣었는데, Gold 14문항으로 가중치 5종 x 후보폭 3종 = 16조합을
# 훑은 결과 dense 단독을 이기는 조합이 하나도 없었다(2026-09-08 실측).
#   dense 단독      Hit@5 1.000 / nDCG@5 0.855 / MRR 0.821
#   최선의 하이브리드  Hit@5 1.000 / nDCG@5 0.855 / MRR 0.821  (sparse 가중 0.1 = 사실상 무효)
#   1:1 로 합치면     Hit@5 0.929 / nDCG@5 0.790 / MRR 0.717
# 정작 목표였던 조건형 4문항은 순위가 전혀 안 움직였고, "사업"·"기간" 처럼 흔한 낱말이
# 많은 상용구 청크가 위로 올라와 멀쩡하던 질문 2개를 밀어냈다.
#
# 다만 이 Gold 는 14문항뿐이고 dense 가 이미 Hit@5 1.000 으로 천장을 쳐서 개선을
# 보여줄 여지 자체가 없다. 코드는 살려두고 기본만 끈다. 더 큰 벤치마크
# (StandardDataset/rag_benchmark.jsonl 980질의)로 다시 재볼 것.
HYBRID = os.environ.get("AI_RETRIEVER_HYBRID", "0").strip().lower() not in ("0", "false", "no")
# RRF 상수. 클수록 상위권 쏠림이 완화된다. 60이 관례값.
RRF_K = int(os.environ.get("AI_RETRIEVER_RRF_K", "60"))
# dense 를 1.0 으로 두고 BM25 쪽에 줄 상대 가중치.
SPARSE_WEIGHT = float(os.environ.get("AI_RETRIEVER_SPARSE_WEIGHT", "0.3"))
# 두 축에서 각각 몇 건을 후보로 뽑아 합칠지. top_k 의 배수.
# 좁게 뽑으면 한쪽에만 잡힌 정답이 합치기 전에 잘려나간다.
CANDIDATE_FANOUT = int(os.environ.get("AI_RETRIEVER_FANOUT", "8"))

# ---------------------------------------------------------------------------
# 컬렉션 / embedder 전역 캐시 - 첫 호출 때만 로드한다
# ---------------------------------------------------------------------------

_collection: Any | None = None
_embedder: Any | None = None
_sparse: Any | None = None  # BM25 색인 (HYBRID 가 꺼져 있으면 None 으로 남는다)


def load_retriever() -> None:
    """Chroma 컬렉션과 embedder를 로드한다. 이미 로드돼 있으면 아무것도 안 한다.

    retrieve()가 첫 호출 때 자동으로 부르므로 직접 부를 필요는 없다.
    backend 기동 시 첫 요청 지연을 없애고 싶을 때만 미리 호출한다.
    """
    global _collection, _embedder, _sparse
    if _collection is not None:
        return
    assert_index_path_ok(PERSIST_DIR)
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    # get_collection 은 sqlite 만 읽으므로 여기서 성공해도 색인이 온전하다는 뜻은 아니다.
    # count() 가 HNSW 를 실제로 연다. 기동 시점에 한 번 확인해 둔다.
    collection.count()
    _collection = collection
    _embedder = KureEmbedder(device=EMBEDDER_DEVICE)

    if HYBRID:
        # 저장된 색인을 읽어 BM25 를 새로 만든다. 파일로 갖고 있지 않으므로
        # Chroma 색인과 어긋날 수가 없다. 대신 기동 시간이 늘어난다.
        _sparse = build_from_collection(collection)


def is_retriever_loaded() -> bool:
    return _collection is not None


def retrieve(question: str, top_k: int = DEFAULT_TOP_K, *, document_id: str) -> list[dict]:
    """P0 Selected-document scope: document_id는 필수이며 Hard Filter로 적용된다.
    (Similarity Score보다 우선 - 다른 문서 결과가 섞이면 RETRIEVAL_SCOPE_ERROR)

    Returns
    -------
    list[dict]
        각 dict는 {"rank", "chunk_id", "document_id", "score", "text", "section_path",
        "requirement_ids", "block_ids"} 를 가진다
        (ai.rag.chain.generate_answer 의 hits 입력 계약).

        `rank` 는 DATA_CONTRACT_v0.1_FROZEN.md 5절(Retrieval -> Generation)에 명시된
        필수 필드다. `block_ids` 는 같은 문서 6절(Generation Output)의
        `sources[].block_ids` 를 채우는 유일한 출처이고, RETRIEVAL_HANDOFF 3.5절의
        "엉뚱한 Section 검색 탐지"(검색 품질 진단)에도 쓰인다.
    """
    if not document_id:
        raise ValueError("document_id is required (Selected-document scope, P0)")

    if _collection is None:
        load_retriever()

    q_vector = _embedder.embed_query(question)

    # 합칠 거라면 두 축에서 각각 넉넉히 뽑는다. top_k 만큼만 뽑으면 한쪽에만
    # 잡힌 정답이 합치기 전에 잘려 RRF 가 의미를 잃는다.
    n_candidates = top_k * CANDIDATE_FANOUT if _sparse is not None else top_k

    results = _collection.query(
        query_embeddings=[q_vector],
        n_results=n_candidates,
        where={"document_id": document_id},  # P0 하드 필터
    )

    dense_ids: list[str] = results["ids"][0]
    records = {
        chunk_id: (
            results["metadatas"][0][i],
            results["documents"][0][i],
            1 - results["distances"][0][i],  # cosine distance -> similarity
        )
        for i, chunk_id in enumerate(dense_ids)
    }

    if _sparse is None:
        ordered = dense_ids[:top_k]
    else:
        # BM25 도 같은 문서 안에서만 찾는다. sparse 축으로 스코프가 새면 안 된다.
        sparse_ids = _sparse.search(question, document_id, n_candidates)
        ordered = reciprocal_rank_fusion(
            [dense_ids, sparse_ids], k=RRF_K, weights=[1.0, SPARSE_WEIGHT]
        )[:top_k]
        _load_records(ordered, records, q_vector)

    hits = []
    for rank, chunk_id in enumerate(ordered, start=1):
        metadata, text, score = records[chunk_id]
        if metadata["document_id"] != document_id:
            # assert는 `python -O` 실행 시 통째로 사라지므로, P0 하드 필터의
            # 유일한 방어선을 assert에만 맡기지 않는다.
            raise RuntimeError(
                f"RETRIEVAL_SCOPE_ERROR: expected {document_id}, got {metadata['document_id']}"
            )
        hits.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "document_id": metadata["document_id"],
                "score": score,
                "text": text,
                "section_path": json.loads(metadata.get("section_path", "[]")),
                "requirement_ids": json.loads(metadata.get("requirement_ids", "[]")),
                "block_ids": json.loads(metadata.get("block_ids", "[]")),
            }
        )
    return hits


def _load_records(chunk_ids: list[str], records: dict, q_vector) -> None:
    """BM25 에만 잡힌 청크는 dense 질의 결과에 없다. 그것만 따로 읽어 채운다."""
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in records]
    if not missing:
        return

    fetched = _collection.get(ids=missing, include=["documents", "metadatas", "embeddings"])
    for i, chunk_id in enumerate(fetched["ids"]):
        # 색인·질의 벡터가 모두 정규화돼 있으므로 내적이 곧 코사인 유사도다.
        # dense 로 잡힌 청크의 score 와 같은 척도를 유지하기 위해 직접 계산한다.
        similarity = sum(a * b for a, b in zip(q_vector, fetched["embeddings"][i]))
        records[chunk_id] = (fetched["metadatas"][i], fetched["documents"][i], similarity)
