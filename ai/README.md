# BIDAR AI

임베딩 생성, RAG 검색/생성, 모델 학습·추론 등 **모델 관련 코드 전체**를 담당하는 패키지입니다. `backend`는 이 패키지를 로컬 편집 가능 설치(`pip install -e`)로 의존성에 추가해 같은 프로세스 안에서 직접 호출합니다.

## 디렉터리 구조

```
ai/
├── pyproject.toml           # 패키지 정의 (backend가 이걸로 설치)
├── config/
│   └── data/
│       └── custom_split_v0.1.json # Custom leakage-safe split 정책
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
│       ├── custom/          # Custom Dataset 생성 파이프라인
│       │   ├── parsers.py   # HWP/PDF 파싱과 Unicode 정규화
│       │   ├── inventory.py # source identity와 duplicate group
│       │   ├── splitting.py # deterministic group-aware split
│       │   ├── dataset_builder.py # Canonical Document/Block 생성
│       │   ├── chunking.py  # C0 고정 문자 청킹
│       │   └── validation.py # ID/FK/provenance 무결성 검증
│       └── indexer.py       # 임베딩 생성 + 벡터 색인 구축
├── scripts/
│   ├── build_custom_dataset.py # Custom M0~M2 Dataset 생성
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

## M0~M2 Data Pipeline

```text
Source Acquisition → Custom / Standard Dataset Pipeline

Custom Frozen v0.1: Raw Source → Inventory → Duplicate Grouping → Split
→ DEV/REGRESSION Parse
→ Canonical Document → Structural Block → C0 Chunk → Validation
```

RFP100과 LIVE는 원천 문서의 cohort이고, Custom과 Standard는 Dataset 구성 방식입니다.
현재 구현된 Custom 파이프라인은 `ai.ingestion.custom` namespace에 있으며, Standard
파이프라인은 향후 별도 namespace에서 독립적으로 관리합니다.

`ai.ingestion.custom.parsers`는 원본 HWP5 또는 PDF 파일을 읽고 Unicode NFC로 정규화된
primitive text block과 페이지·섹션·레코드 위치 정보를 반환합니다. 이 provenance는
`dataset_builder`와 `chunking`에서 document/block/chunk ID, section, requirement,
page, char 범위에 연결됩니다. C0는 `fixed-char-1200-o200-v0.1` 규칙을 사용하며,
마지막 단계에서 ID, FK, 범위, coverage와 provenance를 검증합니다.

기본 split은 duplicate group을 분리하지 않는 범위에서 DEV 70%, REGRESSION 15%,
FINAL_HOLDOUT 15%에 가장 가깝게 배정합니다. `inventory.csv`는 팀 source tracking,
`split.csv`는 partition SSOT이며 각각 동일 내용의 machine-readable JSON 출력을
함께 생성합니다.

Frozen v0.1의 FINAL_HOLDOUT은 inventory와 split assignment만 유지합니다. M2에서는
parse/canonicalize/chunk하지 않으며, 세부 기준은 기존 Frozen Data Contract를 따릅니다.

패키지를 설치한 뒤 한 명령으로 inventory/split과 `documents.jsonl`, `blocks.jsonl`,
`chunks.jsonl`, validation 및 deterministic manifest를 생성할 수 있습니다.

```bash
pip install -e ai/
python ai/scripts/build_custom_dataset.py \
  --raw-dir path/to/raw \
  --metadata path/to/metadata.csv \
  --split-config ai/config/data/custom_split_v0.1.json \
  --output-dir path/to/output
```

RFP100 v0.1을 기존 canonical ID까지 동일하게 재현하려면 원본 파일과 기존
metadata/ID mapping CSV 및 authoritative frozen split mapping을 `--frozen-split`으로
함께 제공해야 하며 새로 분할하지 않습니다. 새 원천에서 mapping을 생략하면 SHA-256
기반 canonical ID와 명시된 seed로 deterministic group-aware split을 생성합니다.

Canonical Dataset과 원본·가공 데이터는 GitHub에 포함하지 않습니다. 실제 Dataset은
별도 팀 공유 저장소(MyBox)를 사용합니다. 봉인된 평가 데이터의 접근·처리는 Dataset
Builder가 아닌 팀 운영 정책을 따르며, 이 저장소의 fixture나 test에 포함하지 않습니다.

Frozen v0.1 재현을 위해 historical requirement ID 정규식 동작을 유지하므로 일부
비요구사항 문자열을 requirement ID로 인식할 수 있습니다.

- [Data Contract v0.1](./src/ai/docs/DATA_CONTRACT_v0.1_FROZEN.md)
- [Data Dictionary v0.1](./src/ai/docs/DATA_DICTIONARY_v0.1.md)

## 파트별 문서

- [Retrieval 문서](./RETRIEVAL.md)
- [Generator 문서](./GENERATOR.md)
