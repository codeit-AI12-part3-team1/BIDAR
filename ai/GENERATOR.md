# BIDAR 생성기 (Generator)

`ai.rag.chain` — 검색된 문서 조각을 받아 RFP 질문에 대한 답변 1건을 만드는 모듈입니다.

이 문서는 **생성기만** 다룹니다. 패키지 전체 구조·설치·검색기·색인은 [`README.md`](README.md) 를 보세요.

```
질문 + hits  →  ai.rag.chain.generate_answer()  →  {"answer", "sources", "abstained"}
```

검색은 하지 않습니다. `hits` 는 `ai.rag.retriever.retrieve()` 가 이미 끝낸 결과입니다.

---

## 1. 확정 설정

| 항목 | 값 | 위치 |
|---|---|---|
| 모델 | `Qwen/Qwen3-14B-AWQ` | `chain.py:36` |
| 디바이스 | `cuda:0` (하드코딩) | `chain.py:37` |
| 컨텍스트 윈도우 | 32,768 | `chain.py:38` |
| top_k | 5 | `chain.py:40` |
| temperature | 0.1 | `chain.py:41` |
| top_p | 1.0 | `chain.py:42` |
| max_tokens | 1,024 | `chain.py:43` |
| thinking | ON | `chain.py:44` |
| 히스토리 턴 상한 | 3턴 (user+assistant 한 쌍 = 1턴) | `chain.py:48` |
| 히스토리 글자 상한 | 2,000자 | `chain.py:49` |

전부 베이스라인 측정에서 확정한 값입니다.

모델은 **첫 호출 때 한 번만** GPU 에 올라가 모듈 전역에 캐시됩니다 (`chain.py:63-81`).

---

## 2. 공개 API

```python
from ai.rag.chain import generate_answer, load_model, is_model_loaded

result = generate_answer(
    question,                 # str
    hits,                     # list[dict]
    document_id=doc_id,       # str | None
    top_k=5,
    enable_thinking=True,
    temperature=0.1,
    top_p=1.0,
    max_tokens=1024,
    history=None,
    max_history_turns=3,
    max_history_chars=2000,
)
```

| 함수 | 하는 일 |
|---|---|
| `generate_answer(...)` | 질문 + hits → 답변 dict. 첫 호출 때 `load_model()` 을 자동으로 부른다 |
| `load_model()` | 모델을 미리 GPU 에 올린다. backend 기동 시 첫 요청 지연을 없애고 싶을 때만 쓴다 |
| `is_model_loaded()` | 로드 여부 |

### 반환 계약

```python
{"answer": str, "sources": list[dict], "abstained": bool}
```

세 키만 있습니다. `chain.py:305-309`.

### 입력 `hits` 계약

각 항목은 최소 이 세 개를 가져야 합니다.

```python
{"chunk_id": str, "score": float, "text": str}
```

`text` 를 채우는 것은 retriever 쪽 책임입니다. 생성기는 `top_k` 개까지만 쓰고 나머지는 버립니다 (`chain.py:93-106`).

선택 필드 `rank / document_id / section_path / requirement_ids / block_ids` 는 있으면 쓰고 없으면 기본값으로 채웁니다. `section_path` 와 `requirement_ids` 가 비면 프롬프트에 `(section: - / requirement: -)` 로 들어갑니다 (`chain.py:109-120`).

### 예외

모델 로드 실패, CUDA 오류는 그대로 올라옵니다. **JSON 파싱 실패는 예외가 아닙니다** — 원문을 `answer` 에 담고 `parse_ok=False` 를 표시합니다.

---

## 3. backend 진입점

`backend/app/services/prediction_service.py:1` 이 이 경로를 탑니다.

```python
from ai.models.predictor import predict

answer: str = predict(query, document_id)
```

`predict()` 는 `retrieve()` → `generate_answer()` 순으로 부르고 **답변 본문 문자열만** 돌려줍니다. `backend/app/schemas/schemas.py:30` 의 `TokenResponse.token` 이 `str` 이기 때문입니다.

`sources` / `abstained` 가 필요하면 `generate_answer()` 를 직접 부르면 됩니다.

---

## 4. 프롬프트

`src/ai/rag/prompts/` 의 텍스트 파일 2개를 **모듈 import 시점에** 읽습니다 (`chain.py:52-53`).

| 파일 | 크기 | 내용 |
|---|---|---|
| `system_prompt.txt` | 967 byte | 규칙 7개 + JSON 출력 형식 |
| `user_template.txt` | 91 byte | `{document_id}` / `{context_block}` / `{question}` |

