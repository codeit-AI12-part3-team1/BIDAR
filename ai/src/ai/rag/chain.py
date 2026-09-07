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
import os
import re
from pathlib import Path
from typing import Any

# torch / transformers 는 로컬 백엔드에서만 필요하다. 모듈 최상단에서 import 하면
# 시나리오 B(API)만 쓰는 서버에서도 GPU 스택이 설치돼 있어야 하므로 함수 안으로
# 내렸다 (ai.embeddings.embedder 가 sentence_transformers / openai 를 다루는 방식과 같다).

# ---------------------------------------------------------------------------
# 모델 설정 — 코드잇 중급 프로젝트 베이스라인에서 확정한 값
# (Qwen3-14B-AWQ vs EXAONE-4.0-32B-GPTQ 비교 후 Qwen3 채택. 근거는
#  ai/notebooks/rfp_rag_generation_baseline_qwen3.ipynb 참고)
# ---------------------------------------------------------------------------

MODEL_NAME = "Qwen/Qwen3-14B-AWQ"
DEVICE = "cuda:0"
CONTEXT_WINDOW = 32_768

# ---------------------------------------------------------------------------
# 백엔드 선택 — 시나리오 A(로컬) / 시나리오 B(API)
#
# 환경변수로만 고른다. backend 패키지(prediction_service.py / chat.py)는 손대지
# 않는다. 미설정이면 "local" 이라 기존 동작 그대로다.
#
#   AI_GENERATOR_BACKEND     local | api        (기본 local)
#   AI_GENERATOR_API_MODEL   API 모델 이름       (기본 gpt-5-mini)
#   AI_GENERATOR_API_KEY_ENV 키가 담긴 환경변수명 (기본 OPENAI_API_KEY)
# ---------------------------------------------------------------------------

VALID_BACKENDS = ("local", "api")

BACKEND = os.environ.get("AI_GENERATOR_BACKEND", "local").strip().lower()
API_MODEL = os.environ.get("AI_GENERATOR_API_MODEL", "gpt-5-mini")
API_KEY_ENV = os.environ.get("AI_GENERATOR_API_KEY_ENV", "OPENAI_API_KEY")

# gpt-5 계열 API 제약 (인수인계.md §1)
#   - max_tokens 를 받지 않는다 -> max_completion_tokens
#   - temperature 는 1 고정. 다른 값을 주면 400
#   - top_p / seed 도 같은 이유로 보내지 않는다
# thinking 은 reasoning_effort 로 대응한다 (작업기록_20260828_judge.md §4:
# gpt-5-mini = minimal, gpt-5-mini-think = medium 으로 측정했다).
API_REASONING_ON = "medium"
API_REASONING_OFF = "minimal"

# ---------------------------------------------------------------------------
# API 키 파일 로드 — 팀은 KEY.env 로 키를 공유한다(repo 바깥에 둔다).
# 규칙은 ai/notebooks/rfp_rag_generation_baseline_qwen3.ipynb 셀 13 과 동일하다:
#   - 파일 이름 후보를 순서대로 찾고, 앞의 것이 우선
#   - 절대경로를 코드에 박지 않는다. find_dotenv 가 현재 폴더에서 위로 올라간다
#   - 20자 미만은 자리표시자로 보고 버린다
#   - 이미 설정된 환경변수가 있으면 그쪽이 이긴다(파일이 덮어쓰지 않는다)
#   - 키 값은 어디에도 출력하지 않는다
# 서버의 env 경로가 cwd 위쪽이 아닐 수 있으므로 AI_GENERATOR_ENV_FILE 로
# 파일 경로를 직접 지정하는 길을 함께 둔다.
# ---------------------------------------------------------------------------

ENV_FILENAMES = ("KEY.env", ".env")     # 앞이 우선
ENV_MIN_KEY_LEN = 20                    # 이보다 짧으면 버린다
ENV_KEY_ALIASES = ("API_TOKEN_OPENAI", "OPENAI_API_KEY")
ENV_FILE_OVERRIDE = os.environ.get("AI_GENERATOR_ENV_FILE", "").strip()

