# M2 Dataset → Retrieval / Generation Handoff & Usage Manual v0.1

## 0. 용어 정리

| 용어                                                            | 의미                                                                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **M0 (Milestone 0: Split / Holdout Control)**                 | DEV와 Regression 데이터를 분리하고 평가 데이터 누수를 방지하기 위한 초기 데이터 분할·검증 단계입니다.                                                    |
| **M1 (Milestone 1: Raw Deep Dive / Gold / Failure Analysis)** | 원천 문서 구조를 분석하고 Gold 질의·정답 및 초기 실패 사례를 정의하는 단계입니다.                                                                   |
| **M2 (Milestone 2: Parser / Canonical / Data Contract)**      | 파서, Canonical Document, Structural Block, Chunk 구조 및 Data Contract를 검증하고 고정하는 단계입니다.                                |
| **M3 (Milestone 3: Retrieval)**                               | 고정된 C0와 Gold를 사용해 Dense, Lexical, Hybrid Retrieval 성능을 측정·개선하는 단계입니다.                                               |
| **P0 (Parser v0)**                                            | 원천 문서에서 텍스트, 표, 메타데이터를 추출하고 Canonical Record로 변환하는 초기 파서 버전입니다.                                                     |
| **Canonical Document**                                        | HWP/PDF 원문을 직접 Parsing하고 Noise를 제거한 문서 단위 기준 데이터입니다. 원문 추적 정보, Metadata, Parser Version을 포함합니다.                     |
| **C0 (Canonical Corpus v0)**                                  | Parsing, 정규화, 청킹을 완료한 기준 코퍼스입니다. 이후 Retrieval 실험에서 입력 문서 집합을 고정하기 위한 기준선입니다.                                        |
| **Structural Block**                                          | 문서를 `HEADING / PARAGRAPH / TABLE / REQUIREMENT / LIST` 등 의미·구조 단위로 분리한 데이터입니다.                                      |
| **C0 Chunk**                                                  | Retrieval 최초 성능 기준을 만들기 위한 **모델 독립 Fixed Chunk Baseline**입니다. `1,200 normalized chars + 200 chars overlap`으로 구성됩니다. |
| **Gold**                                                      | 질의별 정답 문서, 정답 Evidence, Answerable 여부 및 평가 기준을 포함한 기준 정답 세트입니다.                                                     |
| **Gold Question**                                             | 질문, 정답, 원문 Evidence, 조건 및 Critical Fact를 연결한 평가용 기준 데이터입니다.                                                         |
| **Critical Fact**                                             | 금액·기간·수치·자격조건처럼 틀릴 경우 실무상 치명적인 정보입니다.                                                                               |
| **Evidence Logic**                                            | Gold Evidence의 결합 조건입니다. `ALL`은 모든 근거가 필요함을, `ANY`는 대체 근거 중 하나면 충분함을, `NONE`은 문서에 답이 없음을 의미합니다.                     |
| **Data Contract**                                             | Record와 Gold가 반드시 만족해야 하는 필드, 타입, 식별자, Evidence 연결 및 평가 호환성 규칙의 집합입니다.                                              |
| **Provenance**                                                | `document → block → chunk → evidence`를 거슬러 원문 위치까지 추적할 수 있는 연결정보입니다.                                                |
| **Operator**                                                  | `EQ / GTE / LTE / REQUIRED / PROHIBITED` 등 수치·조건의 의미와 방향을 보존하는 연산자입니다.                                              |
| **Selected-document scope**                                   | P0에서 사용자가 선택한 RFP 한 문서 안에서만 Retrieval하는 제약입니다.                                                                      |
| **DEV**                                                       | 개발 중인 모델·검색기·프롬프트를 조정하기 위해 사용하는 평가 데이터 분할입니다.                                                                       |
| **Regression**                                                | 기존 성능 저하와 Data Contract 위반을 반복 검증하기 위해 고정해 두는 회귀 테스트용 데이터 분할입니다.                                                    |
| **Final Holdout**                                             | 개발 과정에 공개하거나 사용하지 않고 최종 성능 검증에만 사용하는 데이터 분할입니다.                                                                     |
| **Freeze**                                                    | 해당 버전의 데이터·스키마·평가 규칙을 이후 실험에서 변경하지 않고 기준선으로 고정하는 것을 의미합니다.                                                          |
| **Hit\@5**                                                    | Top-5 검색 결과 안에 정답 Evidence가 하나라도 포함되는 비율입니다.                                                                        |
| **Evidence Hit\@5**                                           | Top-5 검색 결과가 실제 Gold Evidence를 포함하는지 측정하는 지표입니다.                                                                    |
| **MRR**                                                       | 첫 번째 정답 Evidence가 검색 결과에서 얼마나 높은 순위에 나타나는지 측정하는 지표입니다.                                                              |
| **nDCG\@5**                                                   | 복수의 Relevant Evidence와 검색 순위 품질을 함께 평가하는 지표입니다.                                                                     |
| **Recall\@5**                                                 | 필요한 Gold Evidence 중 Top-5 검색 결과가 포함한 비율입니다.                                                                         |
| **Scope Violation**                                           | `selected_document_id`와 다른 문서의 검색 결과가 포함되는 오류입니다. P0에서는 반드시 0건이어야 합니다.                                              |
| **Retrieval Error**                                           | Gold Evidence가 검색 대상 Corpus에 존재하지만 검색 결과에 포함되지 않은 오류입니다.                                                            |
| **Generation Error**                                          | Gold Evidence가 Retrieval Context에 포함되어 있지만 모델이 잘못된 답변을 생성한 오류입니다.                                                   |
| **Citation Error**                                            | 답변 내용은 맞지만 연결한 Source가 실제 주장을 지지하지 않는 오류입니다.                                                                        |
| **Abstention**                                                | 문서에 답이 없거나 근거가 부족할 때 답변을 생성하지 않고 거절하는 동작입니다.                                                                        |

