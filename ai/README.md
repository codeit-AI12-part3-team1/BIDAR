# BIDAR AI

임베딩 생성, RAG 검색/생성, 모델 학습·추론 등 **모델 관련 코드 전체**를 담당하는 패키지입니다. `backend`는 이 패키지를 로컬 편집 가능 설치(`pip install -e`)로 의존성에 추가해 같은 프로세스 안에서 직접 호출합니다.

## 디렉터리 구조

```
ai/
├── pyproject.toml           # 패키지 정의 (backend가 이걸로 설치)
├── src/ai/
│   ├── embeddings/
│   │   └── embedder.py      # 텍스트 → 벡터 임베딩 생성
│   ├── rag/
│   │   ├── retriever.py     # 벡터 검색
│   │   ├── chain.py         # 프롬프트 조합 + LLM 호출
│   │   └── prompts/         # 프롬프트 템플릿
│   ├── models/
│   │   └── predictor.py     # 학습된 모델 로드 + 추론 (분류/추천 등)
│   ├── training/
│   │   └── train.py         # 모델 학습 스크립트
│   └── ingestion/
│       ├── loaders.py       # raw_data → 문서 로딩
│       ├── chunking.py      # 텍스트 분할
│       └── indexer.py       # 임베딩 생성 + 벡터 색인 구축
├── scripts/
│   ├── build_index.py       # ingestion 파이프라인 실행 (색인 재구축)
│   └── evaluate.py          # RAG/모델 응답 품질 평가
├── tests/
│   └── test_rag/
├── data/
│   ├── raw_data/            # 원본 데이터 (git 미추적)
│   ├── processed/           # 전처리 데이터 (git 미추적)
│   └── vector_store/        # 로컬 벡터 인덱스 (git 미추적)
└── requirements.txt
```

## backend와의 연동

`API 호출 → 임베딩 → 예측 → response` 흐름은 하나의 요청 안에서 처리되므로, `ai`를 별도 서버로 띄우지 않고 **backend 프로세스 안에서 직접 import**해서 씁니다.

```bash
# backend/requirements.txt 에 포함된 편집 가능 설치
pip install -e ai/
```

```python
# backend 코드에서 이렇게 호출
from ai.embeddings.embedder import embed_text
from ai.rag.retriever import retrieve
from ai.rag.chain import generate_answer
```

`backend/app/services/`가 이 호출들을 조합해 API 응답을 만듭니다. 서빙 코드(FastAPI 라우팅/스키마)는 [`backend/README.md`](../backend/README.md) 참고.

## 역할 요약

- **embeddings**: 텍스트 → 벡터 변환 (색인 시점, 질의 시점 모두 재사용)
- **rag**: 벡터 검색 + LLM 응답 생성
- **models / training**: RAG 외 별도 예측 모델의 학습·추론 코드
- **ingestion**: 원본 데이터를 색인 가능한 형태로 가공하는 배치 파이프라인
- **scripts**: `ingestion`/`training`을 실행하는 CLI 진입점