# cwd 기준 탐색만으로는 부족하다 — find_dotenv 는 현재 폴더에서 "위로만" 올라가므로,
# uvicorn 을 backend/ 에서 띄우면 형제 폴더인 ai/.env 를 못 본다(실측 2026-09-04).
# 서버의 키 파일은 ai/.env 에 있으므로, 이 파일(chain.py)의 위치에서도 위로
# 거슬러 올라가며 찾는다. ai/src/ai/rag/chain.py -> 3단계 위가 ai/ 다.
_PKG_DIR = Path(__file__).resolve().parent
# 4 = ai/src/ai -> ai/src -> ai -> (repo 루트). 서버의 ai/.env 는 3단계 위다.
# 더 올리면 홈 디렉터리나 / 까지 뒤지게 되므로 repo 밖으로는 나가지 않는다.
ENV_PKG_SEARCH_DEPTH = 4

DEFAULT_TOP_K = 5
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_TOKENS = 1024
DEFAULT_ENABLE_THINKING = True

# 멀티턴 — 직전 대화를 몇 턴까지, 몇 글자까지 프롬프트에 넣을지.
# 컨텍스트 윈도우(32,768)를 hits 가 이미 상당 부분 쓰므로 히스토리는 작게 잡는다.
DEFAULT_MAX_HISTORY_TURNS = 3      # user+assistant 한 쌍을 1턴으로 센다
DEFAULT_MAX_HISTORY_CHARS = 2000   # 잘라낸 뒤 남은 히스토리 글자 수 상한

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
_api_client: Any | None = None
_api_key_source: str | None = None


def load_model() -> None:
    """Qwen3-14B-AWQ를 GPU 에 올린다. 이미 올라와 있으면 아무것도 안 한다.

    generate_answer()가 로컬 백엔드 첫 호출 때 자동으로 부르므로 직접 부를 필요는
    없다. backend 기동 시 첫 요청 지연을 없애고 싶을 때만 미리 호출한다.

    torch / transformers 는 여기서 import 한다. 시나리오 B(API)만 쓰는 서버에서는
    이 함수가 호출되지 않으므로 두 패키지가 없어도 모듈이 뜬다.
    """
    global _tok, _model
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.cuda.empty_cache()
    _tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, torch_dtype="auto", device_map=DEVICE
    )
    _model.eval()


def is_model_loaded() -> bool:
    return _model is not None


def _iter_package_env_files() -> list[str]:
    """이 파일(chain.py) 위치에서 위로 올라가며 env 파일을 찾는다.

    cwd 와 무관하게 동작한다. 서버는 uvicorn 을 backend/ 에서 띄우는데 키 파일은
    ai/.env 에 있어서, cwd 기준 탐색만으로는 형제 폴더라 닿지 않는다.

    파일 이름이 바깥 루프다 — ENV_FILENAMES 앞쪽 이름이 더 먼 폴더에 있어도
    뒤쪽 이름보다 우선한다(노트북 셀 13 과 같은 우선순위).
    """
    roots = [_PKG_DIR, *list(_PKG_DIR.parents)[:ENV_PKG_SEARCH_DEPTH]]
    out: list[str] = []
    for name in ENV_FILENAMES:
        for root in roots:
            cand = root / name
            if cand.is_file():
                out.append(str(cand))
    return out


def _iter_env_files() -> list[str]:
    """검사할 env 파일 경로를 우선순위대로 모은다.

    1) AI_GENERATOR_ENV_FILE 로 직접 지정한 경로 (있고 실제 파일일 때만)
    2) find_dotenv 가 현재 폴더에서 위로 올라가며 찾은 KEY.env / .env
    3) chain.py 위치에서 위로 올라가며 찾은 KEY.env / .env

    2)는 python-dotenv 가 없으면 건너뛴다. 3)의 "찾기"는 표준 라이브러리만 쓰지만,
    찾은 파일을 "읽는" 것은 _read_key_from_env_files() 가 dotenv 로 한다.
    """
    paths: list[str] = []
    if ENV_FILE_OVERRIDE and Path(ENV_FILE_OVERRIDE).is_file():
        paths.append(ENV_FILE_OVERRIDE)
    try:
        from dotenv import find_dotenv
    except ImportError:
        pass
    else:
        for name in ENV_FILENAMES:
            found = find_dotenv(name, usecwd=True)
            if found and found not in paths:
                paths.append(found)
    for found in _iter_package_env_files():
        if found not in paths:
            paths.append(found)
    return paths