M2 Data Contract는 실제 DEV/Regression Record와 Gold를 이용한 Compatibility Test에서 **14/14 PASS**를 기록한 후 Baseline용으로 Freeze되었습니다.

## 1. M2 데이터가 의도적으로 보존한 것

이번 Dataset은 단순히 `원문 → 글자 자르기` 방식으로 생성된 데이터가 아닙니다.

```text
Raw HWP / PDF
→ Control-safe Parsing
→ Canonical Text
→ Structural Blocks
→ C0 Chunks
→ Gold Evidence 연결
```

위 과정을 통해 다음 정보를 보존했습니다.

### 핵심

- 원문의 **금액·날짜·기간·자격·조건·Requirement ID**
- `이상 / 이하 / 필수 / 불허`와 같은 **조건의 방향**
- Heading / Table / Requirement / List 등의 **문서 구조**
- 문서 내 **순서와 위치**
- `document_id → block_id → chunk_id` 관계
- Canonical Text의 `char_start / char_end`
- PDF의 경우 가능한 `page` 정보
- Requirement의 **raw ID + normalized ID**
- Metadata의 값뿐 아니라 **출처와 품질상태**
- Gold Evidence와 실제 Chunk 사이의 연결

Structural Block에는 `section_path`, `semantic_role`, `requirement_id_raw`, `requirement_id_normalized`, `char_start/end` 등이 포함되어 있습니다.

현재 Parser Baseline은 DEV/Regression 전체 Parse Success와 현재 Gold의 24개 Evidence 및 36개 Critical Fact 보존을 통과했습니다. 다만 이는 현재 Gold 범위에 대한 결과이며, Table Row-Column 완전 복원까지 보장한다는 의미는 아닙니다.

# 2. Retrieval 담당자 전달 파일

## A. 반드시 전달 — 실제 개발 입력

| 파일                                               | 역할                              | 사용 방법                                                                                        |
| ------------------------------------------------ | ------------------------------- | -------------------------------------------------------------------------------------------- |
| **`RFP100_chunks_C0_DEV_v0.1.jsonl`**            | **Dense Retrieval 직접 Index 대상** | `text`를 Embedding하고 `chunk_id`, `document_id`, Block/Section/Requirement Metadata를 함께 저장합니다. |
| **`RFP100_documents_DEV_v0.1.jsonl`**            | 문서 Metadata 및 Provenance        | Title, Agency, Budget Status, Parser 상태 등 Document Metadata 조회에 사용합니다.                       |
| **`RFP100_blocks_DEV_v0.1.jsonl`**               | 구조·문맥·근거 추적                     | 검색 결과 분석, Section/Requirement-aware 실험, Citation 및 Error Analysis에 활용합니다.                    |
| **`RFP100_Gold_Questions_v0.2_Canonical.jsonl`** | Retrieval 평가 기준                 | Query와 Gold Evidence로 Hit\@5, MRR, nDCG\@5, Evidence Hit\@5 등을 계산합니다.                        |
| **`DATA_CONTRACT_v0.1_FROZEN.md`**               | 공식 인터페이스                        | 필드명과 Schema를 임의로 변경하지 않고 그대로 사용합니다.                                                          |
| **`DATA_DICTIONARY_v0.1.md`**                    | 필드 설명                           | 각 Metadata, Block, Chunk 필드의 의미를 확인합니다.                                                      |
| **`RETRIEVAL_HANDOFF_v0.1.md`**                  | Retrieval 전용 요약                 | P0 Scope, 금지사항 및 기본 지표를 확인합니다.                                                               |

