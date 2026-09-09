"""Build the frozen v0.1 baseline dataset records from raw HWP/PDF files."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from ai.ingestion.custom.dataset_builder import build_dataset, write_dataset
from ai.ingestion.custom.inventory import (
    apply_parse_results,
    build_inventory,
    write_inventory,
)
from ai.ingestion.custom.splitting import (
    assign_splits,
    load_frozen_split,
    load_split_config,
    write_splits,
)
from ai.ingestion.custom.validation import combine_validation, validate_splits

DEFAULT_SPLIT_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "data" / "custom_split_v0.1.json"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic inventory, leakage-safe splits, and frozen v0.1 "
            "M0-M2 JSONL records for DEV and REGRESSION."
        ),
        epilog=(
            "Exact RFP100 v0.1 reproduction requires both the original metadata/ID "
            "mapping and --frozen-split. Without them, content-stable IDs and a "
            "deterministic group-aware split are generated for new sources. "
            "FINAL_HOLDOUT remains inventoried and assigned but is not parsed, "
            "canonicalized, or chunked at M2."
        ),
    )
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument(
        "--metadata",
        type=Path,
        help="optional source metadata and canonical ID mapping CSV",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--split-config",
        default=DEFAULT_SPLIT_CONFIG,
        type=Path,
        help="group-aware split policy JSON",
    )
    parser.add_argument(
        "--frozen-split",
        type=Path,
        help="authoritative CSV/JSON split mapping; disables generated allocation",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    inventory = build_inventory(args.raw_dir, args.metadata)
    split_config = load_split_config(args.split_config)
    frozen_mapping = (
        load_frozen_split(args.frozen_split) if args.frozen_split is not None else None
    )
    assignments, split_report = assign_splits(
        inventory, split_config, frozen_mapping=frozen_mapping
    )
    split_validation = validate_splits(inventory, assignments, split_config.splits)
    if split_validation["status"] != "PASS":
        raise ValueError(f"split validation failed: {split_validation['failures']}")

    bundle = build_dataset(
        args.raw_dir,
        metadata_path=args.metadata,
        default_split=next(iter(split_config.splits)),
        inventory_rows=inventory,
        split_assignments=assignments,
    )
    combined_validation = combine_validation(bundle.validation, split_validation)
    if combined_validation["status"] != "PASS":
        raise ValueError(
            f"pipeline validation failed: {combined_validation['failures']}"
        )
    bundle = replace(bundle, validation=combined_validation)
    inventory = apply_parse_results(inventory, bundle.documents)
    write_inventory(inventory, args.output_dir)
    write_splits(assignments, split_report, split_validation, args.output_dir)
    write_dataset(
        bundle,
        args.output_dir,
        additional_manifest_outputs=(
            "inventory.csv",
            "inventory.jsonl",
            "split.csv",
            "split.json",
        ),
    )
    print(
        f"PASS sources={len(inventory)} documents={len(bundle.documents)} "
        f"blocks={len(bundle.blocks)} chunks={len(bundle.chunks)} "
        f"split_mode={split_report['mode'].lower()} "
        f"id_mode={bundle.document_id_mode.lower()} output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
