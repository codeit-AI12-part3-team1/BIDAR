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

`document_id` 형식은 **색인한 데이터셋에 따라 다릅니다**. 위 `DOC_001` 은 Custom/Standard 기준이고, LIVE 계열은 `doc_2b2a6c4e5381c1bbefca` 같은 해시입니다. [지원 데이터셋](#지원-데이터셋) 을 보세요.

---

## 지원 데이터셋

검색기는 아래 데이터셋을 **코드 수정 없이** 색인합니다. 형식이 서로 다르지만 `loaders.py` 의 어댑터가 읽는 시점에 계약 필드명으로 번역합니다.

| 데이터셋 | 문서 | 청크 | `document_id` 형식 |
|---|---|---|---|
| Custom (RFP100 v0.1) | 70 | 4,931 | `DOC_001` |
| Standard V0 DEV | 70 | 16,880 | `DOC_004` |
| Standard V0 VAL | 15 | 3,481 | `DOC_096` |
| LIVE v0.3 DEV | 79 | 7,990 | `doc_2b2a6c4e...` |
| LIVE v0.3 VAL | 15 | 1,130 | `doc_5582c0ad...` |

**`document_id` 체계가 데이터셋마다 다릅니다.** 색인에 없는 ID로 검색하면 예외가 아니라 **빈 리스트**가 돌아오고, 생성기는 근거 없이 그대로 답을 만듭니다. 에러가 안 나서 원인을 찾기 어렵습니다. [ID가 안 맞을 때](#id-가-안-맞을-때) 를 보세요.

### DEV / VAL 은 색인을 나눕니다

같은 색인에 DEV 와 VAL 을 같이 넣으면 검증셋이 개발 검색에 섞일 수 있습니다(split leakage). 데이터팀 권고도 같습니다.

> DEV index 와 VAL index 를 별도로 구축, 또는 하나의 index 를 쓸 경우 `split + document_id` hard filter 를 둘 다 강제
> — `RETRIEVER_HANDOFF_v0.3.md`

`--persist-dir` 와 `--collection` 을 나눠서 만드세요. 어느 split 인지는 색인 메타데이터의 `split` / `semantic_role` 로 사후 확인할 수 있습니다.

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
| `chunk_id` | 청크 식별자 (`DOC_001-C00012` 또는 `chk_015e69e6444a...`) |
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
python ai/scripts/build_index.py \
    --chunks    <청크 JSONL> \
    --documents <문서 JSONL> \
    --persist-dir C:/bidar/vector_store \
    --collection  rfp_chunks
```

청크를 KURE-v1 으로 임베딩해 Chroma 에 저장합니다. 1만 청크에 수십 분 걸립니다.

색인이 여러 개 돌아다니므로 **경로와 컬렉션 이름을 매번 명시하는 편이 안전합니다.** 인자를 생략하면 기본값(Custom RFP100)이 기본 폴더에 만들어져 기존 색인을 덮어씁니다.

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--chunks` | `ai/data/processed/RFP100_chunks_C0_DEV_v0.1.jsonl` | 색인할 청크 |
| `--documents` | `ai/data/processed/RFP100_documents_DEV_v0.1.jsonl` | 제목·기관·예산 출처 |
| `--persist-dir` | `ai/data/vector_store` | 색인 저장 경로 |
| `--collection` | `rfp_chunks` | 컬렉션 이름 |
| `--embed-field` | `text` | 임베딩할 필드. `retrieval_text` 로 바꿀 수 있음 |
| `--device` | `cuda` | 임베딩 디바이스 |
| `--batch-size` | 256 | 임베딩 계산 단위 |
| `--sync-threshold` | 100 | HNSW 를 디스크로 내리는 임계치 |
| `--keep-existing` | (끔) | 붙이면 기존 폴더를 비우지 않음 |

기본은 폴더를 비우고 새로 만듭니다. Chroma 가 컬렉션을 다시 만들 때 새 UUID 폴더를 생성해서, 안 비우면 옛 세그먼트가 남아 어느 쪽이 현재 색인인지 알 수 없습니다.

`--embed-field retrieval_text` 는 사업명·발주기관이 앞에 붙은 검색 전용 텍스트로 임베딩합니다. LIVE/Standard 만 이 필드를 갖고 있습니다. **어느 쪽으로 만들었든 저장되는 본문은 항상 원문(`text`)** 이라 생성기가 보는 내용은 같습니다. 바꾸면 재색인이 필요합니다.

### 환경변수

| 변수 | 기본값 | 용도 |
|---|---|---|
| `AI_RETRIEVER_PERSIST_DIR` | `ai/data/vector_store` | 검색 시 읽을 색인 경로 |
| `AI_RETRIEVER_COLLECTION` | `rfp_chunks` | 컬렉션 이름 |
| `AI_RETRIEVER_DEVICE` | `cuda` | 임베딩 디바이스. `cpu` 로 내릴 수 있음 |
| `AI_RETRIEVER_HYBRID` | `0` | `1` 이면 BM25 를 섞습니다 ([동작 방식](#동작-방식)) |
| `AI_RETRIEVER_SPARSE_WEIGHT` | `0.3` | BM25 쪽 상대 가중치. dense 는 1.0 고정 |
| `AI_RETRIEVER_RRF_K` | `60` | RRF 상수. 클수록 상위권 쏠림이 완화됨 |
| `AI_RETRIEVER_FANOUT` | `8` | 두 축에서 뽑을 후보 수 배수 |

색인을 기본 경로가 아닌 곳에 만들었다면 `AI_RETRIEVER_PERSIST_DIR` 를 맞춰줘야 검색이 그 색인을 찾습니다. **컬렉션 이름이 기본값이 아니면 `AI_RETRIEVER_COLLECTION` 도 같이** 줘야 합니다 — 경로만 맞추면 없는 컬렉션을 찾다가 실패합니다.

아래 넷은 `AI_RETRIEVER_HYBRID=0` 일 때 쓰이지 않습니다.

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

필터가 유사도보다 **앞에** 있는 게 핵심입니다. 질문 문장에는 어느 공고인지가 담겨 있지 않아서, 유사도만으로는 문서를 가려낼 수 없습니다. 그래서 사용자가 고른 문서로 후보를 먼저 가둡니다 (P0 Selected-document scope).

### BM25 하이브리드 (기본 꺼짐)

`AI_RETRIEVER_HYBRID=1` 이면 키워드 검색을 섞습니다.

```
                      ┌─ dense (KURE-v1)  상위 40건
질문 + document_id ───┤
                      └─ BM25 (Kiwi)      상위 40건
                                ↓
                        RRF 로 순위 합산        가중치 1.0 : 0.3
                                ↓
                            상위 5건
```

BM25 색인은 파일로 저장하지 않고 **검색기가 뜰 때 Chroma 안의 본문으로 다시 만듭니다.** 따로 저장하면 `.bin` 과 어긋난 채 배포될 수 있고, 그 어긋남은 조용히 검색 품질만 떨어뜨려 잡기가 어렵습니다. 대신 기동 시간이 늘어납니다(4,931 청크 기준 약 30초).

토크나이저는 데이터팀 인덱스와 맞춰 `kiwipiepy` 를 씁니다. 한국어는 조사를 떼지 않으면 `예산은` 과 `예산` 이 다른 낱말이 되어 BM25 가 사실상 동작하지 않습니다.

**기본이 꺼져 있는 이유는 [현재 성능](#참고--현재-성능) 을 보세요.** 켜면 점수가 떨어집니다.

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
| `smoke_live_cases.py` | 데이터팀 핸드오프 스모크를 회신할 때 | 빠름 |

```bash
python ai/scripts/verify_index.py --persist-dir C:/bidar/vector_store --collection rfp_chunks
python ai/scripts/verify_index_full_query.py --persist-dir C:/bidar/vector_store --collection rfp_chunks
python ai/scripts/smoke_test.py --retrieve-only
```

`smoke_test.py` 의 2단계(`generate_answer`)는 GPU 와 `gptqmodel` 이 필요해 Windows 로컬에서는 `ImportError` 로 끝납니다. 검색기와 무관한 별개 이슈라 `--retrieve-only` 로 건너뛸 수 있습니다.

`verify_index_full_query.py` 는 본문이 똑같은 쌍둥이 청크에 1위를 내준 건수를 `참고` 줄로 따로 찍습니다. 색인 문제는 아니지만 원본 데이터의 중복 신호라 묻지 않고 드러냅니다.

### 데이터팀 스모크 회신

```bash
python ai/scripts/smoke_live_cases.py \
    --cases       <핸드오프>/handoff/SMOKE_CASES_DEV_v0.3.json \
    --package-dir <핸드오프>
```

데이터팀이 준 질문·정답청크로 `RUNTIME_SMOKE_RUNBOOK` 의 PASS 조건을 한 번에 확인합니다 — Top-k 반환, Hard Scope violation 0, `chunk → block → document → provenance` 역추적. `--package-dir` 를 줘야 역추적까지 검사합니다.

생성기 쪽 조건(Generation input schema, Citation invalid ID)은 이 스크립트 범위 밖입니다.

### ID 가 안 맞을 때

증상이 둘로 갈립니다. **원인이 달라서 구분해야 합니다.**

| 증상 | 원인 |
|---|---|
| 예외가 나며 죽음 (`Collection ... does not exist`) | 컬렉션 이름 불일치 |
| **안 죽는데 답이 "근거 없음"만 나옴** | `document_id` 불일치 |

두 번째가 위험합니다. 색인에 없는 `document_id` 로 검색하면 `retrieve()` 가 **빈 리스트**를 돌려주고, 생성기는 그걸로도 그냥 돕니다. 에러가 안 나니 원인을 찾기 어렵습니다.

```python
hits = retrieve(question, document_id=...)
print(len(hits))   # 0 이면 document_id 가 이 색인에 없다
```

`smoke_test.py` 는 이 경우 대체 문서를 골라 알려주고, 그래도 0건이면 중단합니다.

### 검색 결과가 이상할 때

- `document_id` 가 맞는지 — 데이터셋마다 형식이 다릅니다 ([지원 데이터셋](#지원-데이터셋))
- `AI_RETRIEVER_PERSIST_DIR` / `AI_RETRIEVER_COLLECTION` 이 실제 색인을 가리키는지
- 색인을 만든 모델과 지금 검색하는 모델이 같은지 (아래 참고)
- `--embed-field` 를 바꿔놓고 재색인을 안 했는지

---

## 알아둘 제약

**모델을 바꾸면 전체 재색인이 필요합니다.**
색인과 질의는 같은 모델·같은 정규화 설정을 써야 합니다. 다르면 좌표계가 달라져 유사도 계산이 무의미해집니다. 설정 변경이 아니라 20~30분짜리 재구축 작업입니다.

**chromadb 버전은 `1.5.9` 로 고정입니다.**
낮은 버전은 높은 버전이 만든 색인을 열지 못합니다. `pyproject.toml` 에 못박혀 있습니다.

**메모리는 VRAM 이 아니라 RAM 을 씁니다.**
검색 그래프를 시스템 메모리에 올려 탐색하고, 원문은 SQLite 라 디스크에 남습니다. 벡터 1개당 **약 4.2 KB** 입니다 — Custom 4,931 / LIVE 7,990 / Standard 16,880 네 색인에서 모두 같게 나왔습니다(실측). 100만 청크면 약 4.2 GB 이므로 데이터가 커지면 VRAM 보다 RAM 이 먼저 부족해집니다.

`AI_RETRIEVER_HYBRID=1` 이면 BM25 색인이 여기에 더해집니다. 전체 청크의 토큰 목록을 메모리에 들고 있어야 해서, 데이터가 커지면 이쪽이 먼저 문제가 됩니다.

**한 번에 한 문서만 검색합니다.**
`document_id` 가 필수라 "IT 사업 추천해줘" 같은 문서 탐색형 질문은 받을 수 없습니다. 사용자가 공고를 고른 뒤에만 질문이 가능합니다.

**시나리오 B(API 임베딩)는 코드만 있습니다.**
`OpenAIEmbedder` 로 `text-embedding-3-small` 을 쓸 수 있게 구현돼 있으나 측정하지 않았습니다. 전환 시 차원이 1,024 → 1,536 으로 달라져 컬렉션도 새로 만들어야 합니다.

---

## 참고 — 현재 성능

Custom(RFP100) 청크 4,931건 · Gold 14문항 · top_k=5 기준입니다.

| 지표 | 결과 |
|---|---|
| Hit@5 | 1.000 (14/14) |
| nDCG@5 | 0.855 |
| MRR | 0.821 |
| Scope Violation | 0건 |
| 색인 무결성 | 4,931 / 4,931 |

**평가 문항이 15개라 확정적인 수치는 아닙니다.** 14/14 의 Wilson 95% 신뢰구간은 약 76~100% 입니다.

알려진 약점으로 조건형 질문(`QUALIFICATION_CONDITION`)의 1위 적중이 4문항 중 1건입니다. 정답을 놓치는 것은 아니고 순위가 2~3위로 밀립니다.

### BM25 하이브리드는 재봤고, 기각했습니다

위 약점을 노려 BM25 를 붙였지만 **가중치 5종 × 후보폭 3종 = 16조합 중 dense 단독을 이기는 조합이 하나도 없었습니다** (실측 2026-09-08).

| 설정 | Hit@5 | nDCG@5 | MRR |
|---|---|---|---|
| **dense 단독** | **1.000** | **0.855** | **0.821** |
| 하이브리드 (가중 0.1) | 1.000 | 0.855 | 0.821 |
| 하이브리드 (가중 0.3) | 1.000 | 0.818 | 0.750 |
| 하이브리드 (1:1) | 0.929 | 0.790 | 0.717 |

가중 0.1 은 **동점**입니다. BM25 가 아무 영향도 못 줬다는 뜻이지 좋아진 게 아닙니다.

정작 목표였던 조건형 4문항은 순위가 하나도 안 움직였고, 대신 `사업`·`기간` 같은 흔한 낱말이 많은 상용구 청크가 올라와 멀쩡하던 질문 2개를 밀어냈습니다.

**다만 이 Gold 는 14문항뿐이고 dense 가 이미 Hit@5 1.000 으로 천장을 쳐서, 개선을 보여줄 여지 자체가 없었습니다.** 측정 설계의 한계지 BM25 가 쓸모없다는 결론은 아닙니다. 코드는 남겨두고 기본만 껐습니다. 더 큰 벤치마크가 생기면 다시 재볼 값어치가 있습니다.

### 다른 데이터셋

Gold 문항이 Custom 문서를 가리켜서 **LIVE·Standard 색인에서는 같은 지표를 낼 수 없습니다.** 지금 확인된 것은 여기까지입니다.

| 색인 | 무결성 | 그 외 |
|---|---|---|
| LIVE v0.3 DEV | 7,990 / 7,990 | 데이터팀 스모크 5/5, MRR 0.900, Scope violation 0, 역추적 5/5 |
| Standard V0 DEV | 16,880 저장 확인 | 전수 검증 미실시 |

DEV/VAL 어느 데이터셋에도 **VAL 을 가리키는 평가 질문이 아직 없습니다.**

모델 선정 과정, 상세 측정 결과, 트러블슈팅 기록은 별도 문서로 정리돼 있습니다.
