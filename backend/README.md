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
│   │   │   ├── chat.py        # 질의응답 엔드포인트
│   │   │   └── search.py      # 검색/추천 엔드포인트
│   │   └── deps.py            # 의존성 주입
│   ├── services/
│   │   └── prediction_service.py  # ai.embeddings/ai.rag/ai.models 호출을 조합해 응답 생성
│   └── schemas/
│       └── schemas.py         # request/response Pydantic 모델
├── tests/
│   └── test_api/
├── requirements.txt            # fastapi 등 + ai 패키지 editable install
└── .env.example
```

## 요청 흐름

```
API 호출 → (services) 임베딩 → 예측/검색 → response
             └─ ai.embeddings, ai.rag, ai.models 호출
```

라우터(`api/routes`)는 요청을 받아 `services`에 위임하고, `services`가 `ai` 패키지의 함수를 호출해 결과를 조합한 뒤 `schemas`로 응답을 반환합니다. 모델/임베딩 코드 자체는 이 저장소에 두지 않습니다.

## 실행 (예정)

```bash
pip install -r requirements.txt   # ai 패키지도 editable로 함께 설치됨
cp .env.example .env
uvicorn app.main:app --reload
```