Regression 단계에서는 동일한 구조의 다음 파일을 사용합니다.

```text
RFP100_documents_REGRESSION_v0.1.jsonl
RFP100_blocks_REGRESSION_v0.1.jsonl
RFP100_chunks_C0_REGRESSION_v0.1.jsonl
```

Final Holdout은 개발 과정에 전달하지 않습니다.

---

# 3. Retrieval 담당자 사용 매뉴얼

## 3.1 최초 Baseline은 C0를 그대로 사용해 주세요

C0:

```text
fixed-char-1200-o200-v0.1

window  = 1,200 normalized chars
overlap = 200 chars
```

C0는 Embedding Model과 Tokenizer가 아직 고정되지 않은 상태에서 모델 종속성을 피하기 위해 만든 **독립 기준선**입니다. DEV에는 4,931개 Chunk가 있으며, 현재 Answerable Gold 14개 QA에서 Logic-aware Full Evidence Coverage는 100%였습니다.

따라서 최초 Dense Baseline에서는 다음 원칙을 지켜 주세요.

> **C0를 다시 자르거나 합치지 않습니다.**

먼저 현재 상태의 Retrieval 성능을 측정해야 이후 C1/C2/C3 개선량을 정확하게 확인할 수 있습니다.

---

## 3.2 `text`만 저장하지 말고 Metadata를 함께 Index해 주세요

최소 권장 Metadata는 다음과 같습니다.

```text
chunk_id
document_id
chunk_index
section_path
block_ids
requirement_ids
char_start
char_end
page_start
page_end
chunking_version
source_text_version
```

C0 자체는 단순 Fixed Chunk이지만 주변의 Structural Block 정보를 상속하고 있으므로, **향후 Filtering·Reranking·Error Analysis에 활용할 수 있습니다.**

---

## 3.3 가장 중요한 P0 제약

입력 예시는 다음과 같습니다.

```json
{
  "selected_document_id": "DOC_001",
  "query": "사업 예산은?"
}
```

Retrieval 결과는 반드시 다음 조건을 만족해야 합니다.

```text
all(hit.document_id == selected_document_id)
```

이는 Similarity Score보다 우선하는 **Hard Filter**입니다.

다른 문서가 섞이는 경우에는 단순한 성능 저하가 아니라 다음과 같이 처리합니다.

```text
RETRIEVAL_SCOPE_ERROR
```

이는 Critical Failure로 간주합니다.

---

## 3.4 `section_path / semantic_role / requirement_ids`를 버리지 말아 주세요

M2에서 구조정보를 만든 이유는 Dense Score만으로 해결하기 어려운 RFP 특성 때문입니다.

예를 들어 다음 두 표현이 같은 문서의 서로 다른 Semantic Section에 존재할 수 있습니다.

```text
공동수급 불허
```

```text
공동수급체의 경우 ...
```

따라서 후속 실험에서는 다음 정보를 Reranking Feature로 활용할 가치가 있습니다.

```text
Dense Score
+
Section / Semantic Role
+
Requirement ID
```

다만 **Dense C0 Baseline을 먼저 측정한 후** 개선 실험으로 수행해 주시기를 권장합니다.

---

## 3.5 Structural Block 활용법

`blocks`는 기본 Embedding Corpus라기보다 **구조정보와 Provenance 자산**입니다.

활용 예시는 다음과 같습니다.

```text
Top Chunk
→ block_ids 조회
→ 해당 Block의
   section_path
   semantic_role
   requirement_id
   char span 확인
```

이를 통해 다음 작업에 활용할 수 있습니다.

- 엉뚱한 Section 검색 탐지
- Requirement의 정확한 위치 확인
- Citation 생성
- C2 Section-aware 실험
- C3 Requirement-aware 실험

