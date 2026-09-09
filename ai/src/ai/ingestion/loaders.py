"""ai.ingestion.loaders - Data Contract JSONL 로딩.

M2 Data Contract(JSONL) 파일을 읽어 dict 리스트로 반환한다.
필드 스키마는 DATA_CONTRACT_v0.1_FROZEN.md 의 C0 Chunk / Document 스키마를 따른다.

LIVE(Live-Dev Dataset v0.1)는 같은 내용을 다른 이름으로 담는다.
  * 청크 필드 대부분이 `metadata` 아래로 한 단계 들어가 있다
  * `document_id` -> `canonical_doc_id` (파일 내용 SHA256 앞 20자)
  * `block_ids` -> `element_ids`
  * 문서 메타데이터 키가 한글 (`사업명` / `발주기관` / `사업금액`)

레코드마다 스키마를 판별해 계약 필드명으로 정규화하므로 indexer / retriever /
chain 은 어느 데이터가 들어왔는지 알 필요가 없다. 데이터셋을 갈아끼울 때
`--chunks` / `--documents` 경로만 바꾸면 된다.
"""

from __future__ import annotations

import json
import re

# hwp/pdf 파서가 남긴 제어문자. LIVE section_path 의 3.0%(246건)에 \x01 이 섞여 있고,
# 이 값은 chain.py 에서 " > ".join 되어 그대로 프롬프트에 들어가므로 여기서 지운다.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"\s+")

# LIVE 청커는 C0 의 고정 길이 방식이 아니라 섹션 경계 우선 + 300~800 토큰이다
# (LIVE_FIELD_MAPPING_v0.1.md). 어느 청커로 만든 데이터인지 색인에 남긴다.
LIVE_CHUNKING_VERSION = "live-section-300-800-v0.1"
LIVE_SPLIT = "LIVE_DEV"


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# 스키마 판별
# ---------------------------------------------------------------------------


def is_live_chunk(record: dict) -> bool:
    return "canonical_doc_id" in (record.get("metadata") or {})


def is_live_document(record: dict) -> bool:
    return "canonical_doc_id" in record


# ---------------------------------------------------------------------------
# LIVE -> Data Contract 정규화
# ---------------------------------------------------------------------------


def _clean(value) -> str:
    """제어문자를 지우고 연속 공백을 하나로 줄인다."""
    if not isinstance(value, str):
        return ""
    return _SPACES.sub(" ", _CONTROL.sub(" ", value)).strip()


def _clean_path(values) -> list[str]:
    out = []
    for v in values or []:
        cleaned = _clean(v)
        if cleaned:
            out.append(cleaned)
    return out


