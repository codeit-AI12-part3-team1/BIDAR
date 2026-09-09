"""
P0 1~3단계: Live-Dev 100 / Holdout 60 물리 분리 검증 + Raw Inventory(해시 포함) + 핵심 HWP/PDF 선정.

원칙 준수:
- Raw 파일(data/live/raw/, data/live/selected_*)은 절대 수정/덮어쓰기하지 않는다. 이 스크립트는 읽기 전용.
- Live-Dev(selected_jun_jul_100)와 Final Holdout 후보(selected_aug_60)를 섞지 않는다.
- 우선순위: 1.제안요청서 2.과업지시서/과업내용서 3.메인 입찰공고문 4.기술규격서 5.기타.
- 1차 지원 포맷은 HWP/HWPX/PDF만. 그 외(xlsx/zip/pptx/이미지/docx 등)는 processing_status=DEFERRED로
  manifest에 남기고 원본은 그대로 둔다. 지원 안 하는 포맷을 SUCCESS로 기록하지 않는다(선정 단계일 뿐,
  파싱 성공 여부는 노트북에서 별도 판정).

실행: uv run python live_collect/build_live_dev_inventory.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = ROOT / "data" / "live"
DEV_RAW_DIR = LIVE_DIR / "selected_jun_jul_100"
HOLDOUT_RAW_DIR = LIVE_DIR / "selected_aug_60"
MANIFESTS_DIR = LIVE_DIR / "manifests"
OUT_MANIFEST = MANIFESTS_DIR / "live_dev_raw_manifest_v0.1.jsonl"
OUT_BIDS_DEV = MANIFESTS_DIR / "live_dev_bids_v0.1.jsonl"

SUPPORTED_EXT = {".hwp", ".hwpx", ".pdf"}
DEFER_EXT_NOTE = {
    ".xlsx": "spreadsheet", ".xls": "spreadsheet", ".zip": "archive", ".pptx": "slides",
    ".ppt": "slides", ".docx": "word_doc", ".doc": "word_doc", ".jpg": "image", ".jpeg": "image",
    ".png": "image", ".gif": "image", ".hwt": "hwp_template",
}

# 우선순위 tier(guide 3단계 "1차 처리 범위" 순서 그대로): 1=RFP, 2=과업지시서, 3=메인 공고문, 4=규격서
TIER_PATTERNS = [
    (1, re.compile(r"제안\s*요청서")),
    (2, re.compile(r"과업\s*(지시서|내용서|수행\s*계획서)")),
    (3, re.compile(r"(입찰\s*)?공고(문|서)")),
    (4, re.compile(r"(기술\s*)?규격서|시방서")),
]
FORMAT_PRIORITY = {".hwp": 0, ".hwpx": 1, ".pdf": 2}


def classify_tier(filename: str) -> int:
    for tier, pat in TIER_PATTERNS:
        if pat.search(filename):
            return tier
    return 5  # 기타(서식/서약서/사유서 등)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    # --- Step 1: 물리 분리 검증 (수정하지 않음, 확인만) ---
    dev_folders = sorted(p for p in DEV_RAW_DIR.iterdir() if p.is_dir())
    holdout_folders = sorted(p for p in HOLDOUT_RAW_DIR.iterdir() if p.is_dir())
    dev_bid_keys = {tuple(p.name.split("_", 2)[:2]) for p in dev_folders}
    holdout_bid_keys = {tuple(p.name.split("_", 2)[:2]) for p in holdout_folders}
    overlap = dev_bid_keys & holdout_bid_keys
    print(f"[Step1] Live-Dev 폴더: {len(dev_folders)}건 / Holdout 후보 폴더: {len(holdout_folders)}건")
    print(f"[Step1] dev/holdout bid_notice_no 중복: {len(overlap)}건", overlap if overlap else "(없음, PASS)")
    assert not overlap, "Live-Dev와 Holdout 후보가 겹칩니다 - 물리 분리 원칙 위반, 중단합니다."

    dev_bid_notice_nos = {k[0] for k in dev_bid_keys}

    all_bids = read_jsonl(MANIFESTS_DIR / "bids.jsonl")
    bids_by_no = {b["bid_notice_no"]: b for b in all_bids}
    dev_bids = [bids_by_no[no] for no in dev_bid_notice_nos if no in bids_by_no]
    missing_bid_meta = dev_bid_notice_nos - set(bids_by_no)
    print(f"[Step1] bids.jsonl에서 메타 찾은 dev bid: {len(dev_bids)}/{len(dev_bid_notice_nos)}"
          f" (누락 {len(missing_bid_meta)}건)")

    all_attachments = read_jsonl(MANIFESTS_DIR / "attachments.jsonl")
    attachments_by_bid: dict[str, list[dict]] = defaultdict(list)
    for a in all_attachments:
        if a.get("bid_notice_no") in dev_bid_notice_nos:
            attachments_by_bid[a["bid_notice_no"]].append(a)

    # --- Step 2: Raw Inventory + Hash (attachments.jsonl에 이미 있는 sha256/size 재사용, 새로 계산하지 않음) ---
    # --- Step 3: 처리할 핵심 HWP/PDF 선정 (bid당 1개 primary, 나머지 DEFERRED) ---
    manifest_rows = []
    no_supported_candidate = []
    for folder in dev_folders:
        bid_notice_no, bid_notice_ord = folder.name.split("_", 2)[:2]
        bid_id = f"{bid_notice_no}_{bid_notice_ord}"
        files = sorted(p for p in folder.iterdir() if p.is_file())

        candidates = []
        for f in files:
            ext = f.suffix.lower()
            att = next((a for a in attachments_by_bid.get(bid_notice_no, [])
                        if a.get("download_status") in ("SUCCESS", "SUCCESS_WITH_WARNING")
                        and a.get("local_path") and Path(a["local_path"]).name == f.name), None)
            exists = f.exists()
            size = f.stat().st_size if exists else 0
            candidates.append({
                "bid_id": bid_id, "bid_notice_no": bid_notice_no, "bid_notice_ord": bid_notice_ord,
                "filename": f.name, "extension": ext.lstrip("."),
                "local_path": str(f.relative_to(ROOT)),
                "exists": exists, "size": size,
                "sha256": att.get("sha256") if att else None,
                "source_url": att.get("url") if att else None,
                "attachment_manifest_matched": att is not None,
                "content_tier": classify_tier(f.name) if ext in SUPPORTED_EXT else None,
                "format_supported": ext in SUPPORTED_EXT,
            })

        supported = [c for c in candidates if c["format_supported"] and c["exists"] and c["size"] > 0]
        if supported:
            supported.sort(key=lambda c: (c["content_tier"], FORMAT_PRIORITY.get("." + c["extension"], 9)))
            primary = supported[0]
        else:
            primary = None
            no_supported_candidate.append(bid_id)

        for c in candidates:
            is_primary = primary is not None and c["filename"] == primary["filename"]
            if is_primary:
                status = "PRIMARY_SELECTED"
            elif c["format_supported"]:
                status = "DEFERRED_SECONDARY"  # 지원 포맷이지만 우선순위상 후순위
            else:
                status = "DEFERRED_UNSUPPORTED_FORMAT"
            c["processing_status"] = status
            c["defer_reason"] = None if is_primary else (
                None if c["format_supported"] else DEFER_EXT_NOTE.get("." + c["extension"], "unsupported")
            )
            manifest_rows.append(c)

    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_MANIFEST.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with OUT_BIDS_DEV.open("w", encoding="utf-8") as f:
        for row in dev_bids:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # --- 확인 체크리스트 ---
    n_bids = len(dev_folders)
    n_primary = sum(1 for r in manifest_rows if r["processing_status"] == "PRIMARY_SELECTED")
    n_zero_size = sum(1 for r in manifest_rows if r["exists"] and r["size"] == 0)
    n_missing_file = sum(1 for r in manifest_rows if not r["exists"])
    n_no_sha = sum(1 for r in manifest_rows if r["exists"] and not r["sha256"])
    sha_counts = Counter(r["sha256"] for r in manifest_rows if r["sha256"])
    dup_sha = {k: v for k, v in sha_counts.items() if v > 1}
    ext_dist = Counter(r["extension"] for r in manifest_rows)
    primary_ext_dist = Counter(r["extension"] for r in manifest_rows if r["processing_status"] == "PRIMARY_SELECTED")
    primary_tier_dist = Counter(r["content_tier"] for r in manifest_rows if r["processing_status"] == "PRIMARY_SELECTED")

    print(f"\n[Step2/3] dev bid 수: {n_bids} / primary 선정: {n_primary} / primary 없음: {len(no_supported_candidate)}")
    if no_supported_candidate:
        print("  -> primary 후보(HWP/HWPX/PDF) 없는 bid:", no_supported_candidate)
    print(f"[Step2] 전체 attachment 레코드: {len(manifest_rows)} / size=0: {n_zero_size} / 파일 없음: {n_missing_file}"
          f" / sha256 없음(exists인데): {n_no_sha}")
    print(f"[Step2] 중복 sha256 그룹: {len(dup_sha)}건", list(dup_sha.items())[:5] if dup_sha else "")
    print(f"[Step2] 전체 확장자 분포: {dict(ext_dist)}")
    print(f"[Step3] primary 확장자 분포: {dict(primary_ext_dist)}")
    print(f"[Step3] primary 콘텐츠 tier 분포(1=RFP,2=과업지시서,3=공고문,4=규격서,5=기타): {dict(primary_tier_dist)}")
    print(f"\n저장 완료: {OUT_MANIFEST.relative_to(ROOT)}")
    print(f"저장 완료: {OUT_BIDS_DEV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
