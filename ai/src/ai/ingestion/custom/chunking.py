"""Deterministic C0 character chunking for the frozen data contract v0.1."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
CHUNK_STRIDE = CHUNK_SIZE - CHUNK_OVERLAP
CHUNKING_VERSION = "fixed-char-1200-o200-v0.1"
DATA_CONTRACT_VERSION = "FROZEN_v0.1"
SOURCE_TEXT_VERSION = "canonical_text_v0.1"
SECTION_PATH_MAX_VALUES = 6


def build_c0(
    document_id: str,
    split: str,
    blocks: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build C0 chunks and inherit exact block, section, requirement, and page provenance."""

    canonical = "\n\n".join(str(block["text_raw"]) for block in blocks)
    chunks: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(canonical), CHUNK_STRIDE)):
        end = min(len(canonical), start + CHUNK_SIZE)
        related = [
            block
            for block in blocks
            if int(block["char_start"]) < end and int(block["char_end"]) > start
        ]
        sections = list(
            dict.fromkeys(value for block in related for value in block["section_path"])
        )[:SECTION_PATH_MAX_VALUES]
        requirements = list(
            dict.fromkeys(
                value for block in related for value in block["requirement_ids"]
            )
        )
        pages = [
            int(block["source_page"])
            for block in related
            if block["source_page"] is not None
        ]
        chunks.append(
            {
                "chunk_id": f"{document_id}-C{index:05d}",
                "document_id": document_id,
                "split": split,
                "chunk_index": index,
                "chunking_version": CHUNKING_VERSION,
                "text": canonical[start:end],
                "section_path": sections,
                "block_ids": [block["block_id"] for block in related],
                "requirement_ids": requirements,
                "char_start": start,
                "char_end": end,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "source_text_version": SOURCE_TEXT_VERSION,
                "schema_version": "chunk-v0.1",
                "data_contract_version": DATA_CONTRACT_VERSION,
            }
        )
        if end == len(canonical):
            break
    return chunks