def live_chunk_to_contract(record: dict) -> dict:
    """LIVE 청크 1건을 C0 Chunk 계약 필드명으로 옮긴다.

    `document_id` 가 판본마다 다른 자리에 있다. 아래 순서로 찾는다.

      1. 최상위 `document_id`            LIVE v0.3
      2. `metadata.document_id`          STANDARD_V0_SPLIT_70_15_15 v0.1
      3. `metadata.canonical_doc_id`     LIVE v0.1

    2번을 빠뜨리면 안 된다. Standard v0 는 청크에는 `metadata.document_id`(=DOC_004),
    문서에는 최상위 `document_id`(=DOC_004)를 두는데, 청크에서 canonical_doc_id
    (=doc_30d5f1aa...)로 떨어지면 문서 쪽 키와 달라져 **전 청크가 고아가 된다**
    (실측 2026-09-08).
    """
    meta = record.get("metadata") or {}
    return {
        "chunk_id": record["chunk_id"],
        "document_id": (
            record.get("document_id")
            or meta.get("document_id")
            or meta["canonical_doc_id"]
        ),
        "text": record.get("text") or "",
        # 검색 전용 텍스트(제목·기관이 앞에 붙은 것). 데이터팀 스키마의
        # search_text_preference 가 이걸 먼저 쓰라고 명시한다. 파서가 남긴 제어문자가
        # 섞여 있어 정제해서 담는다. 실제로 뭘 임베딩할지는 build_index 가 정한다.
        "retrieval_text": _clean(record.get("retrieval_text")),
        # v0.3 은 DEV/VAL 을 split 으로 구분한다. 이걸 덮어쓰면 한 색인에 둘을
        # 넣었을 때 검증셋이 개발셋 검색에 섞여도 알아챌 수가 없다.
        "split": record.get("split") or meta.get("semantic_role") or LIVE_SPLIT,
        # RETRIEVAL_HANDOFF 3.4 절이 버리지 말아 달라고 명시한 필드.
        # LIVE v0.3 은 최상위, Standard v0 는 metadata 안에 둔다.
        "semantic_role": record.get("semantic_role") or meta.get("semantic_role") or "",
        "chunk_index": meta.get("chunk_index"),
        "section_path": _clean_path(meta.get("section_path")),
        "block_ids": record.get("block_ids") or meta.get("element_ids") or [],
        # LIVE 에는 requirement_ids 가 없다 (9,120건 전수 확인, 채워진 것 0건).
        # RFP100 은 45.3% 가 채워져 있던 필드다. 없는 값을 지어내지 않고 비워 둔다.
        # chain.py 는 비면 프롬프트에 "-" 로 넣으므로 죽지는 않는다.
        "requirement_ids": [],
        # char_start/char_end 는 '몇 번째 글자'인데 LIVE 의 order_index 는 '몇 번째 요소'라
        # 단위가 다르다. 옮겨 담으면 값이 거짓이 되므로 비운다. 위치 추적이 필요하면
        # block_ids(= element_ids)로 blocks 파일을 조회하면 된다.
        "char_start": None,
        "char_end": None,
        "page_start": None,
        "page_end": None,
        "chunking_version": record.get("chunking_version") or LIVE_CHUNKING_VERSION,
        "source_text_version": "canonical_text_v0.1",
    }


def _number_or_none(value):
    """숫자만 통과시킨다. NaN 을 걸러내는 게 목적이다.

    StandardDataset 문서에는 `입찰시작일: nan` 처럼 pandas 가 남긴 NaN 이 들어 있다.
    NaN 은 float 라서 타입 검사를 통과해 그대로 Chroma 메타데이터에 저장되는데,
    이후 어떤 비교와도 False 가 되어 필터링이 조용히 어긋난다.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN 은 자기 자신과 같지 않다
        return None
    return value


def live_document_to_contract(record: dict) -> dict:
    """LIVE / StandardDataset 문서 1건을 Document 계약 필드명으로 옮긴다."""
    return {
        # v0.3 은 document_id 를 최상위로 올렸고 값은 canonical_doc_id 와 같다.
        "document_id": record.get("document_id") or record["canonical_doc_id"],
        "title": _clean(record.get("사업명")),
        "agency": _clean(record.get("발주기관")),
        "budget_amount": _number_or_none(record.get("사업금액")),
        # StandardDataset 에는 budget_status 필드 자체가 없다(LIVE 에는 있다).
        "budget_status": record.get("budget_status", ""),
        "split": record.get("split", LIVE_SPLIT),
    }


# ---------------------------------------------------------------------------
# 공개 로더 - 어느 스키마가 들어와도 계약 필드명으로 돌려준다
# ---------------------------------------------------------------------------


def load_chunks(chunks_path: str) -> list[dict]:
    """C0 청크를 읽는다. LIVE 스키마면 정규화하고, RFP100 이면 그대로 통과시킨다."""
    return [
        live_chunk_to_contract(record) if is_live_chunk(record) else record
        for record in load_jsonl(chunks_path)
    ]


def build_document_lookup(documents_path: str) -> dict:
    """document_id -> 문서 메타데이터(title/agency/budget_amount/budget_status 등) 매핑."""
    lookup: dict = {}
    for record in load_jsonl(documents_path):
        if is_live_document(record):
            record = live_document_to_contract(record)
        lookup[record["document_id"]] = record
    return lookup
