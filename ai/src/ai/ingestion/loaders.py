"""ai.ingestion.loaders — raw_data → 문서 로딩.

M2 Data Contract(JSONL) 파일을 읽어 dict 리스트로 반환한다.
필드 스키마는 ai/src/ai/docs/DATA_CONTRACT_v0.1_FROZEN.md 를 따른다.
"""

from __future__ import annotations

import json


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_document_lookup(documents_path: str) -> dict:
    """document_id -> 문서 메타데이터(title/agency/budget_amount/budget_status 등) 매핑."""
    return {d["document_id"]: d for d in load_jsonl(documents_path)}
