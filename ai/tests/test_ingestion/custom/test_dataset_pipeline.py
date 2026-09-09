from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from ai.ingestion.custom.chunking import CHUNK_OVERLAP, CHUNK_SIZE, build_c0
from ai.ingestion.custom.dataset_builder import (
    annotate_blocks,
    build_dataset,
    write_dataset,
)
from ai.ingestion.custom.inventory import (
    apply_parse_results,
    build_inventory,
    sha256_file,
    write_inventory,
)
from ai.ingestion.custom.parsers import PARSER_PDF, ParseResult, PrimitiveBlock
from ai.ingestion.custom.splitting import (
    assign_splits,
    load_split_config,
    write_splits,
)
from ai.ingestion.custom.validation import (
    combine_validation,
    validate_dataset,
    validate_splits,
)

SPLIT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "data" / "custom_split_v0.1.json"
)


def _write_synthetic_pdf(path: Path, label: str = "Synthetic public RFP") -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), label)
    page.insert_text((72, 100), "SFR-001 Synthetic requirement")
    document.save(path)
    document.close()


def _write_metadata(path: Path, source: Path) -> None:
    fields = (
        "short_name",
        "source_document_id",
        "canonical_document_id",
        "document_id",
        "content_group_id",
        "sha256",
        "ext",
        "size_bytes",
        "original_name",
        "agency",
        "title",
        "budget",
        "budget_status_precheck",
        "split",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "short_name": source.name,
                "source_document_id": "SRC_SYNTHETIC_001",
                "canonical_document_id": "DOC_SYNTHETIC_001",
                "document_id": "DOC_SYNTHETIC_001",
                "content_group_id": "CG_SYNTHETIC_001",
                "sha256": sha256_file(source),
                "ext": ".pdf",
                "size_bytes": source.stat().st_size,
                "original_name": "synthetic-rfp.pdf",
                "agency": "Synthetic Agency",
                "title": "Synthetic RFP",
                "budget": "1000000",
                "budget_status_precheck": "PRESENT_NONZERO",
                "split": "DEV",
            }
        )


