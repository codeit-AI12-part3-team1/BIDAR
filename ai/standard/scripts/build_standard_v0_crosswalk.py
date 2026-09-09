"""
STANDARD_V0_SPLIT_70_15_15_v0.1 crosswalk 생성 스크립트

입력:
  - RFP100_split_v0.1.csv          (document_id/sha256/공고번호/content_group_id/split, SSOT 상세 매핑)
  - RFP100_splits_v0.1.json        (split 배정/정책 SSOT, 교차검증용)
  - standard_v0_baseline/dataset/documents.jsonl  (canonical_doc_id 원천, file_sha256으로 조인)

출력:
  - governance/standard_v0_split_crosswalk_v0.1.jsonl  (document_id ↔ canonical_doc_id ↔ 공고번호 ↔ content_group_id ↔ split)
  - governance/standard_v0_split_validation_v0.1.json  (leakage/join 검증 결과)

매핑 기준: 동일 원본 파일의 SHA-256 (01_STANDARD_DATASET_TO_EXISTING_RAG_COMPAT_GUIDE_v0.1.md 4절 1순위 기준).
"""
import csv
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEMANTIC_ROLE = {
    "DEV": "DEV",
    "REGRESSION": "VAL",
    "FINAL_HOLDOUT": "STANDARD_HOLDOUT",
}


def load_csv_rows():
    with open(f"{ROOT}\\RFP100_split_v0.1.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_split_policy():
    with open(f"{ROOT}\\RFP100_splits_v0.1.json", encoding="utf-8") as f:
        return json.load(f)


def load_standard_documents():
    docs = []
    with open(f"{ROOT}\\standard_v0_baseline\\dataset\\documents.jsonl", encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line))
    return docs