Table Block의 현재 의미는 **텍스트·순서·근거 보존**이며, 완전한 Row-Column Reconstruction까지 보장하지는 않습니다.

---

# 4. Retrieval 추천 평가 지표

최종 선택은 Retrieval 담당자가 결정하면 되지만, 다음 지표 세트를 권장합니다.

## Primary

| 지표                  | 이유                                          |
| ------------------- | ------------------------------------------- |
| **Evidence Hit\@5** | 정답 문서가 아니라 실제 **정답 근거**를 가져왔는지 확인합니다.       |
| **Hit\@5**          | Top-5 안에 정답 Evidence가 하나라도 있는지 직관적으로 측정합니다. |
| **MRR**             | 첫 정답 Evidence가 얼마나 위에 있는지 확인합니다.            |
| **nDCG\@5**         | 복수 Relevant Evidence와 Ranking 품질을 함께 평가합니다. |

## Diagnostic

| 지표                                    | 특히 유용한 경우                     |
| ------------------------------------- | ----------------------------- |
| **Recall\@5**                         | Multi-evidence 질문             |
| **Selected-document Scope Violation** | **반드시 0건이어야 합니다.**            |
| **Retrieval Latency**                 | 실제 E2E 연결 시                   |
| **Section/Semantic-role Error Rate**  | 정답 문서이지만 엉뚱한 Section을 검색하는 문제 |
| **Requirement Hit Rate**              | Requirement ID 질문             |

프로젝트에서는 이미 Retrieval의 핵심 지표로 Hit\@5, MRR, nDCG\@5, Evidence Hit\@5, Recall\@5가 정의되어 있습니다.

### 실험 기록 권장

```text
C0 Dense
→ C1 Token-aware
→ C2 Section-aware
→ C3 Requirement-aware / Hybrid / Rerank
```

각 실험은 반드시 다음 형식으로 비교해 주세요.

```text
Metric
+
Δ vs C0 Baseline
+
Error Breakdown
```

---

# 5. Generation 담당자 전달 파일

Generation 담당자는 **Raw Corpus를 직접 다시 Parsing하거나 Retrieval을 재구현하지 않아야 합니다.**

## A. 반드시 전달

| 파일                                                   | 역할                                 | Generation 사용법                                                |
| ---------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------- |
| **`DATA_CONTRACT_v0.1_FROZEN.md`**                   | Retrieval → Generation 입력/출력 공식 형식 | `hits[]`와 `sources[]` Schema를 그대로 사용합니다.                      |
| **`DATA_DICTIONARY_v0.1.md`**                        | 필드 의미                              | Section, Block, Requirement, Metadata의 의미를 확인합니다.             |
| **`RFP100_Gold_Questions_v0.2_Canonical.jsonl`**     | Answer 평가 기준                       | Gold Answer, Condition, Evidence Logic, Answerability를 이용합니다. |
| **`RFP100_Critical_Fact_Gold_v0.2_Canonical.jsonl`** | 숫자·조건 정확도 평가                       | Normalized Value, Unit, Operator를 비교합니다.                      |

## B. 참고·디버깅용 전달 권장

| 파일                                | 목적                                      |
| --------------------------------- | --------------------------------------- |
| `RFP100_chunks_C0_DEV_v0.1.jsonl` | Retrieval Hit 내용과 실제 Canonical Chunk 비교 |
| `RFP100_blocks_DEV_v0.1.jsonl`    | Citation, Section, Requirement 근거 확인    |
| `RFP100_documents_DEV_v0.1.jsonl` | Document Metadata 및 원문 Provenance 확인    |

Generation의 정상 Runtime 입력은 전체 Dataset이 아니라 **Retrieval의 Top-k Hits**입니다.

Data Contract상 Retrieval → Generation 입력에는 `chunk_id`, `document_id`, Score, Text, `section_path`, `requirement_ids` 등이 포함되도록 정의되어 있습니다.

---

# 6. Generation 담당자 사용 매뉴얼

## 6.1 Retrieval Hit을 그대로 Grounding Context로 사용해 주세요

권장 흐름은 다음과 같습니다.

```text
selected_document_id
+ question
+ Retrieval Top-k hits
        ↓
Grounded Prompt
        ↓
Answer
+ Citation
+ Abstention
```

**전체 Document를 다시 LLM에 입력하거나 별도로 Re-chunking하지 않는 것**을 Baseline 원칙으로 권장합니다.

이렇게 해야 Retrieval 실패와 Generation 실패를 분리해서 측정할 수 있습니다.

