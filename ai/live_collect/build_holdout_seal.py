"""
가이드 17절: 8월 Live Final Holdout 후보 60건(`data/live/selected_aug_60/`) 처리.

원칙(가이드 17/18/21절 그대로):
- Live-Dev 100건과 완전히 분리해서 다룬다(이 스크립트는 selected_aug_60만 읽는다).
- 이 단계에서 허용되는 건 ID/filename/size/SHA-256 manifest, 객관적 exclusion(완전 손상/다운로드
  실패/동일 파일 중복/동일 공고 중복/취소 건), dedup, 랜덤 또는 층화 추출, SEAL 뿐이다.
- **원문 내용을 열어서 파싱하거나 "질문하기 쉬운지/파싱이 쉬운지" 같은 주관적 기준으로 제외하지 않는다**
  (가이드 17절 "제외하면 안 되는 이유" 정확히 준수 - 표가 많다/어려워 보인다는 이유로 빼지 않음).
- SHA-256/매직바이트 확인은 파일 "내용을 읽어 의미를 파악"하는 게 아니라 순수 구조적 무결성 확인이라
  허용된다(가이드 2절 raw inventory 체크리스트에도 "extension과 실제 포맷 mismatch 여부"가 명시됨).
- SEAL 이후에는 이 30건을 절대 다시 열어보거나 파서/프롬프트 튜닝에 쓰지 않는다(18절) - 실제 파싱은
  팀 파이프라인이 완전히 Freeze된 뒤 단 한 번만 수행한다(이 스크립트가 하는 일이 아님).

실행: uv run python live_collect/build_holdout_seal.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = ROOT / "data" / "live"
HOLDOUT_RAW_DIR = LIVE_DIR / "selected_aug_60"
MANIFESTS_DIR = LIVE_DIR / "manifests"

OUT_RAW_MANIFEST = MANIFESTS_DIR / "holdout_raw_manifest_v0.1.jsonl"
OUT_EXCLUSION_LOG = MANIFESTS_DIR / "holdout_exclusion_log_v0.1.jsonl"
OUT_FINAL_30 = MANIFESTS_DIR / "holdout_final_30_v0.1.jsonl"
OUT_SEAL_DOC = LIVE_DIR / "HOLDOUT_FINAL_30_SEALED_v0.1.md"

FINAL_TARGET = 30
RANDOM_SEED = 20260828  # 팀 담당 분담이 시작된 날짜(2026-08-28) 고정 - 재현성 확보

# 확장자별 매직바이트 시그니처. HWPX/ZIP/DOCX/XLSX는 전부 ZIP 컨테이너라 PK로 동일하다.
MAGIC_SIGNATURES = {
    ".hwp": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE Compound File
    ".hwpx": [b"PK\x03\x04"], ".zip": [b"PK\x03\x04"], ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"], ".pptx": [b"PK\x03\x04"],
    ".pdf": [b"%PDF"],
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_magic(path: Path, ext: str) -> tuple[bool, str]:
    """순수 구조적 무결성 확인(파일 내용의 의미는 안 봄) - 완전 손상/확장자 불일치 탐지용."""
    sigs = MAGIC_SIGNATURES.get(ext)
    if sigs is None:
        return True, "unknown_ext_skip_check"
    head = path.open("rb").read(8)
    if any(head.startswith(s) for s in sigs):
        return True, "ok"
    return False, f"magic_mismatch(head={head[:4].hex()})"


def normalize_business_name(name: str) -> str:
    name = re.sub(r"[()\[\]（）「」]", "", str(name or ""))
    name = re.sub(r"\s+", "", name)
    return name.strip()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    # --- Live-Dev와 분리 확인(재확인, 원칙 준수) ---
    dev_dir = LIVE_DIR / "selected_jun_jul_100"
    dev_bid_nos = {p.name.split("_", 1)[0] for p in dev_dir.iterdir() if p.is_dir()}
    holdout_folders = sorted(p for p in HOLDOUT_RAW_DIR.iterdir() if p.is_dir())
    holdout_bid_nos = {p.name.split("_", 1)[0] for p in holdout_folders}
    overlap = dev_bid_nos & holdout_bid_nos
    assert not overlap, f"Live-Dev와 겹치는 bid 발견, 중단: {overlap}"
    print(f"[분리 확인] Holdout 후보 폴더: {len(holdout_folders)}건 / Live-Dev와 중복 0건 (PASS)")

    all_bids = {b["bid_notice_no"]: b for b in read_jsonl(MANIFESTS_DIR / "bids.jsonl")}
    all_attachments = read_jsonl(MANIFESTS_DIR / "attachments.jsonl")
    att_by_bid: dict[str, list[dict]] = defaultdict(list)
    for a in all_attachments:
        if a.get("bid_notice_no") in holdout_bid_nos:
            att_by_bid[a["bid_notice_no"]].append(a)

    # --- Step 1: ID/filename/size/SHA-256 manifest ---
    file_rows = []
    for folder in holdout_folders:
        bid_notice_no, bid_notice_ord = folder.name.split("_", 2)[:2]
        bid_id = f"{bid_notice_no}_{bid_notice_ord}"
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            size = f.stat().st_size
            digest = sha256_of(f) if size > 0 else None
            att = next((a for a in att_by_bid.get(bid_notice_no, [])
                        if a.get("local_path") and Path(a["local_path"]).name == f.name), None)
            ok, magic_detail = check_magic(f, ext) if size > 0 else (False, "zero_size")
            file_rows.append({
                "bid_id": bid_id, "bid_notice_no": bid_notice_no, "bid_notice_ord": bid_notice_ord,
                "filename": f.name, "extension": ext.lstrip("."), "size": size,
                "sha256": digest, "local_path": str(f.relative_to(ROOT)),
                "download_status": att.get("download_status") if att else None,
                "source_url": att.get("url") if att else None,
                "magic_check_ok": ok, "magic_check_detail": magic_detail,
            })

    with OUT_RAW_MANIFEST.open("w", encoding="utf-8") as fh:
        for row in file_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[Step1] raw manifest 저장: {OUT_RAW_MANIFEST.relative_to(ROOT)} ({len(file_rows)}개 파일)")

    # --- Step 2: 객관적 exclusion ---
    exclusion_log = []
    bid_ids = sorted({r["bid_id"] for r in file_rows})
    files_by_bid: dict[str, list[dict]] = defaultdict(list)
    for r in file_rows:
        files_by_bid[r["bid_id"]].append(r)

    excluded_bids: dict[str, str] = {}

    # (a) 다운로드 자체 실패 / 완전 손상: bid의 모든 파일이 size=0이거나 magic 불일치면 그 bid 전체 제외
    for bid_id, rows in files_by_bid.items():
        usable = [r for r in rows if r["size"] > 0 and r["magic_check_ok"]]
        if not usable:
            reasons = sorted({("size=0" if r["size"] == 0 else r["magic_check_detail"]) for r in rows})
            excluded_bids[bid_id] = f"다운로드 실패/완전 손상 (사용 가능한 파일 0개, 사유: {reasons})"

    # (b) 동일 파일 exact duplicate: bid 폴더 내부에서 같은 sha256이 여러 개면 로그만 남김(파일 자체는
    #     manifest에 이미 다 기록되어 있으므로 별도 삭제는 하지 않음 - 원본 불변 원칙)
    dup_file_groups = 0
    for bid_id, rows in files_by_bid.items():
        by_hash = defaultdict(list)
        for r in rows:
            if r["sha256"]:
                by_hash[r["sha256"]].append(r["filename"])
        for h, names in by_hash.items():
            if len(names) > 1:
                dup_file_groups += 1
                exclusion_log.append({"type": "DUPLICATE_FILE_WITHIN_BID", "bid_id": bid_id,
                                       "sha256": h, "filenames": names, "action": "manifest에 기록만, 원본 유지"})

    # (c) 동일 공고 중복 다운로드: 같은 bid_notice_no가 여러 ord로 selected_aug_60에 들어있으면 최신 ord만 유지
    by_no: dict[str, list[str]] = defaultdict(list)
    for bid_id in bid_ids:
        no, ord_ = bid_id.rsplit("_", 1)
        by_no[no].append(ord_)
    for no, ords in by_no.items():
        if len(ords) > 1:
            latest = max(ords)
            for ord_ in ords:
                if ord_ != latest:
                    bid_id = f"{no}_{ord_}"
                    excluded_bids[bid_id] = f"동일 공고번호({no})의 구버전 차수(최신 {latest} 유지)"

    # (d) 취소 건: 사업명에 "취소"가 들어간 경우
    for bid_id in bid_ids:
        if bid_id in excluded_bids:
            continue
        no = bid_id.rsplit("_", 1)[0]
        meta = all_bids.get(no, {})
        name = meta.get("bid_notice_nm") or ""
        if "취소" in name:
            excluded_bids[bid_id] = f"공고명에 '취소' 포함: {name}"

    # (e) dedup / same-bid grouping (cross-bid, 사업명 정규화 매칭): 서로 다른 bid_notice_no인데
    #     정규화한 사업명이 완전히 같으면 재공고/중복 가능성 - 명확한 경우만 최신 공개일 유지, 애매하면
    #     로그만 남기고 배제하지 않는다(예전 Live-Dev 처리 때와 동일한 보수적 기준).
    name_groups: dict[str, list[str]] = defaultdict(list)
    for no in {bid_id.rsplit("_", 1)[0] for bid_id in bid_ids}:
        meta = all_bids.get(no, {})
        norm = normalize_business_name(meta.get("bid_notice_nm", ""))
        if norm:
            name_groups[norm].append(no)
    ambiguous_name_dups = []
    for norm, nos in name_groups.items():
        if len(set(nos)) > 1:
            ambiguous_name_dups.append({"normalized_name": norm, "bid_notice_nos": sorted(set(nos))})
    if ambiguous_name_dups:
        print(f"[Step3] 사업명 정규화 일치(재공고 의심) {len(ambiguous_name_dups)}건 - 자동 배제하지 않고 기록만 함:")
        for g in ambiguous_name_dups:
            print("  ", g)

    for bid_id, reason in excluded_bids.items():
        exclusion_log.append({"type": "BID_EXCLUDED", "bid_id": bid_id, "reason": reason})

    with OUT_EXCLUSION_LOG.open("w", encoding="utf-8") as fh:
        for row in exclusion_log + [{"type": "AMBIGUOUS_NAME_DUP", **g} for g in ambiguous_name_dups]:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    eligible_bid_ids = sorted(set(bid_ids) - set(excluded_bids))
    print(f"[Step2] 제외된 bid: {len(excluded_bids)}건 / 남은 후보: {len(eligible_bid_ids)}건")
    for bid_id, reason in excluded_bids.items():
        print(f"   - {bid_id}: {reason}")
    print(f"[Step2] 동일 bid 내 exact-duplicate 파일 그룹: {dup_file_groups}건(원본 유지, 로그만)")

    # --- Step 4: 층화 추출(tier 기준) -> Final 30 ---
    def tier_of(bid_id: str) -> int:
        no = bid_id.rsplit("_", 1)[0]
        return all_bids.get(no, {}).get("tier", 5)

    by_tier: dict[int, list[str]] = defaultdict(list)
    for bid_id in eligible_bid_ids:
        by_tier[tier_of(bid_id)].append(bid_id)

    rng = random.Random(RANDOM_SEED)
    for t in by_tier:
        by_tier[t].sort()  # 정렬 후 셔플해야 seed로 완전히 재현 가능
        rng.shuffle(by_tier[t])

    target = min(FINAL_TARGET, len(eligible_bid_ids))
    # tier 비율을 원본(eligible) 분포에 맞춰 배분(층화), 나머지는 tier 순서대로 채움
    tier_order = sorted(by_tier)
    quota = {t: round(len(by_tier[t]) * target / len(eligible_bid_ids)) for t in tier_order}
    selected: list[str] = []
    for t in tier_order:
        take = min(quota[t], len(by_tier[t]))
        selected.extend(by_tier[t][:take])
    # 반올림 오차 보정: 부족하면 남은 후보 중에서, 넘치면 뒤에서부터 잘라냄
    remaining_pool = [bid_id for t in tier_order for bid_id in by_tier[t][quota[t]:]]
    rng.shuffle(remaining_pool)
    i = 0
    while len(selected) < target and i < len(remaining_pool):
        if remaining_pool[i] not in selected:
            selected.append(remaining_pool[i])
        i += 1
    selected = sorted(set(selected))[:target]

    print(f"[Step4] 층화 추출(tier 비율 유지, seed={RANDOM_SEED}): {len(selected)}/{len(eligible_bid_ids)}건 선정")
    print(f"        선정 tier 분포: {dict(Counter(tier_of(b) for b in selected))}")
    print(f"        전체(제외 후) tier 분포: {dict(Counter(tier_of(b) for b in eligible_bid_ids))}")

    # --- Step 5: SEAL ---
    final_rows = []
    for bid_id in selected:
        no = bid_id.rsplit("_", 1)[0]
        meta = all_bids.get(no, {})
        files = [r for r in files_by_bid[bid_id] if r["size"] > 0 and r["magic_check_ok"]]
        final_rows.append({
            "bid_id": bid_id, "bid_notice_no": no, "bid_notice_nm": meta.get("bid_notice_nm"),
            "tier": meta.get("tier"), "pub_prcrmnt_lrg_clsfc_nm": meta.get("pub_prcrmnt_lrg_clsfc_nm"),
            "file_count": len(files),
            "files": [{"filename": r["filename"], "extension": r["extension"], "size": r["size"],
                       "sha256": r["sha256"]} for r in files],
        })
    with OUT_FINAL_30.open("w", encoding="utf-8") as fh:
        for row in final_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    seal_doc = f"""# HOLDOUT FINAL 30 - SEALED v0.1

