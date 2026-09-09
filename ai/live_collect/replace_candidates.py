"""selected=true 인 공고 중 실제 파일 다운로드가 0건인 것들을,
같은 주(week)의 다른 후보(첨부URL이 실제로 존재하는 것)로 교체한다.

사용 예:
    uv run python replace_candidates.py
"""
from __future__ import annotations

import json

import config
from select_targets import _week_key


def _has_attachment_url(raw_path: str) -> bool:
    try:
        item = json.loads(open(raw_path, encoding="utf-8").read())
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return any((item.get(f"ntceSpecDocUrl{i}") or "").strip() for i in range(1, 11))


def find_zero_success_bids(rows: list[dict]) -> set[str]:
    selected_nos = {r["bid_notice_no"] for r in rows if r.get("selected")}
    success_nos = set()
    if config.ATTACHMENTS_MANIFEST.exists():
        with config.ATTACHMENTS_MANIFEST.open(encoding="utf-8") as f:
            for line in f:
                a = json.loads(line)
                if a.get("download_status") in ("SUCCESS", "SUCCESS_WITH_WARNING"):
                    success_nos.add(a["bid_notice_no"])
    return selected_nos - success_nos


def main() -> None:
    rows = []
    with config.BIDS_MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    latest_by_no: dict[str, dict] = {}
    for row in rows:
        no = row["bid_notice_no"]
        cur = latest_by_no.get(no)
        if cur is None or (row["bid_notice_ord"] or "0") >= (cur["bid_notice_ord"] or "0"):
            latest_by_no[no] = row

    by_week: dict[str, list[dict]] = {}
    for r in latest_by_no.values():
        by_week.setdefault(_week_key(r["bid_ntce_dt"]), []).append(r)
    for week in by_week:
        by_week[week].sort(key=lambda r: (r["tier"], r["bid_ntce_dt"]))

    zero_success = find_zero_success_bids(rows)
    selected_nos = {r["bid_notice_no"] for r in rows if r.get("selected")}

    replacements = {}
    for bad_no in zero_success:
        bad_row = latest_by_no[bad_no]
        week = _week_key(bad_row["bid_ntce_dt"])
        replacement = None
        for cand in by_week.get(week, []):
            if cand["bid_notice_no"] in selected_nos or cand["bid_notice_no"] in replacements.values():
                continue
            if _has_attachment_url(cand["raw_path"]):
                replacement = cand
                break
        if replacement:
            replacements[bad_no] = replacement["bid_notice_no"]

    # bid_notice_no는 차수(ord)가 여러 건 존재할 수 있으므로, 반드시 최신 ord와
    # 짝지은 "no-ord" 키 단위로만 selected를 갱신한다 (아니면 구/신 차수가 동시에
    # selected=true가 되어 목표 건수가 어긋날 수 있음).
    final_nos = (selected_nos - set(replacements.keys())) | set(replacements.values())
    selected_keys = {f"{no}-{latest_by_no[no]['bid_notice_ord']}" for no in final_nos}

    for row in rows:
        key = f"{row['bid_notice_no']}-{row['bid_notice_ord']}"
        row["selected"] = key in selected_keys

    with config.BIDS_MANIFEST.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"파일 0건이던 {len(zero_success)}건 중 {len(replacements)}건 교체됨:")
    for old, new in replacements.items():
        print(f"  {old} -> {new} ({latest_by_no[new]['bid_notice_nm']})")
    not_replaced = zero_success - set(replacements.keys())
    if not_replaced:
        print(f"교체 후보 못 찾음(그대로 유지, 수동 확인 필요): {sorted(not_replaced)}")


if __name__ == "__main__":
    main()
