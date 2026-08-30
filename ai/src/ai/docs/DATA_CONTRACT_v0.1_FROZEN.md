# RFP RAG Data Contract v0.1 — FROZEN

**상태:** `FROZEN_v0.1_FOR_BASELINE`  
**Freeze 근거:** DEV Raw Deep Dive + Gold v0.2 canonical re-anchor + DEV/Regression 실제 record interface handshake PASS  
**변경 규칙:** v0.1 breaking change 금지. 추가/변경 요구는 v0.2 proposal로 관리.

## 1. P0 불변조건

```text
selected_document_id
→ 해당 document_id의 chunks만 Retrieval
→ Evidence
→ Answer / Citation / Abstention
```

```text
all(hit.document_id == selected_document_id)
```

위반 시 `RETRIEVAL_SCOPE_ERROR` Critical Failure.

## 2. Document Record — mandatory

```json
{
  "document_id": "DOC_001",
  "split": "DEV",
  "content_group_id": "CG001",
  "content_hash": "sha256...",
  "source_file": "...",
  "source_filename_raw": "...",
  "source_filename_nfc": "...",
  "file_type": "HWP",
  "title": "...",
  "agency": "...",
  "metadata_source": "data_list.csv",
  "metadata_quality_flags": [],
  "budget_amount": 352000000,
  "budget_status": "KNOWN",
  "budget_source": "CSV",
  "parser_version": "hwp5-control-safe-v0.2",
  "parse_status": "SUCCESS",
  "parse_warnings": [],
  "source_text_version": "canonical_text_v0.1",
  "normalization_version": "unicode-nfc-whitespace-v0.1",
  "text_raw": "...",
  "text_normalized": "...",
  "schema_version": "document-v0.1",
  "data_contract_version": "FROZEN_v0.1"
}
```

`parse_status`: `SUCCESS | SUCCESS_WITH_WARNING | FAIL`  
`budget_status`: `KNOWN | UNKNOWN | UNDISCLOSED | NOT_APPLICABLE | CONFLICT`

`budget_amount=0`을 자동으로 실제 0원으로 해석하지 않는다.

## 3. Structural Block Record — mandatory

```json
{
  "block_id": "DOC_001-B00042",
  "document_id": "DOC_001",
  "block_index": 42,
  "block_type": "REQUIREMENT",
  "text_raw": "...",
  "text_normalized": "...",
  "section_path": ["Ⅱ. 요구사항"],
  "semantic_role": "REQUIREMENT",
  "requirement_id_raw": "PMR-프로젝트관리-003",
  "requirement_id_normalized": "PMR-003",
  "requirement_ids": ["PMR-003"],
  "source_page": null,
  "char_start": 12345,
  "char_end": 12600,
  "parser_version": "hwp5-control-safe-v0.2",
  "source_text_version": "canonical_text_v0.1",
  "schema_version": "block-v0.1",
  "data_contract_version": "FROZEN_v0.1"
}
```

`block_type`: `HEADING | PARAGRAPH | TABLE | REQUIREMENT | LIST | OTHER`  
`semantic_role`: `PROJECT_OVERVIEW | ELIGIBILITY | REQUIREMENT | EVALUATION | CONTRACT | SECURITY | APPENDIX_TEMPLATE | LEGAL_REFERENCE | OTHER`

Baseline의 table block은 **텍스트/순서 보존**을 의미하며 완전한 row/column reconstruction을 보장하지 않는다.

## 4. Chunk Record — C0

C0는 embedding model/tokenizer 확정 전의 모델 독립적 기준선이므로 **character window**를 사용한다.

```text
fixed-char-1200-o200-v0.1
```

```json
{
  "chunk_id": "DOC_001-C00012",
  "document_id": "DOC_001",
  "split": "DEV",
  "chunk_index": 12,
  "chunking_version": "fixed-char-1200-o200-v0.1",
  "text": "...",
  "section_path": ["입찰참가자격"],
  "block_ids": ["DOC_001-B00120"],
  "requirement_ids": [],
  "char_start": 12000,
  "char_end": 13200,
  "page_start": null,
  "page_end": null,
  "source_text_version": "canonical_text_v0.1",
  "schema_version": "chunk-v0.1",
  "data_contract_version": "FROZEN_v0.1"
}
```

## 5. Retrieval → Generation

```json
{
  "selected_document_id": "DOC_001",
  "query": "사업 예산은?",
  "hits": [
    {
      "rank": 1,
      "chunk_id": "DOC_001-C00012",
      "document_id": "DOC_001",
      "score": 0.82,
      "text": "...",
      "section_path": ["사업개요"],
      "requirement_ids": []
    }
  ]
}
```

## 6. Generation Output

```json
{
  "answer": "...",
  "abstained": false,
  "sources": [
    {
      "document_id": "DOC_001",
      "chunk_id": "DOC_001-C00012",
      "block_ids": ["DOC_001-B00010"],
      "section_path": ["사업개요"]
    }
  ]
}
```

## 7. Gold v0.2

Gold evidence는 `canonical_text_v0.1`에 재-anchor하며 다음을 가진다.

```text
char_start / char_end
block_ids
source_pages
c0_chunk_ids
evidence_logic = ALL | ANY | NONE
```

- `ALL`: 모든 evidence가 답에 필요
- `ANY`: 대체 가능한 evidence 중 하나 이상이면 충분
- `NONE`: Unanswerable

## 8. Critical Fact

```json
{
  "type": "EXPERIENCE_YEARS",
  "raw_value": "10년 이상",
  "normalized_value": 10,
  "unit": "YEAR",
  "operator": "GTE"
}
```

`operator`: `EQ | GTE | LTE | GT | LT | REQUIRED | PROHIBITED`

## 9. Split / Leakage

- DEV / Regression / Final Holdout = document-level
- exact duplicate `content_group_id`는 하나의 split에만 존재
- Final Holdout은 M2에서 parse/canonicalize/chunk하지 않음
- Regression과 Final Holdout을 동일 용도로 사용하지 않음
