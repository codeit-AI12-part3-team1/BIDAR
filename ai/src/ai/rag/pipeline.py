"""ai.rag.pipeline - 검색 + 생성을 한 번에 도는 진입점.

backend 는 이 모듈 하나만 쓰면 된다.

    from ai.rag.pipeline import answer_question, load_all

    load_all()                       # 서버 기동 시 1회 (선택)
    result = answer_question(
        "사업 기간이 언제인가요?",
        document_id="DOC_001",
        history=[{"role": "user", "content": "..."},
                 {"role": "assistant", "content": "..."}],
    )
    # -> {"answer", "sources", "abstained", "hits", "document_id"}

내부적으로는 `ai.rag.retriever.retrieve()` 로 검색한 뒤 그 결과를
`ai.rag.chain.generate_answer()` 에 그대로 넘긴다. 두 함수는 그대로 남아 있으므로
검색 결과를 직접 다뤄야 하면 개별로 호출해도 된다.

주의 - 이 함수는 답변을 전부 만든 뒤 한 번에 돌려준다. 토큰 단위 스트리밍은 아직 없다.
"""

from __future__ import annotations

from ai.rag import chain as _chain
from ai.rag import retriever as _retriever

DEFAULT_TOP_K = _retriever.DEFAULT_TOP_K


def load_all(*, retriever: bool = True, model: bool = True) -> None:
    """Chroma 색인 + 임베더 + 생성 모델을 미리 로드한다.

    첫 요청 지연을 없애려면 서버 기동 시 한 번 부른다. 부르지 않아도
    answer_question() 이 첫 호출 때 알아서 로드한다.
    """
    if retriever:
        _retriever.load_retriever()
    if model:
        _chain.load_model()


def is_ready() -> bool:
    """검색·생성 양쪽이 로드돼 있으면 True."""
    return _retriever.is_retriever_loaded() and _chain.is_model_loaded()


def answer_question(
    question: str,
    *,
    document_id: str,
    history: list[dict] | None = None,
    top_k: int = DEFAULT_TOP_K,
    enable_thinking: bool = _chain.DEFAULT_ENABLE_THINKING,
    temperature: float = _chain.DEFAULT_TEMPERATURE,
    top_p: float = _chain.DEFAULT_TOP_P,
    max_tokens: int = _chain.DEFAULT_MAX_TOKENS,
    max_history_turns: int = _chain.DEFAULT_MAX_HISTORY_TURNS,
    max_history_chars: int = _chain.DEFAULT_MAX_HISTORY_CHARS,
) -> dict:
    """질문 1건을 받아 검색 -> 생성까지 하고 답변 1건을 돌려준다.

    Parameters
    ----------
    question : str
        사용자 질문.
    document_id : str
        대상 문서 ID. 필수이며 검색에 Hard Filter 로 적용된다
        (P0 Selected-document scope). 빈 값이면 ValueError.
    history : list[dict], optional
        직전 대화. `[{"role": "user"|"assistant", "content": str}, ...]`.
        None 이면 단발 질문으로 처리한다. 최근 몇 턴만 쓰는지는
        max_history_turns / max_history_chars 가 정한다.
    top_k : int
        검색해서 생성기에 넘길 청크 수. 기본 5.

    Returns
    -------
    dict
        {
          "answer":      str,          # 생성된 답변
          "sources":     list,         # 근거 chunk_id 목록
          "abstained":   bool,         # 답변 거절 여부
          "hits":        list[dict],   # 검색 결과 원본 (rank/chunk_id/score/text/...)
          "document_id": str,
        }

        "answer" / "sources" / "abstained" 는 chain.generate_answer() 의 반환을
        그대로 옮긴 것이다. "hits" 는 로그·디버깅용으로 덧붙였다.
    """
    if not question or not question.strip():
        raise ValueError("question is required")
    if not document_id:
        raise ValueError("document_id is required (Selected-document scope, P0)")

    hits = _retriever.retrieve(question, top_k=top_k, document_id=document_id)

    result = _chain.generate_answer(
        question,
        hits,
        document_id=document_id,
        top_k=top_k,
        enable_thinking=enable_thinking,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        history=history,
        max_history_turns=max_history_turns,
        max_history_chars=max_history_chars,
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "abstained": result["abstained"],
        "hits": hits,
        "document_id": document_id,
    }
