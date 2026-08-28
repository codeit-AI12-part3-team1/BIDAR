"""ai.rag.chain 유닛 테스트.

실제 Qwen3-14B-AWQ 는 GPU 가 있어야 로드되므로, 모델 부분은 목(mock)으로
채우고 순수 로직(정규화/파싱/프롬프트 조립)과 generate_answer() 의 반환
계약({"answer", "sources", "abstained"} 세 키)만 검증한다.
"""

from ai.rag import chain


def test_normalize_hits_truncates_and_defaults():
    raw = [
        {"chunk_id": "C1", "score": 0.9, "text": "본문1", "section_path": ["A"]},
        {"chunk_id": "C2", "score": 0.5},  # text 없음
        {"chunk_id": "C3", "score": 0.1, "text": "본문3"},
    ]
    norm = chain._normalize_hits(raw, top_k=2)
    assert len(norm) == 2
    assert norm[0]["chunk_id"] == "C1" and norm[0]["text"] == "본문1"
    assert norm[1]["chunk_id"] == "C2" and norm[1]["text"] == ""


def test_build_context_block():
    assert chain._build_context_block([]) == chain.NO_HIT
    hits = chain._normalize_hits(
        [{"chunk_id": "C1", "score": 0.9, "text": "본문1", "section_path": ["A"]}], 5)
    ctx = chain._build_context_block(hits)
    assert "[chunk_id: C1]" in ctx and "본문1" in ctx


def test_strip_think_handles_three_shapes():
    # 1) 정상 쌍 (Qwen3)
    assert chain._strip_think("<think>고민중</think>진짜답") == "진짜답"
    # 2) 여는 태그 없이 닫는 태그만 (다른 모델에서 관측된 실패 패턴에 대한 방어)
    assert chain._strip_think("추론잔여</think>진짜답2") == "진짜답2"
    # 3) 닫는 태그 없이 잘림
    assert chain._strip_think("<think>안닫힌추론") == ""
    assert chain._strip_think("그냥답") == "그냥답"


def test_extract_json_obj_prefers_last_balanced_object():
    s = ('이런 예시 JSON도 있음: {"foo": 1} 그리고 진짜 답은 '
         '{"answer": "150일", "abstained": false, "sources": []}')
    obj = chain._extract_json_obj(s)
    assert obj is not None
    assert obj["answer"] == "150일"


def test_parse_output_variants():
    r1 = chain._parse_output(
        '{"answer": "150일", "abstained": false, "sources": [{"chunk_id":"C1"}]}')
    assert r1 == {"answer": "150일", "abstained": False,
                  "sources": [{"chunk_id": "C1"}], "parse_ok": True}

    r2 = chain._parse_output('```json\n{"answer": "A", "abstained": true, "sources": []}\n```')
    assert r2["answer"] == "A" and r2["abstained"] is True and r2["parse_ok"] is True

    r3 = chain._parse_output('<think>고민</think>{"answer": "B", "abstained": false, "sources": []}')
    assert r3["answer"] == "B" and r3["parse_ok"] is True

    r4 = chain._parse_output("그냥 산문, JSON 아님")
    assert r4["parse_ok"] is False and r4["answer"] == "그냥 산문, JSON 아님"


class _FakeArr:
    shape = [1, 3]


class _FakeEnc(dict):
    def to(self, device):
        return self


class _FakeTok:
    pad_token_id = 0
    eos_token_id = 0

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        joined = " ".join(m["content"] for m in messages)
        assert "이 사업의 사업기간" in joined
        assert "DEMO_C0_001" in joined
        return "PROMPT_TEXT"

    def __call__(self, text, return_tensors):
        enc = _FakeEnc()
        enc["input_ids"] = _FakeArr()
        return enc

    def decode(self, ids, skip_special_tokens):
        return '{"answer": "150일", "abstained": false, "sources": [{"chunk_id": "DEMO_C0_001"}]}'


class _FakeModel:
    device = "cpu"

    def generate(self, **kw):
        class _Out:
            shape = [1, 5]

            def __getitem__(self, i):
                return [10, 11, 12]

        return _Out()


def test_generate_answer_returns_exactly_three_keys(monkeypatch):
    monkeypatch.setattr(chain, "_tok", _FakeTok())
    monkeypatch.setattr(chain, "_model", _FakeModel())

    out = chain.generate_answer(
        question="이 사업의 사업기간은 며칠입니까?",
        hits=[{"chunk_id": "DEMO_C0_001", "score": 1.0, "text": "150일"}],
        document_id="DEMO_DOC",
    )
    assert set(out.keys()) == {"answer", "sources", "abstained"}
    assert out["answer"] == "150일"
    assert out["sources"] == [{"chunk_id": "DEMO_C0_001"}]
    assert out["abstained"] is False