### `system_prompt.txt` 규칙 7개

1. 제공된 문서 조각의 내용만 근거로 답변
2. 근거가 없으면 추측하지 말고 `abstained=true` + `answer` 에 "문서에서 확인할 수 없습니다."
3. 금액·기간·수치·자격조건은 문서에 적힌 그대로 인용
4. "이상 / 이하 / 필수 / 불허 / 허용" 같은 조건의 방향을 바꾸지 않음
5. 질문이 여러 항목을 물으면 모든 항목을 답함 (일부만 답하면 부분 정답)
6. 근거가 된 `chunk_id` 를 `sources` 에 모두 기재
7. 존댓말

출력은 아래 JSON 만. 코드블록 표시나 설명을 덧붙이지 않습니다.

```json
{"answer": "답변 문장", "abstained": false, "sources": [{"document_id": "...", "chunk_id": "..."}]}
```

### 메시지 조립 순서

```
system  ← system_prompt.txt
(history 최근 3턴, 2,000자 이내)
user    ← user_template.txt.format(document_id, context_block, question)
```

`history` 정규화 규칙 (`chain.py:123-160`):

- `role` 이 `user`/`assistant` 가 아니거나 `content` 가 비었으면 버림
- 최근 `max_turns × 2` 개 메시지만 남김
- 그래도 총 글자 수가 `max_chars` 를 넘으면 오래된 것부터 더 버림
- 자르고 나서 맨 앞이 `assistant` 면 짝이 깨진 것이므로 그 메시지를 버림
- `history` 가 `None` 이거나 비면 기존 단발 호출과 완전히 동일한 messages 가 만들어짐

---

## 5. 출력 파싱

Qwen3 는 `<think>...</think>` 를 정상적으로 열고 닫습니다. 다만 방어적으로 **닫는 태그만 나오는 케이스**도 처리합니다 (`chain.py:171-178`). 베이스라인에서 다른 모델(EXAONE)에서 실제로 관측된 실패 패턴입니다.

파싱 순서 (`chain.py:181-212`):

