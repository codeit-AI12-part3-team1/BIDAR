"""selected=true 인 공고에 대해 첨부파일 정보(다운로드 URL)를 조회한다.
공고 목록 API 응답 자체에 들어있는 Url 필드 + 별도 첨부정보 오퍼레이션 응답을
모두 훑어서 attachments.jsonl 에 후보 URL을 모은다 (아직 다운로드는 하지 않음).

사용 예:
    uv run python collect_attachments.py
"""
from __future__ import annotations

import json
import logging
import time

import config
from api_client import G2BClient, extract_attachment_candidates
from quota import QuotaExceeded, QuotaTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collect_attachments")


def load_selected_bids() -> list[dict]:
    rows = []
    with config.BIDS_MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("selected"):
                rows.append(row)
    return rows


def load_processed_keys() -> set[str]:
    seen = set()
    if config.ATTACHMENTS_MANIFEST.exists():
        with config.ATTACHMENTS_MANIFEST.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("marker") == "processed":
                    seen.add(f"{row['bid_notice_no']}-{row['bid_notice_ord']}-processed")
    return seen


def main(debug: bool = False) -> None:
    client = G2BClient(quota=QuotaTracker(), debug=debug)
    bids = load_selected_bids()
    processed = load_processed_keys()

    done, skipped, no_attachment = 0, 0, 0

    with config.ATTACHMENTS_MANIFEST.open("a", encoding="utf-8") as out_f:
        for bid in bids:
            key = f"{bid['bid_notice_no']}-{bid['bid_notice_ord']}-processed"
            if key in processed:
                skipped += 1
                continue

            candidates = []

            # 1) 공고 목록 원본 응답에 이미 포함된 URL 필드
            with open(bid["raw_path"], encoding="utf-8") as f:
                notice_item = json.load(f)
            candidates += [
                {**c, "source_operation": config.NOTICE_LIST_OPERATION}
                for c in extract_attachment_candidates(notice_item)
            ]

            # 2) 전용 첨부정보 오퍼레이션 (계획서 기준, 존재 여부는 실호출로 검증됨)
            for op in config.ATTACHMENT_OPERATIONS:
                try:
                    data = client.get_attachment_info(op, bid["bid_notice_no"], bid["bid_notice_ord"])
                except QuotaExceeded as e:
                    logger.warning("%s", e)
                    _flush_remaining(out_f, bid, candidates, done)
                    return
                if not data:
                    continue
                items = data.get("response", {}).get("body", {}).get("items", []) or []
                for it in items:
                    candidates += [{**c, "source_operation": op} for c in extract_attachment_candidates(it)]

            if not candidates:
                no_attachment += 1

            for c in candidates:
                row = {
                    "bid_notice_no": bid["bid_notice_no"],
                    "bid_notice_ord": bid["bid_notice_ord"],
                    "source_operation": c["source_operation"],
                    "field": c["field"],
                    "url": c["url"],
                    "filename_hint": c.get("filename_hint"),
                    "download_status": "PENDING",
                }
                out_f.write(json.dumps(row, ensure_ascii=False) + "\n")

            # 첨부가 하나도 없어도 "처리 완료"는 기록해 재실행 시 중복 호출을 막는다
            out_f.write(json.dumps({
                "bid_notice_no": bid["bid_notice_no"],
                "bid_notice_ord": bid["bid_notice_ord"],
                "marker": "processed",
            }, ensure_ascii=False) + "\n")

            done += 1
            time.sleep(0.2)

    logger.info("완료: 처리 %s건, 스킵(이미처리) %s건, 첨부없음 %s건", done, skipped, no_attachment)


def _flush_remaining(*_args, **_kwargs) -> None:
    logger.warning("할당량 소진으로 중단. 이미 처리된 건은 저장됨. 내일 재실행하면 이어서 진행됩니다.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    main(args.debug)