---

## 6.2 Citation은 문자열이 아니라 ID 기반으로 생성해 주세요

Data Contract의 Generation Output은 다음 정보를 통해 출처를 연결할 수 있도록 구성되어 있습니다.

```text
document_id
chunk_id
block_ids
section_path
```

권장 연결 방식은 다음과 같습니다.

```text
답변 문장
→ source chunk_id
→ block_id
→ canonical source 위치
```

따라서 단순히 다음과 같이 표시하는 것보다:

> “출처: 제안요청서”

실제로 어떤 Evidence가 답변을 지지했는지 검증할 수 있도록 해야 합니다.

---

## 6.3 Critical Fact 구조를 답변 검증에 적극 활용해 주세요

Gold에는 단순 정답 문자열뿐 아니라 다음과 같은 구조가 포함되어 있습니다.

```json
{
  "raw_value": "24개월 이내",
  "normalized_value": 24,
  "unit": "MONTH",
  "operator": "LTE"
}
```

이를 이용하면 다음 오류를 분리해 탐지할 수 있습니다.

```text
24개월     → 값 오류
24일       → 단위 오류
24개월 이상 → Operator 역전
허용       → Prohibited/Allowed 역전
```

특히 RFP에서는 `이상/이하`, `허용/불허`, `필수/선택`이 중요하므로, **LLM Judge 하나만 사용하는 것보다 Deterministic Exact Check를 병행하는 것**을 권장합니다.

---

## 6.4 Gold의 `evidence_logic`을 반드시 사용해 주세요

Gold v0.2는 다음 세 가지를 구분합니다.

```text
ALL
ANY
NONE
```

### ALL

모든 조건이 필요합니다.

예:

```text
개발경력 10년 이상
+
SI/SM 사업 PL 경력
```

둘 중 하나만 답변하면 부분 정답으로 처리해야 합니다.

### ANY

여러 근거 중 하나만으로도 답변을 충분히 지지할 수 있습니다.

### NONE

문서에서 답을 확인할 수 없는 질문입니다.

→ **Abstention이 올바른 동작입니다.**

이 구조를 무시하고 모든 Evidence를 강제로 요구하면 Generation 평가 자체가 왜곡될 수 있습니다.

---

## 6.5 `gold_conditions`를 단순 키워드가 아닌 Coverage로 사용해 주세요

예를 들어 다음과 같은 조건이 있을 수 있습니다.

```text
공동수급 불허
하도급 불허
```

Gold Answer가 있는데 모델이 다음과 같이 답변하면 핵심 조건을 잃은 것입니다.

> “참여 가능합니다.”

따라서 Natural Language Similarity만 확인하기보다 다음 지표를 별도로 측정하는 것을 권장합니다.

```text
Gold Condition Coverage
```

---

# 7. Generation 추천 평가 지표

## Primary

| 지표                                 | 이유                                         |
| ---------------------------------- | ------------------------------------------ |
| **Critical Answer Exact Accuracy** | 금액·날짜·기간·조건의 정확성을 평가합니다.                   |
| **Faithfulness / Groundedness**    | 답변 주장이 Retrieved Evidence로 실제 지지되는지 확인합니다. |
| **Citation Correctness**           | 표시한 Chunk/Block이 실제 Claim의 근거인지 확인합니다.     |
| **Condition Coverage**             | 중요 조건과 예외의 누락을 방지합니다.                      |
| **Abstention Accuracy**            | 답이 없는 질문에 안전하게 거절하는지 평가합니다.                |
| **Over-Abstention**                | 답이 있는데도 거절하는 문제를 측정합니다.                    |

이 세트는 현재 프로젝트의 Generation Primary KPI와 일치합니다.

## Diagnostic

```text
Format Compliance
Generation Latency
Automated Correctness Proxy
Corrected Over-Abstention
```

특히 Corrected Over-Abstention은 다음과 같이 Root Cause를 분리하는 데 유용합니다.

```text
Gold Evidence가 Retrieval Context에 있음
+ Model abstain
→ GENERATION_ERROR

Gold Evidence가 Retrieval Context에 없음
+ Model abstain
→ RETRIEVAL_ERROR
```

---

# 8. Retrieval ↔ Generation이 함께 지켜야 할 Error Attribution

최종 오답을 바로 “LLM 문제”라고 판단해서는 안 됩니다.