def main():
    csv_rows = load_csv_rows()
    split_policy = load_split_policy()
    std_docs = load_standard_documents()

    def clean(v):
        """standard documents.jsonl은 결측을 JSON 확장 NaN(float)으로 담는 경우가 있어 None으로 통일."""
        if v is None:
            return None
        if isinstance(v, float) and v != v:  # NaN
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # sha256 -> standard 문서 레코드 (canonical_doc_id, 공고번호 등)
    sha_to_std = {}
    for d in std_docs:
        sha_to_std.setdefault(d["file_sha256"], []).append(d)

    # --- 1. csv <-> json split 배정 일치 검증 ---
    json_split = {}
    for split_name, doc_ids in split_policy["documents"].items():
        for doc_id in doc_ids:
            json_split[doc_id] = split_name

    split_mismatch = []
    for row in csv_rows:
        did = row["document_id"]
        if json_split.get(did) != row["split"]:
            split_mismatch.append(
                {"document_id": did, "csv_split": row["split"], "json_split": json_split.get(did)}
            )

    # --- 2. crosswalk 생성 (sha256 join) ---
    crosswalk = []
    unresolved = []
    for row in csv_rows:
        sha = row["sha256"]
        std_matches = sha_to_std.get(sha, [])
        canonical_ids = {m["canonical_doc_id"] for m in std_matches}
        is_duplicate_content_group = len(std_matches) > 1

        if len(canonical_ids) == 1:
            # canonical_doc_id는 sha256에서 결정론적으로 파생되므로, 동일 sha256을 가진
            # standard 레코드가 여러 건이어도 canonical_doc_id 자체는 모호하지 않다.
            match_status = "EXACT"
            canonical_doc_id = next(iter(canonical_ids))
        elif len(canonical_ids) > 1:
            match_status = "NEEDS_REVIEW"
            canonical_doc_id = sorted(canonical_ids)[0]
            unresolved.append({"document_id": row["document_id"], "reason": "conflicting_canonical_doc_id", "sha256": sha, "candidates": sorted(canonical_ids)})
        else:
            match_status = "NEEDS_REVIEW"
            canonical_doc_id = None
            unresolved.append({"document_id": row["document_id"], "reason": "no_standard_match", "sha256": sha})

        csv_notice_no = clean(row["공고 번호"])

        # 중복 콘텐츠 그룹은 standard 쪽 레코드가 어느 CSV document_id에 대응하는지 확정할 수
        # 없으므로(같은 sha256이라 구분 불가), std_notice_no 교차검증/백필은 단일 매칭일 때만 수행한다.
        if not is_duplicate_content_group and std_matches:
            std_notice_no = clean(std_matches[0].get("공고번호"))
        else:
            std_notice_no = None

        # 공고번호 불일치/결측 처리 (csv 우선, 없으면 standard 쪽으로 backfill)
        notice_no = csv_notice_no or std_notice_no
        notice_no_source = "csv" if csv_notice_no else ("standard_backfill" if std_notice_no else None)
        notice_no_conflict = bool(csv_notice_no and std_notice_no and csv_notice_no != std_notice_no)

        crosswalk.append(
            {
                "document_id": row["document_id"],
                "canonical_doc_id": canonical_doc_id,
                "procurement_group_key": notice_no,
                "procurement_group_key_source": notice_no_source,
                "procurement_group_key_conflict": notice_no_conflict,
                "content_group_id": row["content_group_id"],
                "sha256": sha,
                "split": row["split"],
                "semantic_role": SEMANTIC_ROLE[row["split"]],
                "split_version": "STANDARD_V0_SPLIT_70_15_15_v0.1",
                "holdout_sealed": row["holdout_sealed"] == "TRUE",
                "allowed_during_development": row["allowed_during_development"] == "TRUE",
                "match_status": match_status,
                "match_basis": "sha256_content_hash",
                "duplicate_content_group": is_duplicate_content_group,
                "original_name": row["original_name"],
            }
        )

    # --- 3. content_group leakage 검증 (동일 content_group_id가 여러 split에 걸치는지) ---
    group_to_splits = defaultdict(set)
    for row in csv_rows:
        group_to_splits[row["content_group_id"]].add(row["split"])
    group_leakage = {g: sorted(s) for g, s in group_to_splits.items() if len(s) > 1}

    # --- 4. 공고번호(procurement) 재공고 등 동일 공고번호가 여러 split에 걸치는지 ---
    notice_to_splits = defaultdict(set)
    notice_to_docs = defaultdict(list)
    for c in crosswalk:
        if c["procurement_group_key"]:
            notice_to_splits[c["procurement_group_key"]].add(c["split"])
            notice_to_docs[c["procurement_group_key"]].append(c["document_id"])
    notice_leakage = {
        k: {"splits": sorted(v), "documents": notice_to_docs[k]}
        for k, v in notice_to_splits.items()
        if len(v) > 1
    }

    # --- 5. 결과 저장 ---
    import os
    os.makedirs(f"{ROOT}\\governance", exist_ok=True)

    with open(f"{ROOT}\\governance\\standard_v0_split_crosswalk_v0.1.jsonl", "w", encoding="utf-8") as f:
        for c in crosswalk:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    validation = {
        "total_documents": len(crosswalk),
        "split_counts": {
            s: sum(1 for c in crosswalk if c["split"] == s) for s in ["DEV", "REGRESSION", "FINAL_HOLDOUT"]
        },
        "csv_json_split_mismatch_count": len(split_mismatch),
        "csv_json_split_mismatch": split_mismatch,
        "canonical_doc_id_resolved_count": sum(1 for c in crosswalk if c["canonical_doc_id"]),
        "canonical_doc_id_unresolved": unresolved,
        "procurement_group_key_missing_count": sum(1 for c in crosswalk if not c["procurement_group_key"]),
        "procurement_group_key_conflict_count": sum(1 for c in crosswalk if c["procurement_group_key_conflict"]),
        "content_group_split_leakage": group_leakage,
        "procurement_notice_split_leakage": notice_leakage,
        "document_id_unique": len(set(c["document_id"] for c in crosswalk)) == len(crosswalk),
    }

    with open(f"{ROOT}\\governance\\standard_v0_split_validation_v0.1.json", "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    # 콘솔 대신 파일로 요약 출력 (cp949 인코딩 문제 회피)
    summary_lines = [
        f"총 문서: {validation['total_documents']}",
        f"split 분포: {validation['split_counts']}",
        f"csv/json split 불일치: {validation['csv_json_split_mismatch_count']}",
        f"canonical_doc_id 해결됨: {validation['canonical_doc_id_resolved_count']}/{len(crosswalk)}",
        f"canonical_doc_id 미해결: {len(unresolved)}",
        f"공고번호 결측: {validation['procurement_group_key_missing_count']}",
        f"공고번호 충돌(csv vs standard): {validation['procurement_group_key_conflict_count']}",
        f"content_group split leakage: {len(group_leakage)}건 -> {group_leakage}",
        f"공고번호(재공고 등) split leakage: {len(notice_leakage)}건 -> {list(notice_leakage.keys())}",
        f"document_id unique: {validation['document_id_unique']}",
    ]
    with open(f"{ROOT}\\governance\\_last_run_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))


if __name__ == "__main__":
    main()
