"""ai.rag.sparse - BM25 키워드 검색 (하이브리드 검색의 sparse 축).

Dense(KURE-v1)는 의미가 비슷하면 잡지만, 질문에 박힌 특정 낱말이 본문에 그대로
있는지는 따지지 않는다. "5년 이상", "1억원 미만" 같은 조건형 질문이 약한 이유다
(Gold 조건형 4문항 중 1위 적중 1건). BM25 는 그 반대라 둘을 합친다.

토크나이저는 데이터팀 인덱스와 맞춘다 (`StandardDataset/index_config.json`:
`"bm25_tokenizer": "kiwipiepy"`). 한국어는 조사를 떼지 않으면 "예산은" 과 "예산"
이 다른 낱말이 되어 BM25 가 사실상 동작하지 않는다.

색인은 파일로 저장하지 않고 검색기가 뜰 때 Chroma 안의 본문으로 다시 만든다.
따로 저장하면 `.bin` 과 어긋난 채로 배포될 수 있고, 그 어긋남은 조용히 검색
품질만 떨어뜨려 잡기가 어렵다.
"""

from __future__ import annotations

import math
import os
from collections import Counter, defaultdict

# 검색에 의미가 있는 품사만 남긴다. 조사(J*), 어미(E*), 문장부호(SF/SP..) 는 버린다.
#   N* 명사류 / SL 외국어 / SH 한자 / SN 숫자 / XR 어근
KEEP_TAG_PREFIXES = ("N", "SL", "SH", "SN", "XR")

# BM25 표준 파라미터. k1 은 같은 낱말이 반복될 때 점수가 포화되는 속도,
# b 는 긴 문서에 주는 페널티 강도다.
K1 = 1.5
B = 0.75

_kiwi = None


def _get_kiwi():
    """Kiwi 인스턴스를 한 번만 만든다. 사용자 사전이 있으면 같이 읽는다."""
    global _kiwi
    if _kiwi is not None:
        return _kiwi

    try:
        from kiwipiepy import Kiwi
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "BM25 하이브리드 검색에는 kiwipiepy 가 필요하다.\n"
            "  pip install kiwipiepy\n"
            "  (끄려면 환경변수 AI_RETRIEVER_HYBRID=0)"
        ) from e

    _kiwi = Kiwi()
    user_dict = os.environ.get("AI_RETRIEVER_KIWI_DICT", "").strip()
    if user_dict and os.path.exists(user_dict):
        # 데이터팀이 만든 도메인 사전(기관명/사업명/약어). 없어도 동작한다.
        _kiwi.load_user_dictionary(user_dict)
        print(f"  Kiwi 사용자 사전 로드: {user_dict}")
    return _kiwi


def tokenize(text: str) -> list[str]:
    """문장 하나를 검색용 낱말 목록으로 만든다."""
    return [
        token.form.lower()
        for token in _get_kiwi().tokenize(text or "")
        if token.tag.startswith(KEEP_TAG_PREFIXES)
    ]


def tokenize_many(texts: list[str]) -> list[list[str]]:
    """여러 문장을 한 번에 처리한다. 한 건씩 부르는 것보다 훨씬 빠르다."""
    kiwi = _get_kiwi()
    out = []
    for tokens in kiwi.tokenize(texts):
        out.append([t.form.lower() for t in tokens if t.tag.startswith(KEEP_TAG_PREFIXES)])
    return out


class Bm25Index:
    """문서 단위로 범위를 좁혀 점수를 매기는 BM25.

    P0 Selected-document scope 때문에 후보가 항상 한 문서 안(최대 수백 건)으로
    제한된다. 그래서 전체 코퍼스를 매번 훑지 않고 후보만 계산한다.
    다만 IDF(낱말의 희소성)는 코퍼스 전체 통계로 구한다 - 한 문서 안에서만 세면
    그 문서에 흔한 낱말이 과소평가된다.
    """

    def __init__(self, chunk_ids: list[str], document_ids: list[str], texts: list[str]):
        if not (len(chunk_ids) == len(document_ids) == len(texts)):
            raise ValueError("chunk_ids / document_ids / texts 의 길이가 다르다")

        self.chunk_ids = chunk_ids
        corpus = tokenize_many(texts)

        self.term_freqs: list[Counter] = [Counter(tokens) for tokens in corpus]
        self.lengths: list[int] = [len(tokens) for tokens in corpus]
        self.n = len(corpus)
        self.avg_len = (sum(self.lengths) / self.n) if self.n else 0.0

        doc_freq: Counter = Counter()
        for tokens in corpus:
            doc_freq.update(set(tokens))
        # Robertson/Sparck-Jones IDF. log 안에 1을 더해 음수가 나오지 않게 한다
        # (전체의 절반 넘는 문서에 나오는 흔한 낱말이 음수 점수를 받는 것을 막는다).
        self.idf: dict[str, float] = {
            term: math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

        # document_id -> 이 문서에 속한 청크들의 위치
        self.by_document: dict[str, list[int]] = defaultdict(list)
        for i, doc_id in enumerate(document_ids):
            self.by_document[doc_id].append(i)

    def search(self, question: str, document_id: str, top_n: int) -> list[str]:
        """document_id 안에서만 BM25 상위 top_n 의 chunk_id 를 순서대로 돌려준다."""
        candidates = self.by_document.get(document_id)
        if not candidates:
            return []

        query_terms = set(tokenize(question))
        if not query_terms:
            return []

        scored: list[tuple[float, int]] = []
        for i in candidates:
            freqs = self.term_freqs[i]
            norm = K1 * (1 - B + B * self.lengths[i] / self.avg_len) if self.avg_len else K1
            score = 0.0
            for term in query_terms:
                f = freqs.get(term, 0)
                if not f:
                    continue
                score += self.idf.get(term, 0.0) * f * (K1 + 1) / (f + norm)
            if score > 0:
                scored.append((score, i))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [self.chunk_ids[i] for _, i in scored[:top_n]]


def build_from_collection(collection) -> Bm25Index:
    """Chroma 컬렉션 안의 본문으로 BM25 색인을 만든다."""
    data = collection.get(include=["documents", "metadatas"])
    document_ids = [m["document_id"] for m in data["metadatas"]]
    return Bm25Index(data["ids"], document_ids, data["documents"])


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = 60, weights: list[float] | None = None
) -> list[str]:
    """여러 순위 목록을 하나로 합친다 (RRF).

    점수를 직접 더하지 않고 순위의 역수만 쓴다. dense 의 코사인 유사도와 BM25 점수는
    척도가 전혀 달라서 가중합을 하려면 정규화가 필요한데, RRF 는 "몇 등인가"만 본다.
    k 는 상위권 쏠림을 완화하는 상수로 60이 관례다.

    weights 로 축별 영향력을 조절한다. 두 축의 실력이 비슷할 때만 1:1 이 맞고,
    한쪽이 확실히 강하면 약한 쪽을 낮춰야 한다. 실측(2026-09-08) 결과 이 데이터에서는
    dense 가 훨씬 강해서 1:1 로 합치면 오히려 나빠졌다.
    """
    if weights is None:
        weights = [1.0] * len(rankings)

    totals: dict[str, float] = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        for rank, chunk_id in enumerate(ranking):
            totals[chunk_id] += weight / (k + rank + 1)
    return sorted(totals, key=lambda cid: totals[cid], reverse=True)