1. `<think>` 블록 제거
2. 코드펜스(` ```json `) 제거
3. `json.loads()` 시도
4. 실패하면 **마지막 `{` 부터** 균형 잡힌 객체를 찾아 다시 시도
5. 둘 다 실패하면 원문을 `answer` 에 담고 `parse_ok=False`

---

## 6. 모델 선정 근거

Qwen3-14B-AWQ vs EXAONE-4.0-32B-GPTQ, 동일 조건(gold-mock 15문항, top_k=5, thinking ON).

| 지표 | Qwen3-14B-AWQ | EXAONE-4.0-32B-GPTQ | 우위 |
|---|---|---|---|
| Critical Fact Accuracy | 94.4% (34/36) | 88.9% (32/36) | Qwen3 |
| Faithfulness | 96.2% | 80.6% | Qwen3 |
| Condition Coverage | 87.5% | 83.3% | Qwen3 |
| Citation Correctness | 100% | 100% | 동률 |
| Abstention Accuracy | 100% | 100% | 동률 |
| Over-Abstention (낮을수록 좋음) | 7.1% | 7.1% | 동률 |

**우위 3 / 동률 3 / EXAONE 우위 0.**

| | Qwen3-14B-AWQ | EXAONE-4.0-32B-GPTQ |
|---|---|---|
| 지연 평균 | 66.30s | 252.97s (약 3.8배) |
| 지연 최대 | 105.98s | 855.84s |
| 형식 준수 | 100% (15/15) | 93.3% (14/15) |
| operator 역전 | 0건 | 2건 |

operator 역전(조건을 반대로 판단)은 RFP 조건 판단에서 치명적인 오류 유형인데 EXAONE 에서만 나왔습니다.

---

## 7. 평가 지표

각 run 의 `summary.json` 에 기록되는 필드입니다.

| 필드 | 뜻 |
|---|---|
| `critical_fact_accuracy` | Critical Fact 정확도 (분모 `n_critical_facts`) |
| `critical_fact_accuracy_ex_qkey` | 질문에만 등장한 값(`in_question_only`)을 제외한 값 |
| `faithfulness` | 문항 단위 faithfulness 의 평균. claim 이 없는 문항은 분모에서 제외 |
| `condition_coverage` | 조건 항목 회수율 (분모 `n_conditions`) |
| `format_compliance` | JSON 파싱 성공률 |
| `citation_correctness` | 인용한 chunk_id 정확도 |
| `abstention_accuracy` | UNANSWERABLE 을 정확히 거절한 비율 |
| `over_abstention_rate` | 답이 있는데 거절한 비율 (낮을수록 좋음) |
| `operator_reversed` | 조건 방향을 뒤집은 fact 건수 |
| `scope_violation` | 대상 문서 밖 청크를 쓴 건수 |
| `latency_mean` / `latency_median` / `latency_max` | 지연 (초) |
| `thinking_chars_mean` | 사고 과정 글자 수 평균 |

**지연은 평균만 제시하면 안 됩니다.** 베이스라인에서 EXAONE OFF 가 평균 91.98s / 중앙값 31.22s / 최대 839.76s 로, 평균이 중앙값의 2.9배였습니다. 평균 / 중앙값 / 최대를 함께 봐야 합니다.

---

## 8. GPU 없이 검증하기

모델도 GPU 도 없이 돌아가는 검증 2가지가 있습니다.

### 유닛 테스트 (11개)

```bash
cd ai
PYTHONPATH=src pytest tests/test_rag/test_chain.py
# Windows: $env:PYTHONPATH="src"; pytest tests/test_rag/test_chain.py
```

모델 부분은 목(mock)으로 채우고 정규화·파싱·프롬프트 조립과 `generate_answer()` 의 반환 계약(`answer`/`sources`/`abstained` 세 키)만 검증합니다.

### 멀티턴 히스토리 조립 검증

```bash
cd ai
PYTHONPATH=src python scripts/verify_history.py
```

`_normalize_history` 잘림 규칙을 케이스별 수치표로 찍고, 히스토리 턴 수 대비 프롬프트 글자 수 증가와 상한 동작을 그래프(PNG)로 저장합니다.

---

## 9. 실행 환경

| 항목 | 값 |
|---|---|
| 측정 환경 | RTX 3090 24 GiB, Windows |
| Qwen3-14B-AWQ 피크 VRAM | 9.39 GiB |
| KURE-v1 (검색기) VRAM | 1.21 GiB |
| 합계 | 10.60 GiB |
| vLLM | Windows 공식 미지원. `transformers` 직접 로드 |
| AWQ 커널 | `AwqGEMMTritonLinear` (triton fallback) |
| MSVC (`cl.exe`) | 없어도 동작 |

AWQ 로더는 `transformers` 버전에 따라 갈립니다.

| transformers | AWQ 로딩에 필요한 패키지 |
|---|---|
| 4.x | `autoawq` (`quantizer_awq.py` 가 `is_auto_awq_available()` 요구) |
| 5.x | `gptqmodel>=5.0.0` (`quantizer_awq.py` 가 `is_gptqmodel_available()` 요구) |

`pyproject.toml` 에 둘 다 들어 있어 어느 쪽 버전이 깔려도 로더가 있습니다.

---

## 10. 알려진 제약

| # | 내용 |
|---|---|
| 1 | `chain.py:37` `DEVICE = "cuda:0"` 가 하드코딩입니다. 환경변수 오버라이드가 없어 GPU 없는 환경에서는 `load_model()` 이 실패합니다 |
| 2 | AWQ 양자화 모델은 GPU 를 요구합니다. `transformers` 4.x 의 AWQ 로더는 CUDA/XPU 가 없으면 `RuntimeError: GPU is required to run AWQ quantized model` 로 막습니다 |
| 3 | **토큰 단위 스트리밍이 없습니다.** `generate_answer()` 는 생성이 끝난 뒤 완성된 답변을 돌려줍니다. 스트리밍이 필요하면 `streamer` 를 붙여야 합니다 |
| 4 | `max_tokens` 가 1,024 이고 thinking 토큰이 이 예산을 함께 씁니다. 사고가 길어지면 뒤에 나올 JSON 이 잘려 파싱이 실패합니다 (베이스라인에서 EXAONE ON 이 이 경로로 형식 준수 60% 를 기록) |
| 5 | `hits` 에 `section_path` / `requirement_ids` 가 없으면 프롬프트에 `-` 로 들어갑니다. 파일 기반 hits 를 쓸 때 발생합니다 |
| 6 | 프롬프트 텍스트 파일을 import 시점에 읽으므로, wheel 로 빌드할 때 `prompts/*.txt` 가 패키지에 포함돼야 합니다 (`pyproject.toml` 의 `[tool.setuptools.package-data]`) |
