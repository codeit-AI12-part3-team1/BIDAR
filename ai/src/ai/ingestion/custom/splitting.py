"""Deterministic group-aware split allocation and collaboration artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SPLIT_FIELDS = (
    "source_document_id",
    "canonical_document_id",
    "duplicate_group_id",
    "sha256",
    "split",
    "source_filename",
)
CANONICAL_SPLITS = {"DEV", "REGRESSION", "FINAL_HOLDOUT"}


@dataclass(frozen=True, slots=True)
class SplitConfig:
    version: str
    splits: dict[str, float]
    seed: int
    group_by: str
    prevent_cross_split_sha: bool


def load_split_config(source: Path) -> SplitConfig:
    raw = json.loads(source.read_text(encoding="utf-8"))
    splits = raw.get("splits")
    if not isinstance(splits, dict) or not splits:
        raise ValueError("split config requires a non-empty splits object")
    normalized: dict[str, float] = {}
    for name, ratio in splits.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("split names must be non-empty strings")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 0:
            raise ValueError(f"invalid split ratio: {name}")
        normalized[name.strip().upper()] = float(ratio)
    if not math.isclose(sum(normalized.values()), 1.0, abs_tol=1e-9):
        raise ValueError("split ratios must sum to 1.0")
    if set(normalized) != CANONICAL_SPLITS:
        raise ValueError("split config must define DEV, REGRESSION, and FINAL_HOLDOUT")
    seed = raw.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("split seed must be an integer")
    if raw.get("group_by") != "duplicate_group_id":
        raise ValueError("split group_by must be duplicate_group_id")
    if raw.get("prevent_cross_split_sha") is not True:
        raise ValueError("prevent_cross_split_sha must be true")
    version = raw.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("split config version is required")
    return SplitConfig(
        version=version,
        splits=normalized,
        seed=seed,
        group_by="duplicate_group_id",
        prevent_cross_split_sha=True,
    )


def load_frozen_split(source: Path) -> list[dict[str, Any]]:
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    raw = json.loads(source.read_text(encoding="utf-8"))
    rows = raw.get("assignments") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("frozen split must contain an assignment list")
    return rows


def _assignment(row: dict[str, Any], split: str) -> dict[str, Any]:
    return {
        "source_document_id": row["source_document_id"],
        "canonical_document_id": row["canonical_document_id"],
        "duplicate_group_id": row["duplicate_group_id"],
        "sha256": row["sha256"],
        "split": split.strip().upper(),
        "source_filename": row["source_filename"],
    }


def _allocation_groups(inventory: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parent = list(range(len(inventory)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for field in ("sha256", "duplicate_group_id"):
        first_index: dict[str, int] = {}
        for index, row in enumerate(inventory):
            value = str(row[field])
            if value in first_index:
                union(first_index[value], index)
            else:
                first_index[value] = index

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(inventory):
        groups.setdefault(find(index), []).append(row)
    return list(groups.values())


def _target_report(
    assignments: list[dict[str, Any]], config: SplitConfig, mode: str
) -> dict[str, Any]:
    total = len(assignments)
    actual = {
        name: sum(row["split"] == name for row in assignments) for name in config.splits
    }
    return {
        "config_version": config.version,
        "mode": mode,
        "seed": config.seed,
        "allocation_objective": "minimum-total-absolute-count-difference",
        "target_vs_actual": {
            name: {
                "target_count": round(total * ratio, 6),
                "actual_count": actual[name],
                "difference": round(actual[name] - total * ratio, 6),
            }
            for name, ratio in config.splits.items()
        },
    }


def assign_splits(
    inventory: list[dict[str, Any]],
    config: SplitConfig,
    frozen_mapping: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply an authoritative mapping or allocate SHA/group components deterministically."""

    if frozen_mapping is not None:
        by_source = {str(row["source_document_id"]): row for row in inventory}
        by_canonical: dict[str, list[dict[str, Any]]] = {}
        for row in inventory:
            by_canonical.setdefault(str(row["canonical_document_id"]), []).append(row)
        assignments: list[dict[str, Any]] = []
        for frozen in frozen_mapping:
            source_id = str(frozen.get("source_document_id", ""))
            canonical_id = str(
                frozen.get("canonical_document_id") or frozen.get("document_id") or ""
            )
            split = str(frozen.get("split", ""))
            targets = [by_source[source_id]] if source_id in by_source else []
            if not targets and canonical_id in by_canonical:
                targets = by_canonical[canonical_id]
            if targets:
                assignments.extend(_assignment(row, split) for row in targets)
            else:
                assignments.append(
                    {
                        "source_document_id": source_id or canonical_id,
                        "canonical_document_id": canonical_id,
                        "duplicate_group_id": str(frozen.get("duplicate_group_id", "")),
                        "sha256": str(frozen.get("sha256", "")),
                        "split": split.strip().upper(),
                        "source_filename": str(frozen.get("source_filename", "")),
                    }
                )
        assignments.sort(key=lambda row: str(row["source_document_id"]))
        return assignments, _target_report(assignments, config, "FROZEN_MAPPING")

    groups = _allocation_groups(inventory)
    groups.sort(
        key=lambda rows: (
            -len(rows),
            hashlib.sha256(
                f"{config.seed}:{min(str(row['source_document_id']) for row in rows)}".encode()
            ).hexdigest(),
        )
    )
    targets = {name: len(inventory) * ratio for name, ratio in config.splits.items()}
    split_names = list(config.splits)
    states: dict[tuple[int, int], tuple[int, ...]] = {(0, 0): ()}
    for rows in groups:
        next_states: dict[tuple[int, int], tuple[int, ...]] = {}
        for counts, choices in states.items():
            for split_index in range(len(split_names)):
                next_counts = list(counts)
                if split_index < 2:
                    next_counts[split_index] += len(rows)
                state = tuple(next_counts)
                candidate = (*choices, split_index)
                if state not in next_states or candidate < next_states[state]:
                    next_states[state] = candidate
        states = next_states

    total = len(inventory)
    _, selected = min(
        states.items(),
        key=lambda item: (
            sum(
                abs(actual - targets[name])
                for name, actual in zip(
                    split_names,
                    (*item[0], total - sum(item[0])),
                    strict=True,
                )
            ),
            item[1],
        ),
    )
    group_splits: dict[str, str] = {}
    for rows, split_index in zip(groups, selected, strict=True):
        choice = split_names[split_index]
        for row in rows:
            group_splits[str(row["source_document_id"])] = choice
    assignments = [
        _assignment(row, group_splits[str(row["source_document_id"])])
        for row in inventory
    ]
    return assignments, _target_report(assignments, config, "DETERMINISTIC_GROUP_AWARE")


def write_splits(
    assignments: list[dict[str, Any]],
    report: dict[str, Any],
    validation: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "split.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SPLIT_FIELDS)
        writer.writeheader()
        writer.writerows(assignments)
    (output_dir / "split.json").write_text(
        json.dumps(
            {**report, "assignments": assignments, "validation": validation},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
