"""Gold-independent integrity validation for data contract v0.1 records."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from ai.ingestion.custom.chunking import (
    CHUNKING_VERSION,
    CHUNK_SIZE,
    CHUNK_STRIDE,
    DATA_CONTRACT_VERSION,
    SECTION_PATH_MAX_VALUES,
    SOURCE_TEXT_VERSION,
)

DOCUMENT_SCHEMA_VERSION = "document-v0.1"
BLOCK_SCHEMA_VERSION = "block-v0.1"
CHUNK_SCHEMA_VERSION = "chunk-v0.1"
ALLOWED_FILE_TYPES = {"HWP", "PDF"}
ALLOWED_PARSE_STATUSES = {"SUCCESS", "SUCCESS_WITH_WARNING", "FAIL"}
ALLOWED_BUDGET_STATUSES = {
    "KNOWN",
    "UNKNOWN",
    "UNDISCLOSED",
    "NOT_APPLICABLE",
    "CONFLICT",
}
ALLOWED_BLOCK_TYPES = {"HEADING", "PARAGRAPH", "TABLE", "REQUIREMENT", "LIST", "OTHER"}
ALLOWED_SEMANTIC_ROLES = {
    "PROJECT_OVERVIEW",
    "ELIGIBILITY",
    "REQUIREMENT",
    "EVALUATION",
    "CONTRACT",
    "SECURITY",
    "APPENDIX_TEMPLATE",
    "LEGAL_REFERENCE",
    "OTHER",
}

DOCUMENT_REQUIRED_FIELDS = {
    "document_id",
    "split",
    "content_group_id",
    "content_hash",
    "source_file",
    "source_filename_raw",
    "source_filename_nfc",
    "file_type",
    "title",
    "agency",
    "metadata_source",
    "metadata_quality_flags",
    "budget_amount",
    "budget_status",
    "budget_source",
    "parser_version",
    "parse_status",
    "parse_warnings",
    "source_text_version",
    "normalization_version",
    "text_raw",
    "text_normalized",
    "schema_version",
    "data_contract_version",
}
BLOCK_REQUIRED_FIELDS = {
    "block_id",
    "document_id",
    "block_index",
    "block_type",
    "text_raw",
    "text_normalized",
    "section_path",
    "semantic_role",
    "requirement_id_raw",
    "requirement_id_normalized",
    "requirement_ids",
    "source_page",
    "char_start",
    "char_end",
    "parser_version",
    "source_text_version",
    "schema_version",
    "data_contract_version",
}
CHUNK_REQUIRED_FIELDS = {
    "chunk_id",
    "document_id",
    "split",
    "chunk_index",
    "chunking_version",
    "text",
    "section_path",
    "block_ids",
    "requirement_ids",
    "char_start",
    "char_end",
    "page_start",
    "page_end",
    "source_text_version",
    "schema_version",
    "data_contract_version",
}


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _missing_fields(row: dict[str, Any], required: set[str]) -> list[str]:
    return sorted(required - set(row))


def _integer(value: Any, default: int = -1) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _related_blocks(
    blocks: list[dict[str, Any]], start: int, end: int
) -> list[dict[str, Any]]:
    return [
        block
        for block in blocks
        if _integer(block.get("char_start")) < end
        and _integer(block.get("char_end")) > start
    ]


def validate_dataset(
    documents: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    forbidden_document_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate IDs, FKs, spans, deterministic order, coverage, and provenance."""

    failures: list[str] = []
    sealed_document_ids = {str(value) for value in forbidden_document_ids}
    final_holdout_artifact_violations: list[str] = []
    for record_type, rows, required in (
        ("document", documents, DOCUMENT_REQUIRED_FIELDS),
        ("block", blocks, BLOCK_REQUIRED_FIELDS),
        ("chunk", chunks, CHUNK_REQUIRED_FIELDS),
    ):
        for index, row in enumerate(rows):
            missing = _missing_fields(row, required)
            if missing:
                failures.append(
                    f"{record_type}_required_fields:{index}:{','.join(missing)}"
                )
            document_id = str(row.get("document_id", ""))
            if (
                str(row.get("split", "")).strip().upper() == "FINAL_HOLDOUT"
                or document_id in sealed_document_ids
            ):
                record_id = str(
                    row.get(f"{record_type}_id", row.get("document_id", index))
                )
                final_holdout_artifact_violations.append(
                    f"final_holdout_{record_type}:{record_id}"
                )

    failures.extend(final_holdout_artifact_violations)

    for document in documents:
        document_id = str(document.get("document_id", ""))
        expected = {
            "schema_version": DOCUMENT_SCHEMA_VERSION,
            "data_contract_version": DATA_CONTRACT_VERSION,
            "source_text_version": SOURCE_TEXT_VERSION,
        }
        for field, value in expected.items():
            if document.get(field) != value:
                failures.append(f"document_{field}:{document_id}")
        if not isinstance(document.get("split"), str) or not document["split"].strip():
            failures.append(f"document_split:{document_id}")
        if document.get("file_type") not in ALLOWED_FILE_TYPES:
            failures.append(f"document_file_type:{document_id}")
        if document.get("parse_status") not in ALLOWED_PARSE_STATUSES:
            failures.append(f"document_parse_status:{document_id}")
        if document.get("budget_status") not in ALLOWED_BUDGET_STATUSES:
            failures.append(f"document_budget_status:{document_id}")

    for block in blocks:
        block_id = str(block.get("block_id", ""))
        expected = {
            "schema_version": BLOCK_SCHEMA_VERSION,
            "data_contract_version": DATA_CONTRACT_VERSION,
            "source_text_version": SOURCE_TEXT_VERSION,
        }
        for field, value in expected.items():
            if block.get(field) != value:
                failures.append(f"block_{field}:{block_id}")
        if block.get("block_type") not in ALLOWED_BLOCK_TYPES:
            failures.append(f"block_type:{block_id}")
        if block.get("semantic_role") not in ALLOWED_SEMANTIC_ROLES:
            failures.append(f"block_semantic_role:{block_id}")

    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        expected = {
            "schema_version": CHUNK_SCHEMA_VERSION,
            "data_contract_version": DATA_CONTRACT_VERSION,
            "source_text_version": SOURCE_TEXT_VERSION,
            "chunking_version": CHUNKING_VERSION,
        }
        for field, value in expected.items():
            if chunk.get(field) != value:
                failures.append(f"chunk_{field}:{chunk_id}")
        if not isinstance(chunk.get("split"), str) or not chunk["split"].strip():
            failures.append(f"chunk_split:{chunk_id}")

    document_ids = [str(row.get("document_id", "")) for row in documents]
    block_ids = [str(row.get("block_id", "")) for row in blocks]
    chunk_ids = [str(row.get("chunk_id", "")) for row in chunks]
    for record_type, values in (
        ("document", document_ids),
        ("block", block_ids),
        ("chunk", chunk_ids),
    ):
        for duplicate in _duplicates(values):
            failures.append(f"duplicate_{record_type}_id:{duplicate}")

    if document_ids != sorted(document_ids):
        failures.append("document_order")
    if [
        (str(row.get("document_id", "")), _integer(row.get("block_index")))
        for row in blocks
    ] != sorted(
        (str(row.get("document_id", "")), _integer(row.get("block_index")))
        for row in blocks
    ):
        failures.append("block_order")
    if [
        (str(row.get("document_id", "")), _integer(row.get("chunk_index")))
        for row in chunks
    ] != sorted(
        (str(row.get("document_id", "")), _integer(row.get("chunk_index")))
        for row in chunks
    ):
        failures.append("chunk_order")

    document_map = {str(row.get("document_id", "")): row for row in documents}
    blocks_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chunks_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    block_owner: dict[str, str] = {}

    for block in blocks:
        document_id = str(block.get("document_id", ""))
        block_id = str(block.get("block_id", ""))
        if document_id not in document_map:
            failures.append(f"block_document_fk:{block_id}")
        blocks_by_document[document_id].append(block)
        block_owner[block_id] = document_id
    for chunk in chunks:
        document_id = str(chunk.get("document_id", ""))
        chunk_id = str(chunk.get("chunk_id", ""))
        if document_id not in document_map:
            failures.append(f"chunk_document_fk:{chunk_id}")
        chunks_by_document[document_id].append(chunk)

    for document_id, document in document_map.items():
        canonical = str(document.get("text_normalized", ""))
        if canonical != document.get("text_raw"):
            failures.append(f"document_text_mismatch:{document_id}")
        if unicodedata.normalize(
            "NFC", str(document.get("source_filename_raw", ""))
        ) != document.get("source_filename_nfc"):
            failures.append(f"filename_nfc:{document_id}")
        content_hash = str(document.get("content_hash", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            failures.append(f"content_hash:{document_id}")

        document_blocks = sorted(
            blocks_by_document.get(document_id, []),
            key=lambda row: _integer(row.get("block_index")),
        )
        document_chunks = sorted(
            chunks_by_document.get(document_id, []),
            key=lambda row: _integer(row.get("chunk_index")),
        )
        if not document_blocks:
            failures.append(f"document_without_blocks:{document_id}")
            continue
        if not document_chunks:
            failures.append(f"document_without_chunks:{document_id}")
            continue

        indexes = [_integer(row.get("block_index")) for row in document_blocks]
        if indexes != list(range(len(document_blocks))):
            failures.append(f"block_contiguous_index:{document_id}")
        reconstructed = "\n\n".join(
            str(row.get("text_raw", "")) for row in document_blocks
        )
        if reconstructed != canonical:
            failures.append(f"block_canonical_coverage:{document_id}")
        for index, block in enumerate(document_blocks):
            block_id = str(block.get("block_id", ""))
            if block_id != f"{document_id}-B{index:05d}":
                failures.append(f"block_id_order:{block_id}")
            start = _integer(block.get("char_start"))
            end = _integer(block.get("char_end"))
            if not 0 <= start < end <= len(canonical):
                failures.append(f"block_span:{block_id}")
            elif canonical[start:end] != block.get("text_normalized"):
                failures.append(f"block_text_span:{block_id}")
            page = block.get("source_page")
            if page is not None and (not isinstance(page, int) or page < 1):
                failures.append(f"block_page:{block_id}")

        chunk_indexes = [_integer(row.get("chunk_index")) for row in document_chunks]
        if chunk_indexes != list(range(len(document_chunks))):
            failures.append(f"chunk_contiguous_index:{document_id}")
        coverage_end = 0
        for index, chunk in enumerate(document_chunks):
            chunk_id = str(chunk.get("chunk_id", ""))
            if chunk_id != f"{document_id}-C{index:05d}":
                failures.append(f"chunk_id_order:{chunk_id}")
            start = _integer(chunk.get("char_start"))
            end = _integer(chunk.get("char_end"))
            expected_start = index * CHUNK_STRIDE
            expected_end = min(len(canonical), expected_start + CHUNK_SIZE)
            if (start, end) != (expected_start, expected_end):
                failures.append(f"chunk_span:{chunk_id}")
                continue
            if canonical[start:end] != chunk.get("text"):
                failures.append(f"chunk_text_span:{chunk_id}")
            if start > coverage_end:
                failures.append(f"canonical_gap:{document_id}:{coverage_end}-{start}")
            coverage_end = max(coverage_end, end)

            related = _related_blocks(document_blocks, start, end)
            expected_block_ids = [str(block["block_id"]) for block in related]
            if chunk.get("block_ids") != expected_block_ids:
                failures.append(f"block_provenance:{chunk_id}")
            for block_id in chunk.get("block_ids", []):
                if block_id not in block_owner or block_owner[block_id] != document_id:
                    failures.append(f"chunk_block_fk:{chunk_id}:{block_id}")
            expected_sections = list(
                dict.fromkeys(
                    value
                    for block in related
                    for value in block.get("section_path", [])
                )
            )[:SECTION_PATH_MAX_VALUES]
            if chunk.get("section_path") != expected_sections:
                failures.append(f"section_provenance:{chunk_id}")
            expected_requirements = list(
                dict.fromkeys(
                    value
                    for block in related
                    for value in block.get("requirement_ids", [])
                )
            )
            if chunk.get("requirement_ids") != expected_requirements:
                failures.append(f"requirement_provenance:{chunk_id}")
            pages = [
                block["source_page"]
                for block in related
                if isinstance(block.get("source_page"), int)
                and not isinstance(block.get("source_page"), bool)
            ]
            expected_pages = (min(pages), max(pages)) if pages else (None, None)
            if (chunk.get("page_start"), chunk.get("page_end")) != expected_pages:
                failures.append(f"page_provenance:{chunk_id}")
        if coverage_end != len(canonical):
            failures.append(f"canonical_end:{document_id}:{coverage_end}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "documents": len(documents),
        "blocks": len(blocks),
        "chunks": len(chunks),
        "final_holdout_artifact_violations": final_holdout_artifact_violations,
    }


def validate_splits(
    inventory: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    allowed_splits: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Fail closed on missing, duplicate, unknown, or cross-split source identity."""

    failures: list[str] = []
    normalized_allowed = (
        {name.strip().upper() for name in allowed_splits}
        if allowed_splits is not None
        else None
    )
    inventory_ids = [str(row.get("source_document_id", "")) for row in inventory]
    inventory_by_id = {str(row.get("source_document_id", "")): row for row in inventory}
    duplicate_inventory_ids = _duplicates(inventory_ids)
    if duplicate_inventory_ids:
        failures.extend(
            f"duplicate_inventory_source_id:{source_id}"
            for source_id in duplicate_inventory_ids
        )

    assignment_ids = [str(row.get("source_document_id", "")) for row in assignments]
    duplicate_assignments = _duplicates(assignment_ids)
    unknown_ids = sorted(set(assignment_ids) - set(inventory_ids))
    unassigned_ids = sorted(set(inventory_ids) - set(assignment_ids))
    failures.extend(
        f"duplicate_split_assignment:{source_id}" for source_id in duplicate_assignments
    )
    failures.extend(
        f"unknown_source_document_id:{source_id}" for source_id in unknown_ids
    )
    failures.extend(
        f"unassigned_source_document_id:{source_id}" for source_id in unassigned_ids
    )

    sha_splits: dict[str, set[str]] = defaultdict(set)
    group_splits: dict[str, set[str]] = defaultdict(set)
    split_source_ids: dict[str, set[str]] = defaultdict(set)
    split_canonical_ids: dict[str, set[str]] = defaultdict(set)
    split_groups: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        source_id = str(assignment.get("source_document_id", ""))
        split = str(assignment.get("split", "")).strip().upper()
        if not split:
            failures.append(f"empty_split:{source_id}")
            continue
        if normalized_allowed is not None and split not in normalized_allowed:
            failures.append(f"unknown_split:{source_id}:{split}")
        inventory_row = inventory_by_id.get(source_id)
        if inventory_row is None:
            continue
        for field in ("canonical_document_id", "duplicate_group_id", "sha256"):
            if str(assignment.get(field, "")) != str(inventory_row.get(field, "")):
                failures.append(f"split_identity_mismatch:{source_id}:{field}")
        sha = str(inventory_row["sha256"])
        group_id = str(inventory_row["duplicate_group_id"])
        canonical_id = str(inventory_row["canonical_document_id"])
        sha_splits[sha].add(split)
        group_splits[group_id].add(split)
        split_source_ids[split].add(source_id)
        split_canonical_ids[split].add(canonical_id)
        split_groups[split].add(group_id)

    sha_leakage = {
        sha: sorted(splits) for sha, splits in sha_splits.items() if len(splits) > 1
    }
    group_leakage = {
        group_id: sorted(splits)
        for group_id, splits in group_splits.items()
        if len(splits) > 1
    }
    failures.extend(f"sha_cross_split:{sha}" for sha in sorted(sha_leakage))
    failures.extend(
        f"duplicate_group_cross_split:{group_id}" for group_id in sorted(group_leakage)
    )
    split_names = sorted(set(split_source_ids) | (normalized_allowed or set()))
    split_counts = {
        split: {
            "source_document_count": len(split_source_ids[split]),
            "unique_canonical_count": len(split_canonical_ids[split]),
            "duplicate_group_count": len(split_groups[split]),
        }
        for split in split_names
    }
    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "total_inventory_count": len(inventory),
        "assigned_count": len(assignments),
        "unassigned_documents": unassigned_ids,
        "duplicate_assignments": duplicate_assignments,
        "unknown_document_ids": unknown_ids,
        "sha_cross_split_leakage": sha_leakage,
        "duplicate_group_cross_split_leakage": group_leakage,
        "split_counts": split_counts,
    }


def combine_validation(
    dataset_validation: dict[str, Any], split_validation: dict[str, Any]
) -> dict[str, Any]:
    failures = [
        *dataset_validation.get("failures", []),
        *(f"split:{failure}" for failure in split_validation.get("failures", [])),
    ]
    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "documents": dataset_validation.get("documents", 0),
        "blocks": dataset_validation.get("blocks", 0),
        "chunks": dataset_validation.get("chunks", 0),
        "dataset": dataset_validation,
        "split": split_validation,
    }
