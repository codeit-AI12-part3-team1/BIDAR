# BIDAR 검색기 (Retrieval)

`ai.rag.retriever` — 질문을 받아 **사용자가 선택한 RFP 문서 안에서** 근거 청크를 찾습니다.

패키지 전체 구조·설치는 [`README.md`](README.md), 생성기는 [`GENERATOR.md`](GENERATOR.md) 를 보세요.

---

## 빠른 시작

색인이 이미 만들어져 있다면 이게 전부입니다.

```python
from ai.rag.retriever import retrieve

hits = retrieve("이 사업의 소요예산은 얼마인가?", top_k=5, document_id="DOC_001")
```

색인이 없다면 [색인 만들기](#색인-만들기) 를 먼저 하세요.

---

## API

### `retrieve(question, top_k=5, *, document_id)`

| 인자 | 타입 | 설명 |
|---|---|---|
| `question` | `str` | 질문 |
| `top_k` | `int` | 반환할 청크 수. 기본 5 |
| `document_id` | `str` | **필수 · 키워드 전용.** 검색할 문서 |

`document_id` 는 기본값이 없어 안 넘기면 호출이 성립하지 않습니다. 위치 인자로도 못 넘겨서 `top_k` 자리와 헷갈릴 일이 없습니다.

### 반환값

`list[dict]` — 각 항목이 8개 필드를 가집니다.

| 필드 | 내용 |
|---|---|
| `rank` | 1부터 시작하는 순위 |
| `chunk_id` | 청크 식별자 (예: `DOC_001-C00012`) |
| `document_id` | 소속 문서 |
| `score` | 유사도 (0~1, 높을수록 관련) |
| `text` | 청크 본문 |
| `section_path` | 문서 내 섹션 경로 |
| `requirement_ids` | 연결된 요구사항 ID |
| `block_ids` | 원문 블록 ID |

이 목록이 그대로 `generate_answer()` 의 `hits` 입력이 됩니다.

해당 문서에 청크가 없으면 빈 리스트를 돌려줍니다.

### 예외

| 상황 | 예외 |
|---|---|
| `document_id` 를 안 넘김 | `ValueError` |
| 색인 경로에 한글 등이 포함 | `ValueError` — [주의사항](#색인-경로에-한글이-들어가면-안-됩니다) |
| 결과에 다른 문서 청크가 섞임 | `RuntimeError: RETRIEVAL_SCOPE_ERROR` |

### 그 외 함수

| 함수 | 언제 |
|---|---|
| `load_retriever()` | backend 기동 시 미리 호출해 첫 요청 지연을 없앨 때. `retrieve()` 가 알아서 부르므로 보통은 불필요 |
| `is_retriever_loaded()` | 로드 여부 확인 |

### backend 에서

```python
from ai.models.predictor import predict
answer: str = predict(query, document_id)
```

`retrieve()` → `generate_answer()` 를 묶은 진입점입니다. 별도 서버 없이 backend 프로세스 안에서 함수 호출로 씁니다.

---

## 색인 만들기

```bash
python ai/scripts/build_index.py --persist-dir C:/bidar/vector_store
```

C0 청크를 KURE-v1 으로 임베딩해 Chroma 에 저장합니다. 시간이 조금 걸립니다

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--persist-dir` | `ai/data/vector_store` | 색인 저장 경로 |
| `--collection` | `rfp_chunks` | 컬렉션 이름 |
| `--device` | `cuda` | 임베딩 디바이스 |
| `--batch-size` | 256 | 임베딩 계산 단위 |
| `--sync-threshold` | 100 | HNSW 를 디스크로 내리는 임계치 |
| `--keep-existing` | (끔) | 붙이면 기존 폴더를 비우지 않음 |

기본은 폴더를 비우고 새로 만듭니다. Chroma 가 컬렉션을 다시 만들 때 새 UUID 폴더를 생성해서, 안 비우면 옛 세그먼트가 남아 어느 쪽이 현재 색인인지 알 수 없습니다.

### 환경변수

| 변수 | 기본값 | 용도 |
|---|---|---|
| `AI_RETRIEVER_PERSIST_DIR` | `ai/data/vector_store` | 검색 시 읽을 색인 경로 |
| `AI_RETRIEVER_COLLECTION` | `rfp_chunks` | 컬렉션 이름 |
| `AI_RETRIEVER_DEVICE` | `cuda` | 임베딩 디바이스. `cpu` 로 내릴 수 있음 |

색인을 기본 경로가 아닌 곳에 만들었다면 `AI_RETRIEVER_PERSIST_DIR` 를 맞춰줘야 검색이 그 색인을 찾습니다.

---

## 동작 방식

```
질문 + document_id
      ↓
질문만 임베딩            문서 전체를 다시 처리하지 않음
      ↓
document_id 필터         후보를 그 문서 청크로 좁힘
      ↓
코사인 유사도 계산        좁혀진 후보 안에서만
      ↓
상위 5건
```

| 구성 | 값 |
|---|---|
| 임베딩 모델 | `nlpai-lab/KURE-v1` (1,024차원, 정규화) |
| 벡터 DB | Chroma `PersistentClient` |
| 유사도 | cosine |



---

## 문제가 생기면

### 색인 경로에 한글이 들어가면 안 됩니다

chromadb 1.5.9 는 ASCII 밖 문자가 포함된 경로에서 HNSW 색인(`.bin`)을 만들지 못합니다 (실측 2026-09-01).

```
chromadb.errors.InternalError: Error constructing hnsw segment reader:
Error creating hnsw segment reader: Error loading hnsw index
```

색인 생성은 성공한 것처럼 끝나고 `chroma.sqlite3` 도 만들어지는데, 검색할 때 위 에러가 납니다.

**해결** — 색인만 ASCII 경로에 두고 환경변수로 지정하세요.

```powershell
setx AI_RETRIEVER_PERSIST_DIR "C:\bidar\vector_store"
```

`setx` 값은 **새로 여는 터미널부터** 적용됩니다. 이후 `assert_index_path_ok()` 가 색인 생성 전에 경로를 검사해 미리 막습니다.

저장소 자체는 문제없고 `data/vector_store/` 는 git 미추적이라, 각자 로컬에서만 발생합니다.

### 색인이 온전한지 확인하려면

**개수 확인만으로는 알 수 없습니다.** Chroma 는 청크 원본을 `chroma.sqlite3` 에, 검색 그래프를 `.bin` 에 따로 두는데, `count()` 와 `get()` 은 SQLite 만 읽어서 그래프가 비어 있어도 정상으로 나옵니다.

| 스크립트 | 언제 | 속도 |
|---|---|---|
| `verify_index.py` | 색인을 넘겨받았거나 폴더를 옮긴 직후 | 빠름 |
| `verify_index_full_query.py` | 색인이 이상할 때. 전체 청크를 실제로 검색해 확인 | 느림 |
| `smoke_test.py` | 검색기 코드를 고친 뒤 | 빠름 |

```bash
python ai/scripts/verify_index.py --persist-dir C:/bidar/vector_store
python ai/scripts/verify_index_full_query.py --persist-dir C:/bidar/vector_store
python ai/scripts/smoke_test.py
```

`smoke_test.py` 의 2단계(`generate_answer`)는 GPU 와 `gptqmodel` 이 필요해 Windows 로컬에서는 `ImportError` 로 끝납니다. 검색기와 무관한 별개 이슈입니다.

### 검색 결과가 이상할 때

- `document_id` 가 맞는지 — 다른 공고를 지정하면 당연히 엉뚱한 결과가 나옵니다
- `AI_RETRIEVER_PERSIST_DIR` 가 실제 색인 위치를 가리키는지
- 색인을 만든 모델과 지금 검색하는 모델이 같은지 (아래 참고)

---

## 알아둘 제약

**모델을 바꾸면 전체 재색인이 필요합니다.**
색인과 질의는 같은 모델·같은 정규화 설정을 써야 합니다. 다르면 좌표계가 달라져 유사도 계산이 무의미해집니다. 설정 변경이 아니라 20~30분짜리 재구축 작업입니다.

**chromadb 버전은 `1.5.9` 로 고정입니다.**
낮은 버전은 높은 버전이 만든 색인을 열지 못합니다. `pyproject.toml` 에 못박혀 있습니다.

**메모리는 VRAM 이 아니라 RAM 을 씁니다.**
검색 그래프를 시스템 메모리에 올려 탐색하고, 원문은 SQLite 라 디스크에 남습니다. 벡터 1개당 약 4.2 KB(실측)로, 현재 4,931 청크 기준 20 MB 입니다. 100만 청크면 약 4.2 GB 이므로 데이터가 커지면 VRAM 보다 RAM 이 먼저 부족해집니다.

**한 번에 한 문서만 검색합니다.**
`document_id` 가 필수라 "IT 사업 추천해줘" 같은 문서 탐색형 질문은 받을 수 없습니다. 사용자가 공고를 고른 뒤에만 질문이 가능합니다.

**시나리오 B(API 임베딩)는 코드만 있습니다.**
`OpenAIEmbedder` 로 `text-embedding-3-small` 을 쓸 수 있게 구현돼 있으나 측정하지 않았습니다. 전환 시 차원이 1,024 → 1,536 으로 달라져 컬렉션도 새로 만들어야 합니다.

---

## 참고 — 현재 성능

C0 청크 4,931건 · Gold 14문항 · top_k=5 기준입니다.

| 지표 | 결과 |
|---|---|
| Hit@5 | 1.000 (14/14) |
| nDCG@5 | 0.855 |
| MRR | 0.821 |
| Scope Violation | 0건 |
| 색인 무결성 | 4,931 / 4,931 |

**평가 문항이 15개라 확정적인 수치는 아닙니다.** 14/14 의 Wilson 95% 신뢰구간은 약 76~100% 입니다.

알려진 약점으로 조건형 질문(`QUALIFICATION_CONDITION`)의 1위 적중이 4문항 중 1건입니다. 정답을 놓치는 것은 아니고 순위가 2~3위로 밀립니다. BM25 결합을 검토 중입니다.

모델 선정 과정, 상세 측정 결과, 트러블슈팅 기록은 별도 문서로 정리돼 있습니다.
