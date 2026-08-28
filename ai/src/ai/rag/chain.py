"""ai.rag.chain — 프롬프트 조합 + LLM 호출.

ai/README.md 에 정의된 계약을 그대로 따른다.

    from ai.rag.retriever import retrieve
    from ai.rag.chain import generate_answer

    hits = retrieve(query, top_k=5)
    result = generate_answer(question, hits, document_id=doc_id)
    # result == {"answer": str, "sources": list[dict], "abstained": bool}

backend 프로세스 안에서 직접 import 해서 쓰는 걸 전제로 한다(README 참고).
모델(Qwen3-14B-AWQ)은 첫 호출 때 한 번만 GPU 에 올라간다(모듈 전역 캐시).

`hits` 는 ai.rag.retriever.retrieve() 가 이미 검색을 끝낸 결과다. 이 모듈은
검색을 하지 않는다. 각 hit 은 최소 {"chunk_id": str, "score": float, "text": str}
를 가져야 한다 — text 채우기는 retriever 쪽 책임이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ---------------------------------------------------------------------------
# 모델 설정 — 코드잇 중급 프로젝트 베이스라인에서 확정한 값
# (Qwen3-14B-AWQ vs EXAONE-4.0-32B-GPTQ 비교 후 Qwen3 채택. 근거는
#  ai/notebooks/rfp_rag_generation_baseline_qwen3.ipynb 참고)
# ---------------------------------------------------------------------------

MODEL_NAME = "Qwen/Qwen3-14B-AWQ"
DEVICE = "cuda:0"
CONTEXT_WINDOW = 32_768

DEFAULT_TOP_K = 5
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_TOKENS = 1024
DEFAULT_ENABLE_THINKING = True

_PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")
USER_TEMPLATE = (_PROMPTS_DIR / "user_template.txt").read_text(encoding="utf-8")

NO_HIT = "(검색된 문서 조각 없음)"

THINK_RE = re.compile(r"<think>.*?</think>", re.S)

# ---------------------------------------------------------------------------
# 모델 전역 캐시 — 첫 호출 때만 GPU 에 올린다
# ---------------------------------------------------------------------------

_tok: Any | None = None
_model: Any | None = None


def load_model() -> None:
    """Qwen3-14B-AWQ를 GPU 에 올린다. 이미 올라와 있으면 아무것도 안 한다.

    generate_answer()가 첫 호출 때 자동으로 부르므로 직접 부를 필요는 없다.
    backend 기동 시 첫 요청 지연을 없애고 싶을 때만 미리 호출한다.
    """
    global _tok, _model
    if _model is not None:
        return
    torch.cuda.empty_cache()
    _tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, torch_dtype="auto", device_map=DEVICE
    )
    _model.eval()


def is_model_loaded() -> bool:
    return _model is not None


# ---------------------------------------------------------------------------
# hits 정규화 / 컨텍스트 구성
# ---------------------------------------------------------------------------


def _normalize_hits(raw_hits: list[dict], top_k: int) -> list[dict]:
    out = []
    for i, h in enumerate(raw_hits[:top_k], 1):
        out.append({
            "rank": h.get("rank", i),
            "chunk_id": h.get("chunk_id"),
            "document_id": h.get("document_id"),
            "score": float(h.get("score", 0.0)),
            "text": h.get("text") or "",
            "section_path": h.get("section_path") or [],
            "requirement_ids": h.get("requirement_ids") or [],
            "block_ids": h.get("block_ids") or [],
        })
    return out


def _build_context_block(hits: list[dict]) -> str:
    if not hits:
        return NO_HIT
    parts = []
    for h in hits:
        sec = " > ".join(h.get("section_path") or []) or "-"
        req = ", ".join(h.get("requirement_ids") or []) or "-"
        parts.append(
            f"[chunk_id: {h['chunk_id']}] (section: {sec} / requirement: {req})\n"
            f"{h['text']}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 출력 파싱
# (Qwen3는 <think>...</think> 를 정상적으로 열고 닫지만, 방어적으로
#  "닫는 태그만 나오는" 케이스도 함께 처리한다 — 코드잇 중급 프로젝트
#  베이스라인에서 다른 모델(EXAONE)에서 실제로 관측된 실패 패턴이다)
# ---------------------------------------------------------------------------


def _strip_think(text: str) -> str:
    t = text or ""
    t = THINK_RE.sub("", t)
    if "</think>" in t and "<think>" not in t.split("</think>", 1)[0]:
        t = t.split("</think>", 1)[1]
    if "<think>" in t:
        t = t.split("<think>")[0]
    return t.replace("</think>", "").replace("<think>", "").strip()


def _extract_json_obj(s: str) -> dict | None:
    starts = [i for i, ch in enumerate(s) if ch == "{"]
    for start in reversed(starts):
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _parse_output(text: str) -> dict:
    t = _strip_think(text)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.S)
    obj = None
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        obj = _extract_json_obj(t)
    if obj is None:
        return {"answer": t, "abstained": False, "sources": [], "parse_ok": False}
    obj.setdefault("answer", "")
    obj.setdefault("abstained", False)
    obj.setdefault("sources", [])
    obj["parse_ok"] = True
    return obj


# ---------------------------------------------------------------------------
# 공개 API — ai/README.md 가 정한 계약
# ---------------------------------------------------------------------------


def generate_answer(
    question: str,
    hits: list[dict],
    *,
    document_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    enable_thinking: bool = DEFAULT_ENABLE_THINKING,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float = DEFAULT_TOP_P,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """질문 1건 + retriever가 이미 검색한 hits 1건을 받아 답변 1건을 만든다.

    Parameters
    ----------
    question : str
        사용자 질문.
    hits : list[dict]
        ai.rag.retriever.retrieve() 의 결과. 각 dict 는 최소
        {"chunk_id": str, "score": float, "text": str} 를 가져야 한다.
        `top_k` 개까지만 쓰고 나머지는 버린다.
    document_id : str, optional
        대상 문서 ID. 프롬프트에 표기용으로만 쓰인다.
    top_k, enable_thinking, temperature, top_p, max_tokens : optional
        기본값은 베이스라인 노트북에서 확정한 값이다
        (top_k=5, temperature=0.1, thinking ON).

    Returns
    -------
    dict
        {"answer": str, "sources": list[dict], "abstained": bool} 세 키만 있다.

    Raises
    ------
    Exception
        모델 로드 실패, CUDA 오류 등 생성 자체가 실패한 경우 그대로 올라온다.
        (JSON 파싱 실패는 예외가 아니다 — answer 에 원문을 그대로 담아 반환한다.)
    """
    if _model is None:
        load_model()

    norm_hits = _normalize_hits(hits, top_k)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(
            document_id=document_id or "(미지정)",
            context_block=_build_context_block(norm_hits),
            question=question,
        )},
    ]

    text = _tok.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    enc = _tok(text, return_tensors="pt").to(_model.device)
    n_in = enc["input_ids"].shape[-1]

    gen_kw = {
        "max_new_tokens": max_tokens,
        "do_sample": temperature > 0,
        "pad_token_id": _tok.pad_token_id or _tok.eos_token_id,
    }
    if gen_kw["do_sample"]:
        gen_kw["temperature"] = temperature
        gen_kw["top_p"] = top_p

    with torch.no_grad():
        out = _model.generate(**enc, **gen_kw)
    raw = _tok.decode(out[0][n_in:], skip_special_tokens=True)

    parsed = _parse_output(raw)
    return {
        "answer": parsed["answer"],
        "sources": parsed["sources"],
        "abstained": bool(parsed["abstained"]),
    }
