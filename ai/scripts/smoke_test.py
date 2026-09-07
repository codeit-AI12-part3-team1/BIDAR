"""ai/scripts/smoke_test.py — retrieve() -> generate_answer() 전체 파이프라인을
질문 1개로 실제 실행해보는 최소 테스트.

    python ai/scripts/smoke_test.py
"""

from __future__ import annotations

from ai.rag.retriever import retrieve

QUESTION = "이 사업의 소요예산은 얼마인가?"
DOCUMENT_ID = "DOC_001"


def main() -> None:
    print(f"[1/2] retrieve() 호출: question={QUESTION!r}, document_id={DOCUMENT_ID!r}")
    hits = retrieve(QUESTION, top_k=5, document_id=DOCUMENT_ID)
    print(f"  -> {len(hits)}개 hit 반환됨")
    for h in hits:
        print(f"     [{h['chunk_id']}] score={h['score']:.3f} text={h['text'][:50]!r}...")

    print("\n[2/2] generate_answer() 호출 (모델 첫 로딩 시 시간 걸림)")
    from ai.rag.chain import generate_answer  # 여기서 import (모델 로딩은 지연시킴)

    result = generate_answer(QUESTION, hits, document_id=DOCUMENT_ID)
    print("\n=== 결과 ===")
    print(result)


if __name__ == "__main__":
    main()