def _run_pipeline(
    raw_dir: Path,
    output_dir: Path,
    *,
    metadata: Path | None = None,
    frozen_mapping: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    inventory = build_inventory(raw_dir, metadata)
    config = load_split_config(SPLIT_CONFIG_PATH)
    assignments, report = assign_splits(inventory, config, frozen_mapping)
    split_validation = validate_splits(inventory, assignments, config.splits)
    assert split_validation["status"] == "PASS"
    bundle = build_dataset(
        raw_dir,
        metadata_path=metadata,
        default_split=next(iter(config.splits)),
        inventory_rows=inventory,
        split_assignments=assignments,
    )
    bundle = replace(
        bundle,
        validation=combine_validation(bundle.validation, split_validation),
    )
    inventory = apply_parse_results(inventory, bundle.documents)
    write_inventory(inventory, output_dir)
    write_splits(assignments, report, split_validation, output_dir)
    write_dataset(
        bundle,
        output_dir,
        additional_manifest_outputs=(
            "inventory.csv",
            "inventory.jsonl",
            "split.csv",
            "split.json",
        ),
    )
    return inventory, assignments, report


def test_raw_pdf_pipeline_is_deterministic(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = raw_dir / "synthetic.pdf"
    metadata = tmp_path / "metadata.csv"
    _write_synthetic_pdf(source)
    _write_metadata(metadata, source)

    output_a = tmp_path / "output-a"
    output_b = tmp_path / "output-b"
    frozen_mapping = [{"source_document_id": "SRC_SYNTHETIC_001", "split": "DEV"}]
    first_inventory, first_assignments, first_report = _run_pipeline(
        raw_dir, output_a, metadata=metadata, frozen_mapping=frozen_mapping
    )
    second_inventory, second_assignments, second_report = _run_pipeline(
        raw_dir, output_b, metadata=metadata, frozen_mapping=frozen_mapping
    )

    assert first_inventory == second_inventory
    assert first_assignments == second_assignments
    assert first_report == second_report
    assert first_report["mode"] == "FROZEN_MAPPING"
    assert first_inventory[0]["parse_status"] == "SUCCESS"
    for filename in (
        "inventory.csv",
        "inventory.jsonl",
        "split.csv",
        "split.json",
        "documents.jsonl",
        "blocks.jsonl",
        "chunks.jsonl",
        "validation.json",
        "manifest.json",
    ):
        assert (output_a / filename).read_bytes() == (output_b / filename).read_bytes()

    manifest = json.loads((output_a / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata_supplied"] is True
    assert manifest["metadata_input"] == {
        "file_name": metadata.name,
        "sha256": sha256_file(metadata),
    }
    assert manifest["document_id_mode"] == "SOURCE_METADATA"
    assert manifest["chunker"] == {
        "version": "fixed-char-1200-o200-v0.1",
        "size": 1200,
        "overlap": 200,
    }
    assert manifest["split_counts"] == {
        "DEV": 1,
        "REGRESSION": 0,
        "FINAL_HOLDOUT": 0,
    }
    assert manifest["processed_splits"] == ["DEV", "REGRESSION"]
    assert manifest["unprocessed_splits"] == ["FINAL_HOLDOUT"]
    for filename in (
        "inventory.csv",
        "inventory.jsonl",
        "split.csv",
        "split.json",
        "documents.jsonl",
        "blocks.jsonl",
        "chunks.jsonl",
    ):
        assert manifest["output_sha256"][filename] == sha256_file(output_a / filename)


def test_inventory_and_group_aware_split_are_deterministic(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    first_source = raw_dir / "a.pdf"
    duplicate_source = raw_dir / "b.pdf"
    unique_source = raw_dir / "c.pdf"
    _write_synthetic_pdf(first_source, "Synthetic group A")
    duplicate_source.write_bytes(first_source.read_bytes())
    _write_synthetic_pdf(unique_source, "Synthetic group B")

    first_inventory = build_inventory(raw_dir)
    second_inventory = build_inventory(raw_dir)
    config = load_split_config(SPLIT_CONFIG_PATH)
    first_assignments, first_report = assign_splits(first_inventory, config)
    second_assignments, second_report = assign_splits(second_inventory, config)

    assert first_inventory == second_inventory
    assert [row["source_filename"] for row in first_inventory] == [
        "a.pdf",
        "b.pdf",
        "c.pdf",
    ]
    assert first_inventory[0]["sha256"] == first_inventory[1]["sha256"]
    assert (
        first_inventory[0]["duplicate_group_id"]
        == first_inventory[1]["duplicate_group_id"]
    )
    assert (
        first_inventory[0]["canonical_document_id"]
        == first_inventory[1]["canonical_document_id"]
    )
    assert (
        first_inventory[0]["source_document_id"]
        != first_inventory[1]["source_document_id"]
    )
    assert first_assignments == second_assignments
    assert first_report == second_report
    assert first_report["mode"] == "DETERMINISTIC_GROUP_AWARE"
    assert set(first_report["target_vs_actual"]) == {
        "DEV",
        "REGRESSION",
        "FINAL_HOLDOUT",
    }
    assert {
        name: values["actual_count"]
        for name, values in first_report["target_vs_actual"].items()
    } == {"DEV": 2, "REGRESSION": 1, "FINAL_HOLDOUT": 0}
    split_validation = validate_splits(
        first_inventory, first_assignments, config.splits
    )
    assert split_validation["status"] == "PASS"
    assert split_validation["sha_cross_split_leakage"] == {}
    assert split_validation["duplicate_group_cross_split_leakage"] == {}
    assert first_assignments[0]["split"] == first_assignments[1]["split"]

    bundle = build_dataset(
        raw_dir,
        inventory_rows=first_inventory,
        split_assignments=first_assignments,
    )
    assert bundle.validation["status"] == "PASS"
    assert bundle.document_id_mode == "CONTENT_SHA256"
    assert len(bundle.documents) == 2


def test_final_holdout_is_assigned_but_sealed_at_m2(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_synthetic_pdf(raw_dir / "dev.pdf", "Synthetic DEV")
    _write_synthetic_pdf(raw_dir / "regression.pdf", "Synthetic REGRESSION")
    (raw_dir / "final-holdout.pdf").write_bytes(b"not a parseable PDF")

    inventory = build_inventory(raw_dir)
    split_by_filename = {
        "dev.pdf": "DEV",
        "regression.pdf": "REGRESSION",
        "final-holdout.pdf": "FINAL_HOLDOUT",
    }
    frozen_mapping = [
        {
            "source_document_id": str(row["source_document_id"]),
            "split": split_by_filename[str(row["source_filename"])],
        }
        for row in inventory
    ]
    config = load_split_config(SPLIT_CONFIG_PATH)
    assignments, _ = assign_splits(inventory, config, frozen_mapping)
    split_validation = validate_splits(inventory, assignments, config.splits)
    assert split_validation["status"] == "PASS"
    assert split_validation["sha_cross_split_leakage"] == {}
    assert split_validation["duplicate_group_cross_split_leakage"] == {}

    bundle = build_dataset(
        raw_dir,
        inventory_rows=inventory,
        split_assignments=assignments,
    )
    assert len(inventory) == len(assignments) == 3
    assert {document["split"] for document in bundle.documents} == {
        "DEV",
        "REGRESSION",
    }
    final_document_id = next(
        str(row["canonical_document_id"])
        for row in inventory
        if row["source_filename"] == "final-holdout.pdf"
    )
    assert all(
        row["document_id"] != final_document_id
        for rows in (bundle.documents, bundle.blocks, bundle.chunks)
        for row in rows
    )
    updated_inventory = apply_parse_results(inventory, bundle.documents)
    final_inventory_row = next(
        row
        for row in updated_inventory
        if row["source_filename"] == "final-holdout.pdf"
    )
    assert final_inventory_row["parse_status"] == "NOT_RUN"
    assert bundle.split_counts == {
        "DEV": 1,
        "REGRESSION": 1,
        "FINAL_HOLDOUT": 1,
    }

    with pytest.raises(ValueError, match="cannot process splits: FINAL_HOLDOUT"):
        build_dataset(
            raw_dir,
            inventory_rows=inventory,
            split_assignments=assignments,
            processed_splits=("DEV", "REGRESSION", "FINAL_HOLDOUT"),
        )


def test_validation_rejects_sealed_document_artifacts(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_synthetic_pdf(raw_dir / "synthetic.pdf")
    bundle = build_dataset(raw_dir)
    sealed_document_id = str(bundle.documents[0]["document_id"])

    result = validate_dataset(
        bundle.documents,
        bundle.blocks,
        bundle.chunks,
        forbidden_document_ids={sealed_document_id},
    )

    assert result["status"] == "FAIL"
    violations = result["final_holdout_artifact_violations"]
    assert any(value.startswith("final_holdout_document:") for value in violations)
    assert any(value.startswith("final_holdout_block:") for value in violations)
    assert any(value.startswith("final_holdout_chunk:") for value in violations)


def test_split_validation_and_invalid_config_fail_closed(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    first_source = raw_dir / "a.pdf"
    duplicate_source = raw_dir / "b.pdf"
    _write_synthetic_pdf(first_source)
    duplicate_source.write_bytes(first_source.read_bytes())
    inventory = build_inventory(raw_dir)
    config = load_split_config(SPLIT_CONFIG_PATH)
    assignments, _ = assign_splits(inventory, config)

    missing = validate_splits(inventory, assignments[:-1])
    duplicated = validate_splits(inventory, [*assignments, assignments[0]])
    leaking_assignments = [dict(row) for row in assignments]
    leaking_assignments[1]["split"] = "ISOLATED"
    leaking = validate_splits(inventory, leaking_assignments, config.splits)
    unknown = validate_splits(
        inventory,
        [
            *assignments,
            {
                **assignments[0],
                "source_document_id": "SRC_UNKNOWN",
            },
        ],
        config.splits,
    )

    assert missing["status"] == "FAIL" and missing["unassigned_documents"]
    assert duplicated["status"] == "FAIL" and duplicated["duplicate_assignments"]
    assert leaking["status"] == "FAIL" and leaking["sha_cross_split_leakage"]
    assert leaking["duplicate_group_cross_split_leakage"]
    assert unknown["status"] == "FAIL" and unknown["unknown_document_ids"]

    invalid_config = tmp_path / "invalid-split.json"
    invalid_config.write_text(
        json.dumps(
            {
                "version": "invalid",
                "splits": {
                    "DEV": 0.8,
                    "REGRESSION": 0.15,
                    "FINAL_HOLDOUT": 0.15,
                },
                "seed": 1,
                "group_by": "duplicate_group_id",
                "prevent_cross_split_sha": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_split_config(invalid_config)


def test_c0_uses_frozen_window_and_provenance() -> None:
    text = "SFR-001 " + "A" * (CHUNK_SIZE + 80)
    parsed = ParseResult(
        blocks=(PrimitiveBlock(text, 2, None, 0, "PARAGRAPH"),),
        parser_version=PARSER_PDF,
        parse_status="SUCCESS",
        parse_warnings=(),
        table_record_count=None,
        native_section_or_page_count=1,
        skipped_inline_controls=0,
    )
    blocks = annotate_blocks("DOC_SYNTHETIC_002", "DEV", parsed)
    chunks = build_c0("DOC_SYNTHETIC_002", "DEV", blocks)

    assert len(chunks) == 2
    assert chunks[0]["char_end"] - chunks[1]["char_start"] == CHUNK_OVERLAP
    assert chunks[1]["block_ids"] == ["DOC_SYNTHETIC_002-B00000"]
    assert chunks[1]["page_start"] == chunks[1]["page_end"] == 2
    assert chunks[1]["requirement_ids"] == ["SFR-001"]


def test_frozen_requirement_recognizer_preserves_legacy_network_match() -> None:
    parsed = ParseResult(
        blocks=(
            PrimitiveBlock(
                "ECR-03\n1G BASE-T x 24포트\n- 208 Gbps",
                None,
                0,
                0,
                "TABLE",
            ),
        ),
        parser_version="hwp5-control-safe-v0.2",
        parse_status="SUCCESS",
        parse_warnings=(),
        table_record_count=1,
        native_section_or_page_count=1,
        skipped_inline_controls=0,
    )

    block = annotate_blocks("DOC_SYNTHETIC_003", "DEV", parsed)[0]

    assert block["requirement_ids"] == ["ECR-003", "BASE-208"]


def test_validation_rejects_broken_chunk_fk(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = raw_dir / "synthetic.pdf"
    _write_synthetic_pdf(source)
    bundle = build_dataset(raw_dir, default_split="DEV")
    assert bundle.metadata_supplied is False
    assert bundle.document_id_mode == "CONTENT_SHA256"
    assert bundle.documents[0]["document_id"].startswith("DOC_SHA256_")
    assert bundle.documents[0]["split"] == "DEV"
    chunks = json.loads(json.dumps(bundle.chunks))
    chunks[0]["block_ids"] = ["DOC_UNKNOWN-B00000"]

    result = validate_dataset(bundle.documents, bundle.blocks, chunks)

    assert result["status"] == "FAIL"
    assert any(
        failure.startswith("block_provenance:") for failure in result["failures"]
    )
    assert any(failure.startswith("chunk_block_fk:") for failure in result["failures"])
