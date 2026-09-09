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

# 자기 자신 대신 다른 청크가 1위로 잡혔을 때, 그게 "동점"인지 "진짜 누락"인지 가르는 기준.
#
# 1차 기준은 본문 비교다. 본문이 글자까지 같으면 벡터도 같으므로 어느 쪽이 1위가 되든
# 무작위이고, 색인은 정상이다. 실측(2026-09-08): 본문이 동일한 청크 쌍의 거리가
# 1.0133e-6 으로 나왔다. 정규화된 float32 내적이 정확히 1.0 이 안 되어 생기는 잔차라
# 거리 임계값만으로 가르면 이런 쌍을 놓친다.
#
# 2차 기준이 거리다. 본문을 못 꺼낸 경우를 대비한 보조 장치이며, 실제로 다른 내용의
# 청크가 잡히면 거리가 0.06~0.25 수준으로 자릿수가 달라지므로 1e-4 로도 충분히 갈린다.
IDENTICAL_DIST = 1e-4


def verify(collection, query_batch_size: int = 200) -> bool:
    print(f"collection.count() : {collection.count()}  (SQLite 레코드 수)")

    # 저장된 id + 임베딩 + 메타데이터 + 본문을 그대로 꺼냄 (재임베딩 없음, 빠름)
    data = collection.get(include=["embeddings", "metadatas", "documents"])
    all_ids = data["ids"]
    all_vectors = data["embeddings"]
    all_metadatas = data["metadatas"]
    all_documents = data["documents"]
    text_of = dict(zip(all_ids, all_documents))
    print(f"실제로 꺼내온 레코드 수 : {len(all_ids)}")

    # document_id 별로 묶는다 — chromadb 의 where 는 배치 전체에 공통 적용되므로
    # 문서 단위로 나눠서 질의해야 한다.
    by_document: dict[str, list[int]] = defaultdict(list)
    for i, metadata in enumerate(all_metadatas):
        by_document[metadata["document_id"]].append(i)
    print(f"문서 수 : {len(by_document)}")
    print()

    missing: list[str] = []
    tied: list[str] = []
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
                if found_id == expected_id:
                    continue

                # 자기 자신이 아닌 청크가 1위. 본문이 같으면 동점이므로 색인은 정상이다
                # (한 문서 안에 같은 문구가 반복될 때 생긴다).
                if text_of.get(found_id) == text_of.get(expected_id):
                    tied.append(expected_id)
                    continue

                # 본문이 다른데 밀렸다면 거리로 한 번 더 본다.
                if results["distances"][j][0] < IDENTICAL_DIST:
                    tied.append(expected_id)
                    continue

                missing.append(expected_id)

            done += len(index_batch)
            print(f"  검증 중... {done}/{len(all_ids)}")

    print()
    if tied:
        # 색인 문제는 아니지만 데이터 중복 신호라 눈에 보이게 남긴다.
        print(f"참고  본문이 같은 쌍둥이 청크에 1위를 내준 건 : {len(tied)}개")
        print(f"      예시 (최대 5개): {tied[:5]}")
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