**봉인 일시**: 이 파일이 생성된 시점 (git/파일 mtime 참고)
**대상**: `data/live/selected_aug_60/`(원본 60건 후보) 중 {len(selected)}건

## 절대 원칙 (가이드 18/21절)
- 이 30건의 **원문 내용을 열어서 파서/청커/Retriever/프롬프트를 튜닝하는 데 쓰지 않는다.**
- 실제 파싱은 팀의 Retrieval/Generation/M5 평가 파이프라인이 전부 **Freeze된 뒤 단 한 번만** 수행한다.
- Holdout에서 파싱 실패가 나와도 **그 자리에서 원인 분석하며 parser를 고치지 않는다** - 실패를 그대로
  Final 결과에 기록하고 그 Run을 종료한다(가이드 18절).

## 처리 요약
- Raw 후보: {len(holdout_folders)}건
- 객관적 제외: {len(excluded_bids)}건 (사유는 `manifests/holdout_exclusion_log_v0.1.jsonl` 참고)
- 제외 후 남은 후보: {len(eligible_bid_ids)}건
- 층화 추출(seed={RANDOM_SEED}, tier 비율 유지): **{len(selected)}건 선정**
- 사업명 정규화 재공고 의심 {len(ambiguous_name_dups)}건은 자동 배제하지 않고
  `manifests/holdout_exclusion_log_v0.1.jsonl`에 `AMBIGUOUS_NAME_DUP`로 기록만 함(주관적 판단 보류)

## 선정 30건 목록
{chr(10).join(f"- {r['bid_id']} (tier {r['tier']}) - {r['bid_notice_nm']}" for r in final_rows)}

## 산출물
- `manifests/holdout_raw_manifest_v0.1.jsonl` - 60건 전체 원본 inventory(ID/filename/size/SHA-256)
- `manifests/holdout_exclusion_log_v0.1.jsonl` - 제외/중복 사유 로그
- `manifests/holdout_final_30_v0.1.jsonl` - 봉인된 최종 30건(bid_id + 파일별 SHA-256)
"""
    OUT_SEAL_DOC.write_text(seal_doc, encoding="utf-8")
    print(f"\n[Step5] SEAL 완료: {OUT_SEAL_DOC.relative_to(ROOT)}")
    print(f"         {OUT_FINAL_30.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