```text
원문에서 이미 손실
→ DATA_ERROR

Chunk에서 Evidence 절단
→ CHUNK_ERROR

Gold Chunk 존재하지만 검색 실패
→ RETRIEVAL_ERROR

Gold Evidence가 Context에 있는데 답 오답
→ GENERATION_ERROR

답은 맞지만 잘못된 Source
→ CITATION_ERROR
```

현재 M2에서는 Data/Chunk 단계의 초기 Gold Critical Failure를 최대한 제거했기 때문에, 이후 M3/M4에서는 이 구분이 훨씬 명확해질 것입니다.

---

# 9. 하지 말아야 할 것

## Retrieval

```text
X CSV `텍스트`를 다시 Corpus로 사용하지 않습니다.
X C0 Baseline 측정 전에 임의로 Re-chunk하지 않습니다.
X Data Parser를 자체적으로 재구현하지 않습니다.
X selected_document_id를 Soft Boost로만 사용하지 않습니다.
X document_id만 맞으면 Evidence Hit이라고 평가하지 않습니다.
X DEV / Final Holdout을 혼합하지 않습니다.
```

CSV Legacy Text는 Gold Evidence 20.8%, Critical Fact 22.2% 수준으로 Baseline Parser에서 탈락했습니다.

## Generation

```text
X 전체 Raw 문서를 다시 Parsing하지 않습니다.
X Retrieval 결과와 무관하게 자체 검색하지 않습니다.
X 근거 없는 Knowledge로 답변을 보완하지 않습니다.
X Citation을 문서명만으로 처리하지 않습니다.
X 10년 이상 ↔ 10년 이하와 같은 Operator 차이를 무시하지 않습니다.
X NONE Gold에서 억지로 답변을 생성하지 않습니다.
```

---

# 10. 가장 권장하는 실제 사용 흐름

## Retrieval

```text
chunks_C0
    ↓
Dense Embedding
    ↓
selected_document_id Hard Filter
    ↓
Top-k
    ↓
Gold Evidence 비교
    ↓
Hit@5 / Evidence Hit@5 / MRR / nDCG / Recall
    ↓
C0 Baseline Freeze
    ↓
필요한 개선만 실험
```

## Generation

```text
Question
+
Retrieval Top-k
    ↓
Grounded Prompt
    ↓
Answer + Sources
    ↓
Gold Answer
+ Critical Facts
+ Conditions
+ Evidence Logic
    ↓
Exact / Faithfulness / Citation / Abstention 평가
```

---

# 11. 팀에 전달할 핵심 메시지

> **Data팀이 전달한 파일은 단순한 텍스트 묶음이 아닙니다.**

M2에서 이미 다음 작업을 수행했습니다.

```text
원문 직접 Parsing
→ 중요정보 보존
→ Control Noise 제거
→ Metadata Provenance 관리
→ Heading/Table/Requirement 구조화
→ Raw/Normalized Requirement ID 보존
→ 조건의 Value/Unit/Operator 구조화
→ Document/Block/Chunk Provenance 구축
→ C0 독립 Baseline 생성
→ Gold Evidence Canonical Re-anchor
→ ALL/ANY/NONE 의미 보정
→ Retrieval/Generation Interface 검증
```

따라서 Retrieval과 Generation 단계에서는 **이 구조를 버리고 다시 단순 텍스트로 환원하기보다, C0를 공정한 기준선으로 먼저 측정한 뒤 M2에서 제공한 구조·조건·근거·Provenance를 고도화 Feature와 평가 장치로 활용하는 것**이 가장 중요합니다.

M2 Data Contract의 실제 Compatibility Gate에서는 Document/Block/Chunk ID, FK, Offset Reproduction, Gold Anchor, Citation Object까지 모두 검증되었습니다.

---

## 한 줄씩 요약

**Retrieval 담당자:**

> `chunks_C0`를 그대로 Dense Baseline으로 먼저 측정하고, `blocks/section/requirement/provenance`는 이후 정확한 Evidence 검색과 Reranking 고도화에 활용해 주세요.

**Generation 담당자:**

> Retrieval이 반환한 Evidence 안에서만 답변하고, Gold의 `critical facts + conditions + evidence_logic + canonical source IDs`를 이용해 숫자·조건·Citation·Abstention을 정확하게 평가해 주세요.

**공통:**

> M2의 구조와 Provenance를 제거하지 말고 그대로 이어받아야 Data Engineering 단계에서 확보한 품질이 최종 RAG 성능으로 연결될 수 있습니다.
