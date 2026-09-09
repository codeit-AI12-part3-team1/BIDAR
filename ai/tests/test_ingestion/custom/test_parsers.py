from __future__ import annotations

import io
import struct
from pathlib import Path

import pymupdf
import pytest

from ai.ingestion.custom import parsers
from ai.ingestion.custom.parsers import (
    PARSER_HWP,
    PARSER_PDF,
    PARSER_PDF_FALLBACK,
    _decode_hwp_para,
    _hwp_records,
    normalize_text,
    parse_document,
)


def _hwp_payload(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}H", *values)


def _hwp_record(tag: int, level: int, payload: bytes) -> bytes:
    header = tag | (level << 10) | (len(payload) << 20)
    return struct.pack("<I", header) + payload


def test_normalize_text_uses_nfc_and_removes_unsafe_spacing() -> None:
    decomposed = "A\u1100\u1161"
    assert normalize_text(f"  {decomposed}\u3000B\n\nC\u200b  ") == "A가 B\nC"
    assert normalize_text("A\U000f02ecB") == "A B"


def test_hwp_control_safe_parser_returns_source_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = [ord("가"), 21, 1, 2, 3, 4, 5, 6, 21, ord("나"), 10, ord("다"), 13]
    body = _hwp_record(parsers.TAG_PARA_TEXT, 0, _hwp_payload(values))
    header = bytearray(40)

    class FakeContainer:
        def __enter__(self) -> FakeContainer:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def listdir(self) -> list[list[str]]:
            return [["BodyText", "Section0"]]

        def openstream(self, name: str | list[str]) -> io.BytesIO:
            if name == "FileHeader":
                return io.BytesIO(header)
            assert name == ["BodyText", "Section0"]
            return io.BytesIO(body)

    monkeypatch.setattr(parsers.olefile, "OleFileIO", lambda _: FakeContainer())

    result = parse_document(Path("sample.hwp"))

    assert result.parser_version == PARSER_HWP
    assert result.skipped_inline_controls == 1
    assert len(result.blocks) == 1
    assert result.blocks[0].text == "가 나\n다"
    assert result.blocks[0].source_section == 0


def test_pdf_parser_returns_page_provenance(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Public parser fixture")
    document.save(path)
    document.close()

    result = parse_document(path)

    assert result.parser_version == PARSER_PDF
    assert result.parse_status == "SUCCESS"
    assert result.native_section_or_page_count == 1
    assert result.blocks[0].text == "Public parser fixture"
    assert result.blocks[0].source_page == 1


def test_pdf_parser_falls_back_when_pymupdf_returns_no_blocks(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    result = parse_document(path)

    assert result.parser_version == PARSER_PDF_FALLBACK
    assert result.parse_status == "SUCCESS_WITH_WARNING"
    assert result.parse_warnings == ("PYMUPDF_NO_BLOCKS_FALLBACK_TO_PYPDF",)
    assert result.blocks == ()


def test_malformed_hwp_payload_and_record_are_rejected() -> None:
    with pytest.raises(ValueError, match="odd-sized HWP paragraph payload"):
        _decode_hwp_para(b"\x00")
    with pytest.raises(ValueError, match="truncated HWP record header"):
        _hwp_records(b"\x00")


def test_malformed_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")

    with pytest.raises(pymupdf.FileDataError):
        parse_document(path)


def test_unsupported_format_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"unsupported source type: \.txt"):
        parse_document(Path("sample.txt"))
