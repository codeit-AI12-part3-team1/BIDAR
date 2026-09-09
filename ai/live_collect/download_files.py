"""attachments.jsonl 의 PENDING 항목을 실제로 HTTP GET으로 다운로드한다.
API 호출이 아니라 일반 파일 다운로드라 quota와 무관하게 동작한다.

사용 예:
    uv run python download_files.py
    uv run python download_files.py --retry-failed   # NEEDS_RETRY 상태만 재시도
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

import requests

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_files")

MAGIC_SIGNATURES = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip_family",  # hwpx/docx/xlsx/zip 은 모두 zip 컨테이너
    b"\xd0\xcf\x11\xe0": "ole_family",  # 구 hwp/doc/xls (OLE Compound File)
    b"HWP Document File": "hwp_v5",
}

BINARY_EXTS = {".hwp", ".hwpx", ".pdf", ".xlsx", ".xls", ".docx", ".doc", ".zip"}

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    name = _UNSAFE_CHARS.sub("_", name).strip()
    return name or "unnamed"


def guess_filename(url: str, hint: str | None, content_type: str) -> str:
    if hint:
        return sanitize_filename(hint)
    tail = url.rstrip("/").split("/")[-1].split("?")[0]
    if tail and "." in tail:
        return sanitize_filename(tail)
    ext = {
        "application/pdf": ".pdf",
        "application/vnd.hancom.hwp": ".hwp",
    }.get(content_type.split(";")[0].strip(), "")
    return sanitize_filename(f"download{ext or ''}")


def sniff_magic(head: bytes) -> str | None:
    for sig, kind in MAGIC_SIGNATURES.items():
        if head.startswith(sig):
            return kind
    return None


def load_rows() -> list[dict]:
    rows = []
    with config.ATTACHMENTS_MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def save_rows(rows: list[dict]) -> None:
    with config.ATTACHMENTS_MANIFEST.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def download_one(session: requests.Session, url: str, dest_dir: Path, filename: str) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    last_error = ""
    for attempt in range(1, 4):
        try:
            resp = session.get(url, timeout=30, stream=True)
            content_type = resp.headers.get("Content-Type", "")

            if resp.status_code == 404:
                return {"download_status": "FAIL", "detail": "404 Not Found"}
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 * attempt)
                continue
            resp.raise_for_status()

            sha256 = hashlib.sha256()
            size = 0
            head_bytes = b""
            with dest_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    if len(head_bytes) < 32:
                        head_bytes += chunk[: 32 - len(head_bytes)]
                    f.write(chunk)
                    sha256.update(chunk)
                    size += len(chunk)

            if size == 0:
                dest_path.unlink(missing_ok=True)
                return {"download_status": "FAIL", "detail": "empty response body"}

            kind = sniff_magic(head_bytes)
            is_html = head_bytes.lstrip()[:15].lower().startswith(b"<!doctype html") or head_bytes.lstrip()[:5].lower() == b"<html"
            if is_html:
                dest_path.unlink(missing_ok=True)
                return {
                    "download_status": "NEEDS_BROWSER",
                    "detail": "HTML 응답 (로그인/세션 필요 가능성) - Playwright fallback 필요",
                }

            status = "SUCCESS" if kind else "SUCCESS_WITH_WARNING"
            detail = "" if kind else "확장자/매직바이트 불일치 - 수동 확인 권장"

            return {
                "download_status": status,
                "detail": detail,
                "filename_normalized": dest_path.name,
                "local_path": str(dest_path),
                "mime_type": content_type,
                "file_size": size,
                "sha256": sha256.hexdigest(),
            }

        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = str(e)
            time.sleep(2 * attempt)
            continue
        except requests.HTTPError as e:
            return {"download_status": "FAIL", "detail": str(e)}

    return {"download_status": "NEEDS_RETRY", "detail": f"3회 재시도 실패: {last_error}"}


def main(retry_failed: bool = False) -> None:
    rows = load_rows()
    session = requests.Session()
    sha_index: dict[str, str] = {}

    target_statuses = {"NEEDS_RETRY"} if retry_failed else {"PENDING"}

    done = {"SUCCESS": 0, "SUCCESS_WITH_WARNING": 0, "NEEDS_RETRY": 0, "NEEDS_BROWSER": 0, "FAIL": 0}

    for row in rows:
        if row.get("marker") == "processed":
            continue
        if row.get("download_status") not in target_statuses:
            continue

        dest_dir = config.ATTACHMENTS_RAW_DIR / f"{row['bid_notice_no']}_{row['bid_notice_ord']}"
        filename = guess_filename(row["url"], row.get("filename_hint"), "")

        result = download_one(session, row["url"], dest_dir, filename)

        if result.get("sha256") and result["sha256"] in sha_index:
            # 이미 동일 내용 파일이 있으면 중복 저장 대신 원본 경로를 참조
            Path(result["local_path"]).unlink(missing_ok=True)
            result["local_path"] = sha_index[result["sha256"]]
            result["detail"] = (result.get("detail", "") + " [dedup: 기존 파일 재사용]").strip()
        elif result.get("sha256"):
            sha_index[result["sha256"]] = result["local_path"]

        row.update(result)
        row["download_method"] = "OPENAPI_HTTP"
        done[result["download_status"]] = done.get(result["download_status"], 0) + 1

        logger.info("%s [%s] %s", row["bid_notice_no"], result["download_status"], filename)
        time.sleep(0.1)

    save_rows(rows)
    logger.info("다운로드 완료: %s", done)
    needs_browser = done.get("NEEDS_BROWSER", 0)
    if needs_browser:
        logger.info("%s건은 세션/로그인 필요 추정 - Playwright fallback 대상입니다 (아직 미구현)", needs_browser)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    main(args.retry_failed)
