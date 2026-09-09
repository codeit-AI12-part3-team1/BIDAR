"""ai/scripts/smoke_test.py — retrieve() -> generate_answer() 전체 파이프라인을
질문 1개로 실제 실행해보는 최소 테스트.

    python ai/scripts/smoke_test.py
    python ai/scripts/smoke_test.py --document-id doc_2b2a6c4e5381c1bbefca
    python ai/scripts/smoke_test.py --retrieve-only

--document-id 를 주지 않으면 기본값 DOC_001(Standard/Custom 기준)을 쓰고, 그 문서가
색인에 없으면 색인 안의 아무 문서로 대체한다. LIVE 계열은 document_id 가
content-hash(doc_<sha256[:20]>)라 사람이 외울 수 없기 때문이다.

색인에 없는 document_id 로 검색하면 예외가 아니라 **빈 결과**가 나온다. 생성기는
빈 근거로도 그냥 돌아서 "에러는 없는데 답이 엉뚱한" 상태가 된다. 그래서 이 스크립트는
대체가 일어났을 때와 hit 이 0건일 때를 눈에 띄게 알린다.
"""

from __future__ import annotations

import argparse
import sys

from ai.rag.retriever import retrieve

DEFAULT_QUESTION = "이 사업의 소요예산은 얼마인가?"
# Standard V0 / Custom(RFP100) 의 첫 문서. Gold G001~G002 가 가리키는 문서라
# 스모크 결과를 사람이 눈으로 검증하기 쉽다. LIVE 계열 색인에는 존재하지 않는다.
DEFAULT_DOCUMENT_ID = "DOC_001"


def resolve_document_id(preferred: str) -> str:
    """preferred 가 색인에 있으면 그대로, 없으면 색인 안의 아무 문서로 대체한다."""
    from ai.rag.retriever import COLLECTION_NAME, PERSIST_DIR, load_retriever
    import ai.rag.retriever as r

    load_retriever()
    if r._collection.get(where={"document_id": preferred}, limit=1, include=[])["ids"]:
        return preferred

    sample = r._collection.get(limit=1, include=["metadatas"])
    metadatas = sample.get("metadatas") or []
    if not metadatas:
        raise SystemExit(
            f"색인이 비어 있다: {PERSIST_DIR} / {COLLECTION_NAME}\n"
            f"  먼저 build_index.py 로 색인을 만들어라."
        )
    fallback = metadatas[0]["document_id"]
    print(f"!! {preferred!r} 가 이 색인에 없다 -> {fallback!r} 로 대체한다.")
    print(f"   ({PERSIST_DIR} / {COLLECTION_NAME} 는 다른 document_id 체계를 쓴다)\n")
    return fallback


def main() -> None:
    ap = argparse.ArgumentParser(description="검색기 + 생성기 최소 스모크 테스트")
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID,
                    help=f"기본 {DEFAULT_DOCUMENT_ID} (Standard/Custom 기준). "
                         f"색인에 없으면 그 색인의 아무 문서로 대체한다")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--retrieve-only", action="store_true",
                    help="generate_answer() 를 건너뛴다 (GPU/gptqmodel 없이 검색만 확인)")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    document_id = resolve_document_id(args.document_id)

    print(f"[1/2] retrieve() 호출: question={args.question!r}, document_id={document_id!r}")
    hits = retrieve(args.question, top_k=args.top_k, document_id=document_id)
    print(f"  -> {len(hits)}개 hit 반환됨")
    if not hits:
        # 예외가 아니라 빈 결과다. 생성기는 이 상태로도 돌아가므로 여기서 끊는다.
        raise SystemExit(
            f"\n검색 결과가 0건이다. document_id={document_id!r} 가 이 색인에 없거나"
            f" 해당 문서에 청크가 없다.\n"
            f"  이대로 generate_answer() 에 넘기면 근거 없이 답을 만들어낸다."
        )
    for h in hits:
        section = " > ".join(h["section_path"]) or "-"
        print(f"     [{h['chunk_id']}] score={h['score']:.3f} section={section[:40]!r}")
        print(f"       {h['text'][:70]!r}...")

    if args.retrieve_only:
        print("\n[2/2] --retrieve-only 이므로 생성기는 건너뛴다")
        return

    print("\n[2/2] generate_answer() 호출 (모델 첫 로딩 시 시간 걸림)")
    from ai.rag.chain import generate_answer  # 여기서 import (모델 로딩은 지연시킴)

    result = generate_answer(args.question, hits, document_id=document_id)
    print("\n=== 결과 ===")
    print(result)


if __name__ == "__main__":
    main()
