from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

import config
from quota import QuotaTracker

logger = logging.getLogger("g2b")

_TRAILING_DIGITS_RE = re.compile(r"(\d*)$")
_STEM_STRIP_RE = re.compile(r"(Url|FileNm|Fnm|Nm|Name)\d*$", re.IGNORECASE)


class ApiError(RuntimeError):
    pass


def _log_request(operation: str, params: dict, status: str, detail: str = "") -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "params": {k: v for k, v in params.items() if k != "ServiceKey"},
        "status": status,
        "detail": detail,
    }
    with config.REQUEST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class G2BClient:
    def __init__(self, quota: QuotaTracker | None = None, debug: bool = False):
        if not config.SERVICE_KEY:
            raise RuntimeError("G2B_SERVICE_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        self.quota = quota or QuotaTracker()
        self.debug = debug
        self.session = requests.Session()

    def _call(self, operation: str, params: dict, max_retries: int = 5) -> dict:
        url = f"{config.API_BASE_URL}/{operation}"
        req_params = {
            "ServiceKey": config.SERVICE_KEY,
            "type": "json",
            **params,
        }

        self.quota.ensure_available(1)

        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(url, params=req_params, timeout=25)
                self.quota.record_call()

                if resp.status_code == 429:
                    wait = 5 * attempt
                    _log_request(operation, params, "RATE_LIMITED", f"429, wait {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = 2 * attempt
                    _log_request(operation, params, "SERVER_ERROR", f"{resp.status_code}, wait {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()

                data = resp.json()
                if self.debug:
                    self._dump_debug(operation, params, data)

                # 정상 응답이 아니면 최상위 키가 'response'가 아니라
                # 'nkoneps.com.response.ResponseError' 등으로 나오는 경우가 있다
                # (예: resultCode 07 "입력범위값 초과 에러" - 조회기간이 너무 넓을 때).
                if "response" not in data:
                    error_body = next(iter(data.values()), {}) if data else {}
                    header = error_body.get("header", {})
                    result_code = header.get("resultCode", "UNKNOWN")
                    msg = header.get("resultMsg", str(data)[:200])
                    _log_request(operation, params, "API_ERROR", f"{result_code}: {msg}")
                    raise ApiError(f"[{operation}] resultCode={result_code} msg={msg}")

                header = data["response"].get("header", {})
                result_code = header.get("resultCode")
                if result_code not in (None, "00", "0"):
                    msg = header.get("resultMsg", "")
                    _log_request(operation, params, "API_ERROR", f"{result_code}: {msg}")
                    raise ApiError(f"[{operation}] resultCode={result_code} msg={msg}")

                _log_request(operation, params, "OK")
                return data

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = str(e)
                wait = 2 * attempt
                _log_request(operation, params, "TIMEOUT_RETRY", f"attempt {attempt}, wait {wait}s")
                time.sleep(wait)
                continue
            except ValueError as e:  # JSON 파싱 실패 (XML 에러 응답 등)
                last_error = f"JSON decode failed: {e}; body[:300]={resp.text[:300]!r}"
                _log_request(operation, params, "PARSE_ERROR", last_error)
                raise ApiError(last_error) from e

        raise ApiError(f"[{operation}] {max_retries}회 재시도 실패: {last_error}")

    def _dump_debug(self, operation: str, params: dict, data: dict) -> None:
        fname = f"{operation}_{int(time.time()*1000)}.json"
        (config.DEBUG_RAW_DIR / fname).write_text(
            json.dumps({"params": params, "response": data}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_service_bid_list(
        self, begin_dt: str, end_dt: str, page_no: int = 1, num_rows: int = 100, inqry_div: str = "1"
    ) -> tuple[list[dict], int]:
        """용역 입찰공고 목록. begin_dt/end_dt 포맷: yyyyMMddHHmm"""
        data = self._call(
            config.NOTICE_LIST_OPERATION,
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": begin_dt,
                "inqryEndDt": end_dt,
                "pageNo": page_no,
                "numOfRows": num_rows,
            },
        )
        body = data.get("response", {}).get("body", {})
        items = body.get("items", []) or []
        total_count = int(body.get("totalCount", 0))
        return items, total_count

    def get_attachment_info(self, operation: str, bid_ntce_no: str, bid_ntce_ord: str) -> dict | None:
        """계획서에 명시된 첨부정보 전용 오퍼레이션 호출. 오퍼레이션명이 실제와 다르면
        API_ERROR로 실패하는데, 이 경우 호출 자체를 건너뛰도록 상위에서 처리한다."""
        try:
            data = self._call(
                operation,
                {"bidNtceNo": bid_ntce_no, "bidNtceOrd": bid_ntce_ord, "pageNo": 1, "numOfRows": 50},
            )
        except ApiError as e:
            logger.warning("attachment operation %s failed for %s-%s: %s", operation, bid_ntce_no, bid_ntce_ord, e)
            return None
        return data


def _stem(key: str) -> str:
    """비교용으로 Url/Nm/FileNm/Name 접미사와 끝자리 숫자를 떼고 소문자화.
    예: ntceSpecDocUrl1 -> 'ntcespecdoc', ntceSpecFileNm1 -> 'ntcespec'"""
    return _STEM_STRIP_RE.sub("", key).lower()


def _trailing_idx(key: str) -> str:
    m = _TRAILING_DIGITS_RE.search(key)
    return m.group(1) if m else ""


def extract_attachment_candidates(item: dict) -> list[dict]:
    """응답 dict에서 http로 시작하는 'Url' 계열 필드를 전부 찾아,
    같은 번호 접미사(1~10 등)를 가진 파일명 계열 필드('Nm'/'FileNm'/'Name')와
    prefix가 가장 비슷한 것끼리 짝지어 반환한다.

    공식 필드명(ntceSpecDocUrl1 -> ntceSpecFileNm1 처럼 Url/Nm 앞의 접두사가
    완전히 같지 않을 수 있음)이 문서마다 조금씩 다를 수 있어, 완전일치 대신
    '동일 번호 + 최장 공통 접두사'로 매칭한다. 실제 응답을 받으면
    state/debug_raw/ 에 원본 JSON이 남으므로 필드명을 눈으로 확인해 조정할 수 있다.
    """
    url_keys = [
        k for k, v in item.items()
        if isinstance(v, str) and v.strip().startswith("http") and "url" in k.lower()
    ]
    name_keys = [
        k for k, v in item.items()
        if isinstance(v, str) and v.strip() and re.search(r"(nm|name)\d*$", k, re.IGNORECASE)
    ]

    candidates = []
    for ukey in url_keys:
        uidx = _trailing_idx(ukey)
        ustem = _stem(ukey)

        best_key, best_score = None, 0
        for nkey in name_keys:
            if _trailing_idx(nkey) != uidx:
                continue
            score = len(os.path.commonprefix([ustem, _stem(nkey)]))
            if score > best_score:
                best_key, best_score = nkey, score

        candidates.append({
            "field": ukey,
            "url": item[ukey],
            "filename_hint": item.get(best_key) if best_key else None,
        })
    return candidates
