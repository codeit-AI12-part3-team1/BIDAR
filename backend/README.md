# BIDAR Backend

FastAPI 기반 API 서버입니다. 라우팅/요청 검증/응답 조합을 담당하며, 임베딩·RAG·모델 추론 등 **모델 관련 로직은 [`ai`](../ai/README.md) 패키지를 import해서** 사용합니다.

## 디렉터리 구조

```
backend/
├── app/
│   ├── main.py                # FastAPI 엔트리포인트
│   ├── core/
│   │   ├── config.py          # 환경변수/설정 (pydantic Settings)
│   │   └── logging.py         # 로깅 설정
│   ├── api/
│   │   ├── routes/
│   │   │   ├── health_check.py  # 헬스체크 엔드포인트 (GET /health)
│   │   │   ├── chat.py        # 질의응답 엔드포인트 (POST /chat)
│   │   │   └── search.py      # 검색/추천 엔드포인트 (예정)
│   │   └── deps.py            # 의존성 주입 (예정)
│   ├── services/
│   │   └── prediction_service.py  # predict(query) — 현재는 임시 텍스트 반환, 추후 ai.models.predictor 연동
│   └── schemas/
│       └── schemas.py         # request/response Pydantic 모델, BaseResponse(code/msg/data)
├── scripts/
│   ├── start.sh                # venv 활성화 + uvicorn 실행 (systemd ExecStart용)
│   └── bidar-backend.service    # systemd 유닛 템플릿
├── tests/
│   └── test_api/
├── requirements.txt            # fastapi 등 + ai 패키지 editable install
└── .env                        # 현재 사용하는 환경변수 없음, 필요해지면 채우면 됨
```

## 요청 흐름

```
API 호출 → (services) 임베딩 → 예측/검색 → response
             └─ ai.embeddings, ai.rag, ai.models 호출
```

라우터(`api/routes`)는 요청을 받아 `services`에 위임하고, `services`가 `ai` 패키지의 함수를 호출해 결과를 조합한 뒤 `schemas`로 응답을 반환합니다. 모델/임베딩 코드 자체는 이 저장소에 두지 않습니다.

## 응답 규약

모든 API는 `schemas.BaseResponse[T]`(`code`, `msg`, `data`)로 감싸서 응답합니다. `data`는 nullable입니다.

```python
from app.schemas.schemas import BaseResponse, success, error

@router.get("/health", response_model=BaseResponse[str])
def health_check() -> BaseResponse[str]:
    return success(data="ok")          # {"code": 200, "msg": "success", "data": "ok"}
    # 실패 시: return error(msg="...", code=500)
```

## 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows / PowerShell
# source .venv/bin/activate         # Linux / macOS
pip install -r requirements.txt     # ai 패키지도 editable로 함께 설치됨
uvicorn app.main:app --reload
```

IntelliJ 등 IDE 실행 설정을 쓸 경우 working directory를 반드시 `backend`로 지정해야 합니다 (프로젝트 루트로 두면 `app` 모듈을 못 찾음).

## 엔드포인트

| Method | Path     | 설명                                   |
|--------|----------|----------------------------------------|
| GET    | `/health`| 헬스체크 → `{"code": 200, "msg": "success", "data": "ok"}` |
| POST   | `/chat`  | 질의응답. `query`(str), `use_streaming`(bool, 기본 False). 현재 `prediction_service.predict()`가 임시 텍스트 반환. `use_streaming=True`는 아직 501 |

## 배포 (systemd)

리눅스 서버에서 프로세스가 죽어도 자동 재시작되도록 systemd로 관리합니다.

```bash
# 서버에서 최초 1회
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# scripts/bidar-backend.service의 WorkingDirectory/ExecStart/User를
# 실제 배포 경로·계정에 맞게 수정한 뒤
sudo cp scripts/bidar-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bidar-backend
```

`scripts/start.sh`가 `.venv` 활성화 후 `uvicorn app.main:app`을 실행하며, `Restart=on-failure`로 크래시 시 자동 재시작됩니다.
