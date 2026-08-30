# RFP Canonical Dataset — Data Dictionary v0.1

## Document

| Field | Type | Required | Meaning |
|---|---|---|---|
| document_id | string | Y | filename과 독립된 canonical document key |
| split | enum | Y | DEV / REGRESSION / FINAL_HOLDOUT |
| content_group_id | string | Y | exact duplicate grouping key |
| content_hash | string | Y | SHA-256 |
| source_filename_raw | string | Y | archive 원문 filename |
| source_filename_nfc | string | Y | Unicode NFC normalized filename |
| file_type | enum | Y | HWP / PDF |
| title | string | Y | 현재 metadata title |
| agency | string | Y | 현재 metadata agency |
| metadata_quality_flags | list | Y | zero sentinel / duplicate / mismatch 등 |
| budget_amount | int/null | Y | 검증 가능한 경우 KRW normalized value |
| budget_status | enum | Y | KNOWN / UNKNOWN / UNDISCLOSED / NOT_APPLICABLE / CONFLICT |
| budget_source | string | Y | value provenance |
| parser_version | string | Y | parser implementation version |
| parse_status | enum | Y | SUCCESS / SUCCESS_WITH_WARNING / FAIL |
| parse_warnings | list | Y | recoverable parser issues |
| text_raw | string | Y | control-safe parser output |
| text_normalized | string | Y | canonical retrieval text |
| source_text_version | string | Y | canonical_text_v0.1 |

## Structural Block

| Field | Meaning |
|---|---|
| block_id | unique block key |
| block_type | HEADING / PARAGRAPH / TABLE / REQUIREMENT / LIST / OTHER |
| section_path | heuristic semantic heading path |
| semantic_role | PROJECT_OVERVIEW / ELIGIBILITY / REQUIREMENT / EVALUATION / CONTRACT / SECURITY / ... |
| requirement_id_raw | source expression |
| requirement_id_normalized | e.g. PMR-003 |
| requirement_ids | normalized IDs found in block |
| source_page | PDF page; HWP baseline null |
| char_start / char_end | canonical document text offsets |

DEV block distribution:

```text
{'TABLE': 3935, 'PARAGRAPH': 19791, 'LIST': 11675, 'HEADING': 7711, 'REQUIREMENT': 4255}
```

## Chunk C0

| Field | Meaning |
|---|---|
| chunk_id | unique chunk key |
| chunking_version | fixed-char-1200-o200-v0.1 |
| text | canonical substring |
| block_ids | overlapping structural blocks |
| requirement_ids | requirement IDs inherited from overlapping blocks |
| char_start / char_end | canonical document offsets |
| page_start / page_end | PDF provenance where available |

## Gold v0.2

`evidence_logic`:

- ALL: 모든 listed evidence가 필요한 multi-evidence question
- ANY: listed evidence가 서로 대체 가능
- NONE: unanswerable

각 evidence는 canonical char span + block IDs + C0 chunk IDs로 재-anchor한다.
