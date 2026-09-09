"""Gold-independent M0-M2 builder for the frozen RFP data contract v0.1."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.ingestion.custom.chunking import (
    CHUNKING_VERSION,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    build_c0,
)
from ai.ingestion.custom.inventory import (
    load_metadata,
    metadata_alias,
    sha256_file,
    source_files,
)
from ai.ingestion.custom.parsers import (
    NORMALIZATION_VERSION,
    PARSER_HWP,
    ParseResult,
    PrimitiveBlock,
)
from ai.ingestion.custom.parsers import parse_document as parse_raw_document
from ai.ingestion.custom.validation import validate_dataset

DATA_CONTRACT_VERSION = "FROZEN_v0.1"
SOURCE_TEXT_VERSION = "canonical_text_v0.1"
PIPELINE_VERSION = "m0-m2-baseline-v0.1"
FROZEN_M2_PROCESSED_SPLITS = ("DEV", "REGRESSION")
FROZEN_M2_UNPROCESSED_SPLITS = ("FINAL_HOLDOUT",)
FROZEN_SPLITS = (*FROZEN_M2_PROCESSED_SPLITS, *FROZEN_M2_UNPROCESSED_SPLITS)

REQUIREMENT_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{2,5})\s*[-–—]\s*"
    r"(?:(?:[가-힣A-Za-z]+)\s*[-–—]\s*)?(\d{1,4})(?!\d)",
    re.IGNORECASE,
)
# Kept only because this rule is part of the frozen v0.1 block annotation behavior.
REQUIREMENT_NETWORK_SPEC_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{2,5})\s*[-–—]\s*[A-Z]\s+x\s+\d+[^\n]*"
    r"\n-\s*(\d{1,4})\b",
    re.IGNORECASE,
)
LIST_RE = re.compile(r"^(?:[□■○◦ㅇ❍※*]|-)")
HEADING_MARKER_RE = re.compile(
    r"^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+[.]|Ⅰ\s+[가-힣A-Za-z]|[IVX]{1,6}[.]\s*|"
    r"제\s*\d+\s*[장절]|\d+(?:\.\d+)*\s*(?:[.)])\s*\S|"
    r"[가-힣]\s*[.)]\s*\S|주\)\s*\S|20\s+[.]\s*[.])"
)
HEADING_KEYWORD_RE = re.compile(
    r"(?:요구사항|평가기준|사업\s*(?:개요|범위)|추진배경|"
    r"사업기간|계약조건|입찰\s*참가자격|일반사항|보안|"
    r"제안서\s*평가|특수계약조건)$"
)
DATE_OR_SIGNATURE_RE = re.compile(r"^(?:\d{3,4}\s*[.]|20\s*년|0000(?:[.\s]|년))")
HEADING_MAX_CHARS = 90

SEMANTIC_ROLE_RULES = (
    ("ELIGIBILITY", ("참가자격", "공동수급", "하도급")),
    ("EVALUATION", ("평가기준", "기술평가", "가격평가", "제안서 평가")),
    ("SECURITY", ("보안", "개인정보")),
    (
        "CONTRACT",
        (
            "계약조건",
            "계약방법",
            "계약 방법",
            "협상에 의한 계약",
            "입찰 및 계약 방법",
            "사업자 선정 및 계약 방법",
        ),
    ),
    ("PROJECT_OVERVIEW", ("사업개요", "추진배경", "사업기간", "사업비", "사업예산")),
    (
        "REQUIREMENT",
        (
            "요구사항 상세",
            "요구사항 고유번호",
            "요구사항고유번호",
            "요구사항 명칭",
            "요구사항명칭",
        ),
    ),
    ("APPENDIX_TEMPLATE", ("별지", "서식", "별첨")),
)


@dataclass(frozen=True, slots=True)
class DatasetBundle:
    documents: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    validation: dict[str, Any]
    metadata_supplied: bool
    metadata_file_name: str | None
    metadata_sha256: str | None
    document_id_mode: str
    default_split: str
    source_inputs: list[dict[str, Any]]
    split_counts: dict[str, int]
    processed_splits: tuple[str, ...]
    unprocessed_splits: tuple[str, ...]


def _requirement_ids(text: str) -> list[str]:
    matches = [
        (match.start(), f"{match.group(1).upper()}-{int(match.group(2)):03d}")
        for pattern in (REQUIREMENT_RE, REQUIREMENT_NETWORK_SPEC_RE)
        for match in pattern.finditer(text)
    ]
    return list(dict.fromkeys(value for _, value in sorted(matches)))


def _semantic_role(
    text: str, section_path: list[str], requirement_ids: list[str]
) -> str:
    context = " ".join([*section_path, text]).lower()
    for role, needles in SEMANTIC_ROLE_RULES:
        if any(needle in context for needle in needles) or (
            role == "REQUIREMENT" and requirement_ids
        ):
            return role
    return "OTHER"


def _is_heading(text: str) -> bool:
    numbered_lines = text.splitlines()
    compact_numbered_group = bool(
        HEADING_MAX_CHARS < len(text) <= 100
        and len(numbered_lines) > 1
        and all(
            re.match(r"^\d+(?:\.\d+)*\s*[.)]\s*\S", line) for line in numbered_lines
        )
    )
    if not (1 < len(text) <= HEADING_MAX_CHARS or compact_numbered_group):
        return False
    if DATE_OR_SIGNATURE_RE.match(text):
        return False
    if text.startswith(("I.\n", "V.\n", "X.\n")):
        return False
    if HEADING_MARKER_RE.match(text):
        return True
    return "\n" not in text and bool(HEADING_KEYWORD_RE.search(text.strip()))


def _block_type(
    parsed: ParseResult, block: PrimitiveBlock, requirement_ids: list[str]
) -> str:
    is_hwp = parsed.parser_version == PARSER_HWP
    if requirement_ids and (
        not is_hwp or "요구" in block.text or block.text.count("\n") >= 2
    ):
        return "REQUIREMENT"
    if block.native_type == "TABLE":
        return "TABLE"
    if _is_heading(block.text):
        return "HEADING"
    if is_hwp and LIST_RE.match(block.text):
        return "LIST"
    return "PARAGRAPH"


def _heading_section_labels(parsed: ParseResult, text: str) -> tuple[str, str]:
    if parsed.parser_version == PARSER_HWP:
        return text, " ".join(text.split())
    first_line = text.splitlines()[0].strip()
    return first_line, first_line


def annotate_blocks(
    document_id: str, split: str, parsed: ParseResult
) -> list[dict[str, Any]]:
    """Create deterministic structural blocks using the frozen v0.1 annotation rules."""

    rows: list[dict[str, Any]] = []
    section_path: list[str] = []
    cursor = 0
    for index, block in enumerate(parsed.blocks):
        requirement_ids = _requirement_ids(block.text)
        block_type = _block_type(parsed, block, requirement_ids)
        inherited_section_path: list[str] | None = None
        if block_type == "HEADING":
            row_label, inherited_label = _heading_section_labels(parsed, block.text)
            section_path = [row_label]
            inherited_section_path = [inherited_label]
        start = cursor
        end = start + len(block.text)
        requirement_raw = REQUIREMENT_RE.search(block.text)
        rows.append(
            {
                "block_id": f"{document_id}-B{index:05d}",
                "document_id": document_id,
                "block_index": index,
                "block_type": block_type,
                "text_raw": block.text,
                "text_normalized": block.text,
                "section_path": list(section_path),
                "semantic_role": _semantic_role(
                    block.text, list(section_path), requirement_ids
                ),
                "requirement_id_raw": requirement_raw.group(0)
                if requirement_raw
                else None,
                "requirement_id_normalized": requirement_ids[0]
                if requirement_ids
                else None,
                "requirement_ids": requirement_ids,
                "source_page": block.source_page,
                "source_section": block.source_section,
                "source_record": block.source_record,
                "char_start": start,
                "char_end": end,
                "split": split,
                "parser_version": parsed.parser_version,
                "source_text_version": SOURCE_TEXT_VERSION,
                "normalization_version": NORMALIZATION_VERSION,
                "schema_version": "block-v0.1",
                "data_contract_version": DATA_CONTRACT_VERSION,
            }
        )
        if inherited_section_path is not None:
            section_path = inherited_section_path
        cursor = end + 2
    return rows


def _parse_amount(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(float(value.replace(",", "").strip()))


def _budget_contract(metadata: dict[str, str], canonical: str) -> dict[str, Any]:
    flags: list[str] = []
    if metadata.get("is_exact_duplicate") == "True":
        flags.extend(("EXACT_DUPLICATE_GROUP", "METADATA_SOURCE_MISMATCH_SUSPECT"))

    explicit_status = metadata.get("budget_status", "").strip().upper()
    explicit_amount = _parse_amount(metadata.get("budget_amount"))
    if explicit_status:
        return {
            "budget_amount": explicit_amount,
            "budget_status": explicit_status,
            "budget_source": metadata.get("budget_source", "METADATA") or "METADATA",
            "metadata_quality_flags": flags,
        }

    raw_budget = metadata.get("budget", "").strip()
    precheck = metadata.get("budget_status_precheck", "")
    if precheck == "PRESENT_NONZERO" and raw_budget:
        return {
            "budget_amount": _parse_amount(raw_budget),
            "budget_status": "KNOWN",
            "budget_source": "CSV",
            "metadata_quality_flags": flags,
        }
    if precheck == "ZERO_SENTINEL_SUSPECT":
        flags.append("CSV_BUDGET_ZERO_SENTINEL_SUSPECT")
        contexts = [
            match.group(0)
            for match in re.finditer(
                r"사업\s*(?:예산|비|금액)\s*[:：][^\n]{0,180}", canonical, re.IGNORECASE
            )
        ]
        if any(re.search(r"비공개|공개하지\s*않", context) for context in contexts):
            return {
                "budget_amount": None,
                "budget_status": "UNDISCLOSED",
                "budget_source": "SOURCE_DOCUMENT",
                "metadata_quality_flags": flags,
            }
        for context in contexts:
            component_amounts = re.findall(
                r"(?:개발비|H\s*/?\s*W|S\s*/?\s*W)[^0-9]{0,12}"
                r"([0-9][0-9,.]*)\s*(억원|백만원|만원|천원|원)",
                context,
                re.IGNORECASE,
            )
            if len(component_amounts) >= 2:
                return {
                    "budget_amount": None,
                    "budget_status": "CONFLICT",
                    "budget_source": "SOURCE_DOCUMENT_MULTICOMPONENT_BUDGET",
                    "metadata_quality_flags": flags,
                }
        for context in contexts:
            match = re.search(
                r"(?:금\s*)?([0-9][0-9,.]*)\s*(억원|백만원|만원|천원|원)", context
            )
            if match:
                multipliers = {
                    "억원": 100_000_000,
                    "백만원": 1_000_000,
                    "만원": 10_000,
                    "천원": 1_000,
                    "원": 1,
                }
                amount = int(
                    float(match.group(1).replace(",", "")) * multipliers[match.group(2)]
                )
                return {
                    "budget_amount": amount,
                    "budget_status": "KNOWN",
                    "budget_source": "SOURCE_DOCUMENT",
                    "metadata_quality_flags": flags,
                }
    return {
        "budget_amount": None,
        "budget_status": "UNKNOWN",
        "budget_source": "CSV" if metadata else "NONE",
        "metadata_quality_flags": flags,
    }


def _validate_source_identity(
    source: Path, metadata: dict[str, str], digest: str
) -> None:
    expected_hash = metadata.get("sha256", "").strip().lower()
    if expected_hash and digest != expected_hash:
        raise ValueError(f"source SHA-256 mismatch: {source.name}")
    expected_extension = metadata.get("ext", "").strip().lower()
    if expected_extension and not expected_extension.startswith("."):
        expected_extension = f".{expected_extension}"
    if expected_extension and source.suffix.lower() != expected_extension:
        raise ValueError(f"source extension mismatch: {source.name}")
    expected_size = metadata.get("size_bytes", "").strip()
    if expected_size and source.stat().st_size != int(expected_size):
        raise ValueError(f"source size mismatch: {source.name}")


def build_document_record(
    *,
    document_id: str,
    split: str,
    metadata: dict[str, str],
    metadata_source: str,
    source: Path,
    parsed: ParseResult,
) -> dict[str, Any]:
    canonical = "\n\n".join(block.text for block in parsed.blocks)
    digest = sha256_file(source)
    _validate_source_identity(source, metadata, digest)
    original_name = (
        metadata.get("source_filename_raw")
        or metadata.get("original_name")
        or source.name
    )
    budget = _budget_contract(metadata, canonical)
    return {
        "document_id": document_id,
        "split": split,
        "content_group_id": metadata.get("content_group_id")
        or f"CG_{digest[:16].upper()}",
        "content_hash": digest,
        "source_file": source.name,
        "source_filename_raw": original_name,
        "source_filename_nfc": unicodedata.normalize("NFC", original_name),
        "file_type": source.suffix.removeprefix(".").upper(),
        "title": metadata.get("title") or source.stem,
        "agency": metadata.get("agency", ""),
        "metadata_source": metadata_source,
        **budget,
        "parser_version": parsed.parser_version,
        "parse_status": parsed.parse_status,
        "parse_warnings": list(parsed.parse_warnings),
        "parse_seconds": None,
        "source_text_version": SOURCE_TEXT_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "text_raw": canonical,
        "text_normalized": canonical,
        "text_length": len(canonical),
        "block_count": len(parsed.blocks),
        "table_record_count": parsed.table_record_count,
        "native_section_or_page_count": parsed.native_section_or_page_count,
        "skipped_inline_controls": parsed.skipped_inline_controls,
        "schema_version": "document-v0.1",
        "data_contract_version": DATA_CONTRACT_VERSION,
    }


def _normalize_split(value: str) -> str:
    split = value.strip().upper()
    if not split:
        raise ValueError("split label must not be empty")
    return split


def _validate_processed_splits(values: Iterable[str]) -> tuple[str, ...]:
    requested = {_normalize_split(value) for value in values}
    if not requested:
        raise ValueError("processed splits must not be empty")
    forbidden = requested - set(FROZEN_M2_PROCESSED_SPLITS)
    if forbidden:
        raise ValueError(
            "Frozen v0.1 M2 cannot process splits: " + ", ".join(sorted(forbidden))
        )
    return tuple(split for split in FROZEN_M2_PROCESSED_SPLITS if split in requested)


def build_dataset(
    raw_dir: Path,
    *,
    metadata_path: Path | None = None,
    default_split: str = "DEV",
    inventory_rows: list[dict[str, Any]] | None = None,
    split_assignments: list[dict[str, Any]] | None = None,
    processed_splits: Iterable[str] = FROZEN_M2_PROCESSED_SPLITS,
) -> DatasetBundle:
    """Build frozen M2 records for DEV/REGRESSION while sealing FINAL_HOLDOUT."""

    default_split = _normalize_split(default_split)
    normalized_processed_splits = _validate_processed_splits(processed_splits)
    metadata_by_name = load_metadata(metadata_path)
    inventory_by_filename = {
        metadata_alias(str(row["source_filename"])): row
        for row in (inventory_rows or [])
    }
    assignments_by_source: dict[str, dict[str, Any]] = {}
    for assignment in split_assignments or []:
        source_id = str(assignment["source_document_id"])
        if source_id in assignments_by_source:
            raise ValueError(f"duplicate split assignment: {source_id}")
        assignments_by_source[source_id] = assignment

    resolved: dict[str, dict[str, Any]] = {}
    id_sources: set[str] = set()
    for source in source_files(raw_dir):
        filename = metadata_alias(source.name)
        metadata = metadata_by_name.get(filename)
        if metadata_path is not None and metadata is None:
            raise ValueError(f"metadata missing for source: {source.name}")
        metadata = metadata or {}
        inventory_row = inventory_by_filename.get(filename)
        if inventory_rows is not None and inventory_row is None:
            raise ValueError(f"inventory missing for source: {source.name}")
        if inventory_row is not None:
            source_id = str(inventory_row["source_document_id"])
            assignment = assignments_by_source.get(source_id)
            if split_assignments is not None and assignment is None:
                raise ValueError(f"split assignment missing for source: {source_id}")
            document_id = str(inventory_row["canonical_document_id"])
            split = _normalize_split(
                str(assignment["split"])
                if assignment is not None
                else metadata.get("split") or default_split
            )
            metadata = {
                **metadata,
                "content_group_id": metadata.get("content_group_id")
                or str(inventory_row["duplicate_group_id"]),
            }
            id_sources.add(str(inventory_row.get("canonical_id_source", "MIXED")))
            digest = str(inventory_row["sha256"])
        else:
            digest = sha256_file(source)
            canonical_from_metadata = metadata.get("document_id")
            document_id = canonical_from_metadata or f"DOC_SHA256_{digest.upper()}"
            split = _normalize_split(metadata.get("split") or default_split)
            id_sources.add(
                "SOURCE_METADATA" if canonical_from_metadata else "CONTENT_SHA256"
            )
        if split not in FROZEN_SPLITS:
            raise ValueError(f"unknown Frozen v0.1 split: {split}")
        candidate = {
            "document_id": document_id,
            "source": source,
            "metadata": metadata,
            "split": split,
            "sha256": digest,
        }
        existing = resolved.get(document_id)
        if existing is not None and existing["sha256"] != digest:
            raise ValueError(
                f"canonical document maps to multiple SHA-256 values: {document_id}"
            )
        if existing is not None and existing["split"] != split:
            raise ValueError(
                f"canonical document maps to multiple splits: {document_id}"
            )
        resolved.setdefault(document_id, candidate)

    if id_sources == {"SOURCE_METADATA"}:
        document_id_mode = "SOURCE_METADATA"
    elif id_sources == {"CONTENT_SHA256"}:
        document_id_mode = "CONTENT_SHA256"
    else:
        document_id_mode = "MIXED"

    documents: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    metadata_source = metadata_path.name if metadata_path is not None else "NONE"
    unprocessed_document_ids = {
        document_id
        for document_id, item in resolved.items()
        if item["split"] in FROZEN_M2_UNPROCESSED_SPLITS
    }
    for document_id in sorted(resolved):
        item = resolved[document_id]
        source = item["source"]
        metadata = item["metadata"]
        split = item["split"]
        if split not in normalized_processed_splits:
            continue
        parsed = parse_raw_document(source)
        document = build_document_record(
            document_id=document_id,
            split=split,
            metadata=metadata,
            metadata_source=metadata_source,
            source=source,
            parsed=parsed,
        )
        document_blocks = annotate_blocks(document_id, split, parsed)
        document_chunks = build_c0(document_id, split, document_blocks)
        documents.append(document)
        blocks.extend(document_blocks)
        chunks.extend(document_chunks)

    validation = validate_dataset(
        documents,
        blocks,
        chunks,
        forbidden_document_ids=unprocessed_document_ids,
    )
    parser_by_document = {
        str(document["document_id"]): str(document["parser_version"])
        for document in documents
    }
    source_inputs = (
        [
            {
                "file_name": row["source_filename"],
                "sha256": row["sha256"],
                "parser_version": parser_by_document.get(
                    str(row["canonical_document_id"]), row["parser_version"]
                ),
            }
            for row in inventory_rows
        ]
        if inventory_rows is not None
        else [
            {
                "file_name": document["source_file"],
                "sha256": document["content_hash"],
                "parser_version": document["parser_version"],
            }
            for document in documents
        ]
    )
    split_count_rows = (
        split_assignments
        if split_assignments is not None
        else [{"split": item["split"]} for item in resolved.values()]
    )
    split_counts = {
        split: sum(
            _normalize_split(str(row["split"])) == split for row in split_count_rows
        )
        for split in FROZEN_SPLITS
    }
    return DatasetBundle(
        documents=documents,
        blocks=blocks,
        chunks=chunks,
        validation=validation,
        metadata_supplied=metadata_path is not None,
        metadata_file_name=metadata_path.name if metadata_path is not None else None,
        metadata_sha256=sha256_file(metadata_path)
        if metadata_path is not None
        else None,
        document_id_mode=document_id_mode,
        default_split=default_split,
        source_inputs=source_inputs,
        split_counts=split_counts,
        processed_splits=normalized_processed_splits,
        unprocessed_splits=FROZEN_M2_UNPROCESSED_SPLITS,
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _build_manifest(bundle: DatasetBundle, output_dir: Path) -> dict[str, Any]:
    output_names = ("documents.jsonl", "blocks.jsonl", "chunks.jsonl")
    return {
        "pipeline_version": PIPELINE_VERSION,
        "data_contract_version": DATA_CONTRACT_VERSION,
        "schema_versions": {
            "document": "document-v0.1",
            "block": "block-v0.1",
            "chunk": "chunk-v0.1",
        },
        "parser_versions": sorted(
            {str(document["parser_version"]) for document in bundle.documents}
        ),
        "chunker": {
            "version": CHUNKING_VERSION,
            "size": CHUNK_SIZE,
            "overlap": CHUNK_OVERLAP,
        },
        "inputs": bundle.source_inputs,
        "output_sha256": {
            name: sha256_file(output_dir / name) for name in output_names
        },
        "record_counts": {
            "documents": len(bundle.documents),
            "blocks": len(bundle.blocks),
            "chunks": len(bundle.chunks),
        },
        "split_counts": bundle.split_counts,
        "processed_splits": list(bundle.processed_splits),
        "unprocessed_splits": list(bundle.unprocessed_splits),
        "metadata_supplied": bundle.metadata_supplied,
        "metadata_input": (
            {
                "file_name": bundle.metadata_file_name,
                "sha256": bundle.metadata_sha256,
            }
            if bundle.metadata_supplied
            else None
        ),
        "document_id_mode": bundle.document_id_mode,
        "deterministic_build": {
            "default_split": bundle.default_split,
            "source_discovery_order": "unicode-nfc-filename-ascending",
            "record_order": "document-id-ascending",
            "json_keys": "sorted",
            "timestamp_included": False,
        },
    }


def write_dataset(
    bundle: DatasetBundle,
    output_dir: Path,
    additional_manifest_outputs: tuple[str, ...] = (),
) -> None:
    """Write deterministic JSONL outputs after the integrity gate passes."""

    if bundle.validation["status"] != "PASS":
        raise ValueError(
            f"dataset integrity validation failed: {bundle.validation['failures']}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "documents.jsonl", bundle.documents)
    _write_jsonl(output_dir / "blocks.jsonl", bundle.blocks)
    _write_jsonl(output_dir / "chunks.jsonl", bundle.chunks)
    _write_json(output_dir / "validation.json", bundle.validation)
    manifest = _build_manifest(bundle, output_dir)
    manifest["output_sha256"].update(
        {name: sha256_file(output_dir / name) for name in additional_manifest_outputs}
    )
    _write_json(output_dir / "manifest.json", manifest)
