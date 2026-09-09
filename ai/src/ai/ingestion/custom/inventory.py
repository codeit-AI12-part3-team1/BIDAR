"""Deterministic source inventory without raw text or local paths."""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

from ai.ingestion.custom.parsers import PARSER_HWP, PARSER_PDF

SUPPORTED_SUFFIXES = {".hwp", ".pdf"}
METADATA_FILENAME_FIELDS = (
    "short_name",
    "source_file",
    "source_filename_raw",
    "original_name",
    "filename",
)
INVENTORY_FIELDS = (
    "source_document_id",
    "canonical_document_id",
    "source_filename",
    "file_type",
    "file_size",
    "sha256",
    "duplicate_group_id",
    "parse_status",
    "parser_version",
    "bid_notice_no",
    "title",
    "agency",
    "metadata_identity",
    "canonical_id_source",
)


def sha256_file(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata_alias(value: str) -> str:
    return unicodedata.normalize("NFC", Path(value).name.strip())


def load_metadata(source: Path | None) -> dict[str, dict[str, str]]:
    """Load optional CSV metadata keyed by supported filename aliases."""

    if source is None:
        return {}
    aliases: dict[str, dict[str, str]] = {}
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("metadata CSV has no header")
        for row_number, row in enumerate(reader, start=2):
            row_aliases = {
                metadata_alias(row[field])
                for field in METADATA_FILENAME_FIELDS
                if row.get(field, "").strip()
            }
            if not row_aliases:
                raise ValueError(f"metadata row {row_number} has no source filename")
            for alias in row_aliases:
                if alias in aliases:
                    raise ValueError(f"duplicate metadata source alias: {alias}")
                aliases[alias] = row
    return aliases


def source_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.is_dir():
        raise ValueError(f"raw directory does not exist: {raw_dir}")
    sources = sorted(
        (
            source
            for source in raw_dir.iterdir()
            if source.is_file() and source.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda source: (unicodedata.normalize("NFC", source.name), source.name),
    )
    if not sources:
        raise ValueError("raw directory has no supported HWP/PDF files")
    return sources


def _stable_source_id(filename: str, digest: str) -> str:
    identity = hashlib.sha256(f"{filename}\0{digest}".encode()).hexdigest().upper()
    return f"SRC_{identity}"


def build_inventory(
    raw_dir: Path, metadata_path: Path | None = None
) -> list[dict[str, Any]]:
    """Inventory every source row and group identical binary content."""

    metadata_by_name = load_metadata(metadata_path)
    inventory: list[dict[str, Any]] = []
    for source in source_files(raw_dir):
        filename = unicodedata.normalize("NFC", source.name)
        metadata = metadata_by_name.get(filename)
        if metadata_path is not None and metadata is None:
            raise ValueError(f"metadata missing for source: {source.name}")
        metadata = metadata or {}
        digest = sha256_file(source)
        canonical_from_metadata = metadata.get("canonical_document_id") or metadata.get(
            "document_id"
        )
        canonical_document_id = (
            canonical_from_metadata or f"DOC_SHA256_{digest.upper()}"
        )
        inventory.append(
            {
                "source_document_id": metadata.get("source_document_id")
                or _stable_source_id(filename, digest),
                "canonical_document_id": canonical_document_id,
                "source_filename": filename,
                "file_type": source.suffix.removeprefix(".").upper(),
                "file_size": source.stat().st_size,
                "sha256": digest,
                "duplicate_group_id": metadata.get("duplicate_group_id")
                or metadata.get("content_group_id")
                or f"DUP_SHA256_{digest.upper()}",
                "parse_status": "NOT_RUN",
                "parser_version": PARSER_HWP
                if source.suffix.lower() == ".hwp"
                else PARSER_PDF,
                "bid_notice_no": metadata.get("bid_notice_no")
                or metadata.get("bidNtceNo", ""),
                "title": metadata.get("title", ""),
                "agency": metadata.get("agency", ""),
                "metadata_identity": metadata.get("source_metadata_identity")
                or metadata.get("metadata_id")
                or metadata.get("bid_notice_no")
                or metadata.get("bidNtceNo", ""),
                "canonical_id_source": (
                    "SOURCE_METADATA" if canonical_from_metadata else "CONTENT_SHA256"
                ),
            }
        )
    return inventory


def apply_parse_results(
    inventory: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach canonical parse results without adding text or local paths."""

    by_document = {str(row["document_id"]): row for row in documents}
    return [
        {
            **row,
            "parse_status": by_document.get(str(row["canonical_document_id"]), {}).get(
                "parse_status", "NOT_RUN"
            ),
            "parser_version": by_document.get(
                str(row["canonical_document_id"]), {}
            ).get("parser_version", row["parser_version"]),
        }
        for row in inventory
    ]


def _write_jsonl(destination: Path, rows: list[dict[str, Any]]) -> None:
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_inventory(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _write_jsonl(output_dir / "inventory.jsonl", rows)