def _read_key_from_env_files() -> tuple[str, str, str] | None:
    """env 파일에서 API 키를 찾는다.

    Returns
    -------
    (파일경로, 키이름, 키값) 또는 None.
        찾는 키 이름은 API_KEY_ENV 가 먼저고, 그 다음이 ENV_KEY_ALIASES 다.
        ENV_MIN_KEY_LEN 미만인 값은 자리표시자로 보고 건너뛴다.

    키 값은 이 함수 밖으로 로그/예외 어디에도 나가지 않는다.
    """
    paths = _iter_env_files()
    if not paths:
        return None
    try:
        from dotenv import dotenv_values
    except ImportError:
        return None

    names = [API_KEY_ENV, *(a for a in ENV_KEY_ALIASES if a != API_KEY_ENV)]
    for path in paths:
        try:
            vals = dotenv_values(path)
        except OSError:
            continue
        for name in names:
            value = (vals.get(name) or "").strip()
            if len(value) >= ENV_MIN_KEY_LEN:
                return path, name, value
    return None


def load_api_client() -> None:
    """OpenAI 클라이언트를 만든다. 이미 있으면 아무것도 안 한다.

    키는 여기서 처음 읽는다. 모듈 로드 시점에 읽으면 키가 없는 서버(시나리오 A 전용)
    에서 import 가 죽어 uvicorn 이 기동하지 못한다.

    순서
    ----
    1. 환경변수 API_KEY_ENV (기본 OPENAI_API_KEY) — 이미 있으면 이게 이긴다
    2. env 파일 (KEY.env / .env). 찾으면 같은 이름의 환경변수에 넣어 둔다
    """
    global _api_client, _api_key_source
    if _api_client is not None:
        return
    from openai import OpenAI

    key = (os.environ.get(API_KEY_ENV) or "").strip()
    source = f"환경변수 {API_KEY_ENV}"

    if not key:
        found = _read_key_from_env_files()
        if found:
            path, name, key = found
            # 이후 호출과 하위 라이브러리가 같은 키를 보도록 환경변수에도 넣는다.
            os.environ[API_KEY_ENV] = key
            source = f"{Path(path).name}({name})"

    if not key:
        try:
            import dotenv  # noqa: F401
            hint = f"찾은 파일: {_iter_env_files() or '없음'}"
        except ImportError:
            hint = "python-dotenv 가 없어 env 파일 탐색을 못 했다 (pip install python-dotenv)"
        raise RuntimeError(
            f"API 백엔드인데 키를 못 찾았다. {API_KEY_ENV} 환경변수도, "
            f"{list(ENV_FILENAMES)} 파일도 비어 있다. {hint} / "
            f"AI_GENERATOR_ENV_FILE 로 경로를 직접 줄 수 있다. "
            f"아니면 AI_GENERATOR_BACKEND=local 로 바꿔야 한다."
        )

    _api_client = OpenAI(api_key=key)
    _api_key_source = source


def is_api_client_loaded() -> bool:
    return _api_client is not None


def get_api_key_source() -> str | None:
    """키를 어디서 읽었는지. 기동 로그용 — 키 값은 담기지 않는다."""
    return _api_key_source


def get_backend() -> str:
    """현재 선택된 백엔드. 기동 로그·헬스체크에 찍어 확인용으로 쓴다."""
    return BACKEND


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


