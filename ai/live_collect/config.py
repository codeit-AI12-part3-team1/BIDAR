from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data" / "live"
STATE_DIR = BASE_DIR / "state"

load_dotenv(BASE_DIR / ".env")


def _normalize_service_key(raw: str) -> str:
    """data.go.kr이 Encoding/Decoding 키를 구분 없이 하나만 보여주는 경우가 있어,
    percent-encoding( %2B, %2F, %3D 등)이 섞여 있으면 원래(디코딩된) 값으로 되돌린다.
    requests가 요청 시 자체적으로 다시 인코딩하므로, 여기서는 항상 '디코딩된' 형태를 유지해야 한다."""
    if re.search(r"%[0-9A-Fa-f]{2}", raw):
        return unquote(raw)
    return raw


SERVICE_KEY = _normalize_service_key(os.environ.get("G2B_SERVICE_KEY", ""))
DAILY_CALL_LIMIT = int(os.environ.get("G2B_DAILY_CALL_LIMIT", "480"))

API_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

# 사업 대상 오퍼레이션 (용역 우선, 필요시 물품/공사 추가)
NOTICE_LIST_OPERATION = "getBidPblancListInfoServc"

# 실호출로 확인됨: inqryBgnDt~inqryEndDt 조회기간이 30일을 넘으면(31일부터)
# resultCode=07 "입력범위값 초과 에러"로 실패한다 (2026-08-28 검증, 30일=OK/31일=실패).
MAX_QUERY_SPAN_DAYS = 30

# 계획서에 명시된 첨부정보 전용 오퍼레이션. 정확한 존재 여부/필드는
# 첫 실호출 응답(response header resultCode/resultMsg)으로 검증 필요.
ATTACHMENT_OPERATIONS = [
    "getBidPblancListInfoEorderAtchFileInfo",  # e발주 첨부파일정보
    "getBidPblancListPPIFnlRfpIssAtchFileInfo",  # 혁신장터 최종제안요청서 첨부파일정보
]

NOTICES_RAW_DIR = DATA_DIR / "raw" / "notices"
ATTACHMENTS_RAW_DIR = DATA_DIR / "raw" / "attachments"
MANIFESTS_DIR = DATA_DIR / "manifests"
GOVERNANCE_DIR = DATA_DIR / "governance"

BIDS_MANIFEST = MANIFESTS_DIR / "bids.jsonl"
ATTACHMENTS_MANIFEST = MANIFESTS_DIR / "attachments.jsonl"

REQUEST_LOG = STATE_DIR / "request_log.jsonl"
QUOTA_STATE_FILE = STATE_DIR / "quota_state.json"
DEBUG_RAW_DIR = STATE_DIR / "debug_raw"

# 실호출로 확인된 공식 대분류(pubPrcrmntLrgClsfcNm) 값. "기술용역"은 감리/설계 등
# 계약방식 구분(srvceDivNm)일 뿐 IT 여부와 무관해서 사용하지 않음 - 대신 이 대분류를 1차 필터로 쓴다.
PRIMARY_LARGE_CATEGORY = "ICT 서비스"

# 대분류가 ICT 서비스가 아니어도 건져올 보조 키워드 (2순위 fallback, 실측상 거의 안 씀)
FALLBACK_KEYWORDS_TIER2 = ["사물인터넷", "IoT", "네트워크", "통신망", "정보시스템", "플랫폼"]

# ICT 서비스 안에서 사업명 우선순위를 매기는 키워드 (SW/AI 최우선)
KEYWORD_TIERS: dict[int, list[str]] = {
    1: [
        "소프트웨어", "SW", "인공지능", "AI", "정보시스템", "플랫폼", "빅데이터",
        "데이터", "챗봇", "클라우드", "ISP", "ISMP", "정보화전략", "시스템 구축",
        "시스템구축", "고도화", "차세대",
    ],
    2: [
        "사물인터넷", "IoT", "네트워크", "통신", "보안", "스마트",
    ],
}

for _d in (NOTICES_RAW_DIR, ATTACHMENTS_RAW_DIR, MANIFESTS_DIR, GOVERNANCE_DIR, STATE_DIR, DEBUG_RAW_DIR):
    _d.mkdir(parents=True, exist_ok=True)
