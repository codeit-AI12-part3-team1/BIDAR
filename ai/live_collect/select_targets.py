"""bids.jsonl 을 tier(키워드 우선순위) 기준으로 정렬해 목표 건수만 selected=true로 표시한다.
첨부파일 다운로드(API 호출 비용이 큰 단계) 전에 반드시 이 결과를 검토할 것.

사용 예:
    uv run python select_targets.py --target 100
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date

import config


def _week_key(bid_ntce_dt: str) -> str:
    """bid_ntce_dt('2026-06-01 09:10:23' 형식)에서 ISO 연-주차 키를 뽑는다.
    형식이 예상과 다르면(빈 값 등) 'unknown'으로 묶어 마지막에 처리한다."""
    try:
        d = date.fromisoformat(bid_ntce_dt[:10])
    except ValueError:
        return "unknown"
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def main(target: int) -> None:
    rows = []
    with config.BIDS_MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    # 동일 bid_notice_no의 최신 차수만 후보로 사용 (재공고/정정은 최신본이 최종본)
    latest_by_no: dict[str, dict] = {}
    for row in rows:
        no = row["bid_notice_no"]
        cur = latest_by_no.get(no)
        if cur is None or (row["bid_notice_ord"] or "0") >= (cur["bid_notice_ord"] or "0"):
            latest_by_no[no] = row

    # 주(week) 단위로 그룹핑 -> 각 그룹 내부는 tier, 날짜 순으로 정렬해둔다.
    by_week: dict[str, list[dict]] = defaultdict(list)
    for r in latest_by_no.values():
        by_week[_week_key(r["bid_ntce_dt"])].append(r)
    for week in by_week:
        by_week[week].sort(key=lambda r: (r["tier"], r["bid_ntce_dt"]))

    # 라운드로빈: 매 라운드마다 각 주(week)에서 가장 우선순위 높은 후보를 하나씩 뽑는다.
    # -> 특정 며칠에 몰리지 않고 기간 전체에 고르게 분산되면서도, 주 내부에서는 tier 우선순위가 유지된다.
    week_order = sorted(w for w in by_week if w != "unknown") + (["unknown"] if "unknown" in by_week else [])
    cursors = {w: 0 for w in week_order}
    selected: list[dict] = []
    while len(selected) < target:
        progressed = False
        for w in week_order:
            if len(selected) >= target:
                break
            items = by_week[w]
            c = cursors[w]
            if c < len(items):
                selected.append(items[c])
                cursors[w] = c + 1
                progressed = True
        if not progressed:
            break  # 모든 주의 후보를 다 썼는데도 target 미달 (전체 풀이 target보다 작음)

    selected_keys = {f"{r['bid_notice_no']}-{r['bid_notice_ord']}" for r in selected}
    tier_counts = Counter(r["tier"] for r in selected)
    week_counts = Counter(_week_key(r["bid_ntce_dt"]) for r in selected)

    for row in rows:
        key = f"{row['bid_notice_no']}-{row['bid_notice_ord']}"
        row["selected"] = key in selected_keys

    with config.BIDS_MANIFEST.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"전체 공고(중복제거 후) {len(latest_by_no)}건 중 {len(selected_keys)}건 선택 (주간 라운드로빈)")
    print(
        f"Tier 분포(선택분): {dict(sorted(tier_counts.items()))}  "
        "(1=ICT서비스+SW/AI키워드, 2=ICT서비스 기타, 3=ICT서비스 아님+IoT/네트워크 키워드, 4=일반용역 fallback)"
    )
    print(f"주(week) 분포(선택분): {dict(sorted(week_counts.items()))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=100)
    args = parser.parse_args()
    main(args.target)