def _normalize_history(
    history: list[dict] | None,
    max_turns: int = DEFAULT_MAX_HISTORY_TURNS,
    max_chars: int = DEFAULT_MAX_HISTORY_CHARS,
) -> list[dict]:
    """대화 히스토리를 chat message 목록으로 정규화한다.

    - role 이 user/assistant 가 아닌 항목, content 가 비었거나 공백뿐인 항목은 버린다.
    - 최근 `max_turns` 턴(= user+assistant 2개 메시지)만 남긴다.
    - 그래도 총 글자 수가 `max_chars` 를 넘으면 오래된 메시지부터 더 버린다.
    - 자르고 나서 맨 앞이 assistant 면 짝이 깨진 것이므로 그 메시지를 버린다.

    history 가 None 이거나 비면 빈 목록을 돌려준다 — 기존 단발 호출과 동일하게 동작한다.
    """
    if not history:
        return []

    clean = []
    for h in history:
        if not isinstance(h, dict):
            continue
        role = h.get("role")
        content = (h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            clean.append({"role": role, "content": content})

    if not clean or max_turns <= 0:
        return []

    keep = clean[-(max_turns * 2):]

    while keep and sum(len(m["content"]) for m in keep) > max_chars:
        keep.pop(0)

    while keep and keep[0]["role"] == "assistant":
        keep.pop(0)

    return keep


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
# 백엔드별 생성 — messages 를 받아 모델 원문(raw)만 돌려준다.
# 프롬프트 조립·파싱은 두 경로가 공유한다.
# ---------------------------------------------------------------------------


def _generate_local(
    messages: list[dict],
    *,
    enable_thinking: bool,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> str:
    """시나리오 A — Qwen3-14B-AWQ 를 GPU 에서 직접 돌린다."""
    if _model is None:
        load_model()

    import torch

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
    return _tok.decode(out[0][n_in:], skip_special_tokens=True)


def _generate_api(
    messages: list[dict],
    *,
    enable_thinking: bool,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> str:
    """시나리오 B — OpenAI API.

    gpt-5 계열은 `max_tokens` 를 받지 않고 `temperature` 가 1 고정이다. 인자로 받은
    temperature / top_p 는 이 경로에서 보내지 않는다(400 오류). thinking 은
    reasoning_effort 로 옮긴다.

    빈 응답을 조용히 통과시키지 않는다 — 예산이 추론 토큰에 다 소모돼 content 가
    빈 문자열로 오는 사례가 실측으로 확인됐다(작업기록_20260828_judge.md §2-1).
    """
    if _api_client is None:
        load_api_client()

    kwargs: dict = {"model": API_MODEL, "messages": messages}
    if API_MODEL.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = max_tokens
        kwargs["reasoning_effort"] = (
            API_REASONING_ON if enable_thinking else API_REASONING_OFF
        )
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature
        kwargs["top_p"] = top_p

    resp = _api_client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    raw = (choice.message.content or "").strip()
    if not raw:
        usage = getattr(resp, "usage", None)
        raise RuntimeError(
            f"API 응답이 비었다. model={API_MODEL} "
            f"finish_reason={getattr(choice, 'finish_reason', None)} usage={usage}"
        )
    return raw


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
    history: list[dict] | None = None,
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
    backend: str | None = None,
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
    history : list[dict], optional
        직전 대화. `[{"role": "user"|"assistant", "content": str}, ...]` 형태다.
        후속 질문("그럼 그 기간은?")의 지시대상을 모델이 찾을 수 있도록 system 과
        현재 질문 사이에 chat message 로 끼워 넣는다. None 이면 기존 단발 호출과
        완전히 동일한 messages 가 만들어진다.
    max_history_turns, max_history_chars : optional
        히스토리 상한. 최근 turns 턴만 남기고, 그래도 chars 를 넘으면 오래된
        메시지부터 버린다. 기본 3턴 / 2000자.
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
    backend = (backend or BACKEND).strip().lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"알 수 없는 백엔드: {backend!r}. {VALID_BACKENDS} 중 하나여야 한다 "
            f"(AI_GENERATOR_BACKEND 환경변수)."
        )

    norm_hits = _normalize_hits(hits, top_k)
    norm_history = _normalize_history(history, max_history_turns, max_history_chars)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *norm_history,
        {"role": "user", "content": USER_TEMPLATE.format(
            document_id=document_id or "(미지정)",
            context_block=_build_context_block(norm_hits),
            question=question,
        )},
    ]

    gen = _generate_local if backend == "local" else _generate_api
    raw = gen(
        messages,
        enable_thinking=enable_thinking,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    parsed = _parse_output(raw)
    return {
        "answer": parsed["answer"],
        "sources": parsed["sources"],
        "abstained": bool(parsed["abstained"]),
    }
