"""ai/scripts/verify_index_full_query.py — 색인된 청크가 실제로 "검색되는지" 전수 검증.

chromadb 는 데이터를 두 군데에 나눠 둔다.

  * `chroma.sqlite3`  : 청크 원본(텍스트/메타데이터/벡터)
  * `.bin` (HNSW)     : 검색용 그래프

SQLite 에 다 들어있어도 HNSW 그래프에 반영이 덜 되면 그 청크는 검색에서 빠진다.
`collection.count()` 나 `collection.get()` 은 SQLite 만 읽으므로 이 상태를 못 잡고,
`ai/scripts/verify_index.py` 는 색인이 "열리는지"까지만 본다.

이 스크립트는 저장된 벡터를 그대로 꺼내(재임베딩 없음) 자기 자신으로 `query()` 해서,
전체 청크가 실제로 검색되는지 확인한다. 위 두 검증이 못 잡는 부분을 담당한다.

    python ai/scripts/verify_index_full_query.py --persist-dir C:/bidar/vector_store

검색 범위는 프로덕션 `ai.rag.retriever.retrieve()` 와 동일하게 `document_id` 로
제한한다. 전체 컬렉션에서 찾으면, 내용이 완전히 동일한 다른 문서의 청크가 1위로
잡혀 멀쩡한 청크를 "누락"으로 오판한다 (실측 2026-09-02: DOC_046↔DOC_057,
DOC_058↔DOC_062 가 청크 텍스트까지 100% 동일해 126건이 오탐으로 보고됨).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ai/
DATA_DIR = PROJECT_ROOT / "data"

# 같은 벡터로 검색했을 때 이 거리 안이면 "내용이 동일한 청크"로 본다.
# 색인에서 진짜 빠진 청크라면 내용이 다른 청크가 잡히므로 거리가 유의미하게 커진다.
IDENTICAL_DIST = 1e-6


def verify(collection, query_batch_size: int = 200) -> bool:
    print(f"collection.count() : {collection.count()}  (SQLite 레코드 수)")

    # 저장된 id + 임베딩 + 메타데이터를 그대로 꺼냄 (재임베딩 없음, 빠름)
    data = collection.get(include=["embeddings", "metadatas"])
    all_ids = data["ids"]
    all_vectors = data["embeddings"]
    all_metadatas = data["metadatas"]
    print(f"실제로 꺼내온 레코드 수 : {len(all_ids)}")

    # document_id 별로 묶는다 — chromadb 의 where 는 배치 전체에 공통 적용되므로
    # 문서 단위로 나눠서 질의해야 한다.
    by_document: dict[str, list[int]] = defaultdict(list)
    for i, metadata in enumerate(all_metadatas):
        by_document[metadata["document_id"]].append(i)
    print(f"문서 수 : {len(by_document)}")
    print()

    missing: list[str] = []
    done = 0

    for doc_id, indices in by_document.items():
        for start in range(0, len(indices), query_batch_size):
            index_batch = indices[start : start + query_batch_size]

            results = collection.query(
                query_embeddings=[all_vectors[i] for i in index_batch],
                n_results=1,
                where={"document_id": doc_id},  # retrieve() 의 P0 하드 필터와 동일
            )

            for j, i in enumerate(index_batch):
                expected_id = all_ids[i]
                found_ids = results["ids"][j]
                if not found_ids:
                    missing.append(expected_id)
                    continue

                found_id = found_ids[0]
                distance = results["distances"][j][0]

                # 내용이 완전히 동일한 청크가 대신 1위로 잡히는 경우가 있다
                # (한 문서 안에 같은 문구가 반복될 때). 색인은 정상이므로 통과시킨다.
                if found_id != expected_id and distance >= IDENTICAL_DIST:
                    missing.append(expected_id)

            done += len(index_batch)
            print(f"  검증 중... {done}/{len(all_ids)}")

    print()
    if missing:
        print(f"FAIL  {len(missing)}개 청크가 검색 그래프에 반영 안 됨")
        print(f"      누락 예시 (최대 10개): {missing[:10]}")
    else:
        print(f"PASS  전체 {len(all_ids)}개 청크 전부 정상 검색됨. 색인 완전합니다.")

    return not missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="색인된 청크가 실제로 검색되는지 전수 검증 (재임베딩 없음)"
    )
    parser.add_argument("--persist-dir", default=str(DATA_DIR / "vector_store"))
    parser.add_argument("--collection", default="rfp_chunks")
    args = parser.parse_args()

    # 파일로 리다이렉트하거나 cp949 콘솔에서 돌리면 한글 출력이 UnicodeEncodeError 로
    # 죽는다. 검증을 다 끝내고 결과를 찍는 순간 터지므로 미리 막아둔다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    client = chromadb.PersistentClient(path=args.persist_dir)
    collection = client.get_collection(args.collection)

    raise SystemExit(0 if verify(collection) else 1)


if __name__ == "__main__":
    main()
