from __future__ import annotations

import json
from datetime import date

import config


class QuotaExceeded(RuntimeError):
    pass


class QuotaTracker:
    """하루 API 호출 횟수를 파일에 지속시켜, 재실행해도 누적 한도를 넘지 않게 한다."""

    def __init__(self, limit: int = config.DAILY_CALL_LIMIT):
        self.limit = limit
        self.path = config.QUOTA_STATE_FILE
        self._state = self._load()

    def _load(self) -> dict:
        today = date.today().isoformat()
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state.get("date") == today:
                return state
        return {"date": today, "calls": 0}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, ensure_ascii=False), encoding="utf-8")

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self._state["calls"])

    def record_call(self) -> None:
        self._state = self._load()  # 다른 프로세스가 갱신했을 수 있어 매번 재확인
        if self._state["calls"] >= self.limit:
            raise QuotaExceeded(
                f"오늘({self._state['date']}) API 호출 한도 {self.limit}건 도달. 내일 다시 실행하세요."
            )
        self._state["calls"] += 1
        self._save()

    def ensure_available(self, n: int = 1) -> None:
        self._state = self._load()
        if self._state["calls"] + n > self.limit:
            raise QuotaExceeded(
                f"오늘 호출 {self._state['calls']}건 + 요청 {n}건이 한도 {self.limit}건을 초과합니다."
            )
