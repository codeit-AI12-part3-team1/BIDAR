"""Reusable parsers for raw HWP and PDF request-for-proposal documents.

The parsers return normalized primitive blocks with source locations. They do
not assign document, block, or chunk IDs and do not depend on dataset or
experiment artifacts.
"""

from __future__ import annotations

import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import olefile
import pymupdf
from pypdf import PdfReader

PARSER_HWP = "hwp5-control-safe-v0.2"
PARSER_PDF = "pymupdf-blocks-v0.1"
PARSER_PDF_FALLBACK = "pymupdf+pypdf-fallback-v0.1"
NORMALIZATION_VERSION = "unicode-nfc-whitespace-v0.1"

TAG_PARA_TEXT = 67
TAG_TABLE = 77

SEVERE_MUPDF_WARNING_RE = re.compile(
    r"invalid key in dict|cannot load object|cannot find object|object out of range",
    re.IGNORECASE,
)
LOGICAL_PAGE_MARKER_RE = re.compile(r"^-\s*\d+\s*-$")


@dataclass(frozen=True, slots=True)
class PrimitiveBlock:
    """A parser-native text block and its source location."""

    text: str
    source_page: int | None
    source_section: int | None
    source_record: int
    native_type: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Normalized primitive blocks and parser diagnostics for one document."""

    blocks: tuple[PrimitiveBlock, ...]
    parser_version: str
    parse_status: str
    parse_warnings: tuple[str, ...]
    table_record_count: int | None
    native_section_or_page_count: int
    skipped_inline_controls: int


def normalize_text(raw: str) -> str:
    """Normalize text to NFC while removing unsafe invisible/control content."""

    raw = "".join(
        " "
        if ord(character) > 0xFFFF or character == "\u3000"
        else ""
        if character == "\u200b"
        else character
        for character in raw
    )
    lines: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if line:
            lines.append(line)
    return unicodedata.normalize("NFC", "\n".join(lines))


def _decode_hwp_para(payload: bytes) -> tuple[str, int]:
    if len(payload) % 2:
        raise ValueError("odd-sized HWP paragraph payload")

    values = struct.unpack(f"<{len(payload) // 2}H", payload)
    kept: list[int] = []
    skipped = 0
    index = 0
    while index < len(values):
        value = values[index]
        if (
            value < 32
            and value != 13
            and index + 7 < len(values)
            and values[index + 7] == value
        ):
            kept.append(32)
            skipped += 1
            index += 8
            continue
        if value == 10:
            kept.append(10)
        elif value < 32 and value != 13:
            kept.append(32)
        elif value >= 32:
            kept.append(value)
        index += 1

    decoded = (
        struct.pack(f"<{len(kept)}H", *kept).decode("utf-16le", errors="replace")
        if kept
        else ""
    )
    return normalize_text(decoded), skipped


def _hwp_records(data: bytes) -> list[tuple[int, int, bytes]]:
    records: list[tuple[int, int, bytes]] = []
    position = 0
    while position < len(data):
        if position + 4 > len(data):
            raise ValueError("truncated HWP record header")
        header = struct.unpack_from("<I", data, position)[0]
        position += 4
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if position + 4 > len(data):
                raise ValueError("truncated extended HWP record size")
            size = struct.unpack_from("<I", data, position)[0]
            position += 4
        end = position + size
        if end > len(data):
            raise ValueError("truncated HWP record payload")
        records.append((tag, level, data[position:end]))
        position = end
    return records


def parse_hwp(path: Path) -> ParseResult:
    """Parse an HWP5 OLE document into normalized paragraph and table blocks."""

    blocks: list[PrimitiveBlock] = []
    table_records = 0
    skipped_controls = 0
    with olefile.OleFileIO(path) as container:
        flags = struct.unpack_from("<I", container.openstream("FileHeader").read(), 36)[
            0
        ]
        sections = sorted(
            (
                item
                for item in container.listdir()
                if len(item) == 2
                and item[0] == "BodyText"
                and item[1].startswith("Section")
            ),
            key=lambda item: int(item[1].removeprefix("Section")),
        )
        for section_path in sections:
            section = int(section_path[1].removeprefix("Section"))
            data = container.openstream(section_path).read()
            if flags & 1:
                data = zlib.decompress(data, -15)
            table: list[Any] | None = None
            for record_index, (tag, level, payload) in enumerate(_hwp_records(data)):
                table_records += int(tag == TAG_TABLE)
                if table is not None and level < int(table[1]):
                    if table[2]:
                        blocks.append(
                            PrimitiveBlock(
                                text="\n".join(table[2]),
                                source_page=None,
                                source_section=section,
                                source_record=int(table[0]),
                                native_type="TABLE",
                            )
                        )
                    table = None
                if tag == TAG_TABLE and table is None:
                    table = [record_index, level, []]
                elif tag == TAG_PARA_TEXT:
                    text, skipped = _decode_hwp_para(payload)
                    skipped_controls += skipped
                    if not text:
                        continue
                    if table is not None and level > int(table[1]):
                        table[2].append(text)
                    elif table is None:
                        blocks.append(
                            PrimitiveBlock(
                                text=text,
                                source_page=None,
                                source_section=section,
                                source_record=record_index,
                                native_type="PARAGRAPH",
                            )
                        )
            if table is not None and table[2]:
                blocks.append(
                    PrimitiveBlock(
                        text="\n".join(table[2]),
                        source_page=None,
                        source_section=section,
                        source_record=int(table[0]),
                        native_type="TABLE",
                    )
                )

    return ParseResult(
        blocks=tuple(blocks),
        parser_version=PARSER_HWP,
        parse_status="SUCCESS",
        parse_warnings=(),
        table_record_count=table_records,
        native_section_or_page_count=len(sections),
        skipped_inline_controls=skipped_controls,
    )


def _segment_pypdf_page(raw: str) -> list[str]:
    """Split a malformed PDF page on generic logical-page/table boundaries."""

    lines = raw.splitlines()
    groups: list[list[str]] = []
    current: list[str] = []
    previous_nonempty = ""
    for raw_line in lines:
        line = normalize_text(raw_line)
        if not line:
            if current:
                current.append(raw_line)
            continue
        whitespace_ratio = sum(character.isspace() for character in line) / len(line)
        starts_logical_page = bool(
            current
            and previous_nonempty.endswith(".")
            and LOGICAL_PAGE_MARKER_RE.fullmatch(line)
        )
        starts_dense_table = bool(
            current
            and previous_nonempty.endswith(".")
            and len(line) >= 75
            and whitespace_ratio < 0.20
        )
        if starts_logical_page or starts_dense_table:
            groups.append(current)
            current = []
        current.append(raw_line)
        previous_nonempty = line
    if current:
        groups.append(current)
    return [text for group in groups if (text := normalize_text("\n".join(group)))]


def _parse_pdf_pypdf(path: Path) -> ParseResult:
    reader = PdfReader(path, strict=False)
    blocks: list[PrimitiveBlock] = []
    for page_index, page in enumerate(reader.pages, start=1):
        page_parts = _segment_pypdf_page(page.extract_text() or "")
        blocks.extend(
            PrimitiveBlock(
                text=part,
                source_page=page_index,
                source_section=None,
                source_record=record_index,
                native_type="PARAGRAPH",
            )
            for record_index, part in enumerate(page_parts)
        )
    return ParseResult(
        blocks=tuple(blocks),
        parser_version=PARSER_PDF_FALLBACK,
        parse_status="SUCCESS_WITH_WARNING",
        parse_warnings=("PYMUPDF_NO_BLOCKS_FALLBACK_TO_PYPDF",),
        table_record_count=None,
        native_section_or_page_count=len(reader.pages),
        skipped_inline_controls=0,
    )


def parse_pdf(path: Path) -> ParseResult:
    """Parse a PDF with PyMuPDF and fall back to pypdf for malformed layouts."""

    pymupdf.TOOLS.reset_mupdf_warnings()
    document = pymupdf.open(path)
    blocks: list[PrimitiveBlock] = []
    try:
        for page_index, page in enumerate(document, start=1):
            for native in page.get_text("blocks", sort=True):
                text = normalize_text(str(native[4]))
                if text:
                    blocks.append(
                        PrimitiveBlock(
                            text=text,
                            source_page=page_index,
                            source_section=None,
                            source_record=int(native[5]),
                            native_type="PARAGRAPH",
                        )
                    )
        page_count = len(document)
    finally:
        document.close()

    warnings = pymupdf.TOOLS.mupdf_warnings()
    if not blocks or SEVERE_MUPDF_WARNING_RE.search(warnings):
        return _parse_pdf_pypdf(path)
    return ParseResult(
        blocks=tuple(blocks),
        parser_version=PARSER_PDF,
        parse_status="SUCCESS",
        parse_warnings=(),
        table_record_count=None,
        native_section_or_page_count=page_count,
        skipped_inline_controls=0,
    )


def parse_document(path: Path) -> ParseResult:
    """Parse a supported raw document based on its case-insensitive suffix."""

    suffix = path.suffix.lower()
    if suffix == ".hwp":
        return parse_hwp(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"unsupported source type: {path.suffix}")
