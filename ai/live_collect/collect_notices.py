"""용역 입찰공고 목록을 기간으로 수집해 raw json + manifest(jsonl)로 저장한다.

사용 예:
    uv run python collect_notices.py --start 202606010000 --end 202607312359
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta

import config
from api_client import ApiError, G2BClient
from quota import QuotaExceeded, QuotaTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collect_notices")


def classify_tier(item: dict) -> int:
    """실호출로 확인된 pubPrcrmntLrgClsfcNm(공식 대분류)을 1차 기준으로 쓴다.
    tier 1: ICT 서비스 + SW/AI 키워드 매치 (최우선)
    tier 2: ICT 서비스 (그 외 전부, 컨설팅/유지관리 등 포함)
    tier 3: ICT 서비스 아니지만 IoT/네트워크 등 키워드 매치 (fallback, 실측상 거의 안 씀)
    tier 4: 그 외 일반 용역 (last resort)
    """
    name = item.get("bidNtceNm", "") or ""
    lrg_category = (item.get("pubPrcrmntLrgClsfcNm", "") or "").strip()
    name_low = name.lower()

    if lrg_category == config.PRIMARY_LARGE_CATEGORY:
        if any(kw.lower() in name_low for kw in config.KEYWORD_TIERS[1]):
            return 1
        return 2
    if any(kw.lower() in name_low for kw in config.FALLBACK_KEYWORDS_TIER2):
        return 3
    return 4


def load_seen_keys() -> set[str]:
    seen = set()
    if config.BIDS_MANIFEST.exists():
        with config.BIDS_MANIFEST.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                seen.add(f"{row['bid_notice_no']}-{row['bid_notice_ord']}")
    return seen


def _split_into_chunks(start: str, end: str, max_span_days: int) -> list[tuple[str, str]]:
    """yyyyMMddHHmm 문자열 구간을 API 제한(31일)을 넘지 않는 여러 구간으로 쪼갠다."""
    fmt = "%Y%m%d%H%M"
    start_dt = datetime.strptime(start, fmt)
    end_dt = datetime.strptime(end, fmt)

    chunks = []
    cur = start_dt
    span = timedelta(days=max_span_days)
    while cur < end_dt:
        chunk_end = min(cur + span, end_dt)
        chunks.append((cur.strftime(fmt), chunk_end.strftime(fmt)))
        cur = chunk_end + timedelta(minutes=1)
    return chunks


def _collect_chunk(
    client: G2BClient, seen: set[str], begin_dt: str, end_dt: str, num_rows: int, max_pages: int
) -> int:
    new_count = 0
    page_no = 1
    total_count = 0
    fetched_so_far = 0

    while True:
        try:
            items, total_count = client.get_service_bid_list(
                begin_dt=begin_dt, end_dt=end_dt, page_no=page_no, num_rows=num_rows
            )
        except QuotaExceeded as e:
            logger.warning("%s", e)
            break
        except ApiError as e:
            # 네트워크 타임아웃 등으로 클라이언트 자체 재시도(5회)까지 실패한 경우.
            # 여기서 한 번 더 길게 쉬었다가 같은 페이지를 재시도한다 - 이미 저장된
            # 이전 페이지 데이터는 그대로 남아있으므로 데이터 유실은 없다.
            logger.error("페이지 %s 조회 실패, 30초 대기 후 이 구간은 포기하고 다음으로 넘어갑니다: %s", page_no, e)
            time.sleep(30)
            try:
                items, total_count = client.get_service_bid_list(
                    begin_dt=begin_dt, end_dt=end_dt, page_no=page_no, num_rows=num_rows
                )
            except (ApiError, QuotaExceeded) as e2:
                logger.error(
                    "재시도도 실패해 이 구간(%s~%s)을 여기서 중단합니다: %s. "
                    "이미 수집된 데이터는 보존되어 있고, 스크립트를 그대로 재실행하면 "
                    "중복 없이 이어서 진행됩니다.",
                    begin_dt, end_dt, e2,
                )
                break

        if not items:
            break

        with config.BIDS_MANIFEST.open("a", encoding="utf-8") as manifest_f:
            for item in items:
                bid_no = item.get("bidNtceNo", "")
                bid_ord = item.get("bidNtceOrd", "")
                key = f"{bid_no}-{bid_ord}"
                if not bid_no or key in seen:
                    continue
                seen.add(key)

                raw_path = config.NOTICES_RAW_DIR / f"{bid_no}_{bid_ord}.json"
                raw_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

                row = {
                    "bid_notice_no": bid_no,
                    "bid_notice_ord": bid_ord,
                    "bid_notice_nm": item.get("bidNtceNm", ""),
                    "ntce_instt_nm": item.get("ntceInsttNm", ""),
                    "dminstt_nm": item.get("dminsttNm", ""),
                    "bid_ntce_dt": item.get("bidNtceDt", ""),
                    "bid_clse_dt": item.get("bidClseDt", ""),
                    "asign_bdgt_amt": item.get("asignBdgtAmt", ""),
                    "presmpt_prce": item.get("presmptPrce", ""),
                    "pub_prcrmnt_lrg_clsfc_nm": item.get("pubPrcrmntLrgClsfcNm", ""),
                    "pub_prcrmnt_mid_clsfc_nm": item.get("pubPrcrmntMidClsfcNm", ""),
                    "tier": classify_tier(item),
                    "raw_path": str(raw_path),
                    "selected": False,
                }
                manifest_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                new_count += 1

        fetched_so_far += len(items)
        logger.info(
            "  [%s~%s] page %s, 누적 조회 %s/%s건 (신규 %s건)",
            begin_dt, end_dt, page_no, fetched_so_far, total_count, new_count,
        )

        # num_rows보다 실제 반환 건수가 적을 수 있어(API가 상한을 두는 경우),
        # page_no*num_rows가 아니라 실제 누적 조회 건수로 종료 조건을 판단한다.
        if fetched_so_far >= total_count or page_no >= max_pages:
            break
        page_no += 1
        time.sleep(0.3)

    return new_count


def collect(start: str, end: str, num_rows: int = 500, max_pages: int = 100, debug: bool = False) -> None:
    client = G2BClient(quota=QuotaTracker(), debug=debug)
    seen = load_seen_keys()
    total_new = 0

    chunks = _split_into_chunks(start, end, config.MAX_QUERY_SPAN_DAYS)
    logger.info("기간 %s~%s 를 %s개 구간(최대 %s일)으로 분할해 조회합니다.", start, end, len(chunks), config.MAX_QUERY_SPAN_DAYS)

    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        logger.info("구간 %s/%s: %s ~ %s", i, len(chunks), chunk_start, chunk_end)
        total_new += _collect_chunk(client, seen, chunk_start, chunk_end, num_rows, max_pages)

    logger.info("전체 완료: 신규 %s건 저장됨 (누적 고유 공고 %s건)", total_new, len(seen))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="yyyyMMddHHmm, 예: 202606010000")
    parser.add_argument("--end", required=True, help="yyyyMMddHHmm, 예: 202607312359")
    parser.add_argument("--num-rows", type=int, default=500)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--debug", action="store_true", help="원본 응답을 state/debug_raw/ 에 덤프")
    args = parser.parse_args()

    collect(args.start, args.end, args.num_rows, args.max_pages, args.debug)
