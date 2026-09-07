"""ai.rag.chain 멀티턴 히스토리 검증 — 수치 출력 + 시각화.

GPU/모델 없이 프롬프트 조립 로직만 검증한다. transformers/torch 가 없어도 돈다
(tests/conftest.py 와 같은 방식으로 스텁을 끼운다).

실행 (PowerShell, ai/ 폴더에서):
    $env:PYTHONPATH="src"; python scripts/verify_history.py

출력
    1) _normalize_history 잘림 규칙 케이스별 수치표
    2) 히스토리 턴 수 대비 프롬프트 글자 수 증가 + 상한 동작 그래프 (PNG 저장)
"""

import argparse
import sys
import types
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


# --- torch / transformers 가 없으면 스텁 (tests/conftest.py 와 동일 방식) -------
def _install_stub_if_missing(name, build):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = build()


def _fake_torch():
    mod = types.ModuleType("torch")

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return False

    mod.no_grad = lambda: _NoGrad()
    mod.cuda = types.SimpleNamespace(empty_cache=lambda: None,
                                     is_available=lambda: False)
    return mod


def _fake_transformers():
    mod = types.ModuleType("transformers")
    mod.AutoModelForCausalLM = object
    mod.AutoTokenizer = object
    return mod


_install_stub_if_missing("torch", _fake_torch)
_install_stub_if_missing("transformers", _fake_transformers)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai.rag import chain   # noqa: E402


_FONT_OK = False
for _f in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"):
    if any(_f.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _f
        _FONT_OK = True
        break
plt.rcParams["axes.unicode_minus"] = False
T = (lambda k, e: k) if _FONT_OK else (lambda k, e: e)


def make_history(n_turns, chars_per_msg=40):
    """user/assistant 짝 n_turns 개짜리 히스토리를 만든다."""
    h = []
    for i in range(1, n_turns + 1):
        h.append({"role": "user", "content": f"질문{i}" + "가" * chars_per_msg})
        h.append({"role": "assistant", "content": f"답변{i}" + "나" * chars_per_msg})
    return h


HITS = [{"chunk_id": "DEMO_C0_001", "score": 1.0,
         "text": "본 사업의 사업기간은 계약체결일로부터 150일로 한다."}]


def build_messages(history):
    """generate_answer 와 똑같은 순서로 messages 를 만든다 (모델 호출은 안 한다)."""
    norm_hits = chain._normalize_hits(HITS, chain.DEFAULT_TOP_K)
    norm_history = chain._normalize_history(history)
    return [
        {"role": "system", "content": chain.SYSTEM_PROMPT},
        *norm_history,
        {"role": "user", "content": chain.USER_TEMPLATE.format(
            document_id="DEMO_DOC",
            context_block=chain._build_context_block(norm_hits),
            question="그럼 그 기간은 며칠입니까?",
        )},
    ]


def part1_table():
    print("=" * 78)
    print("1) _normalize_history 잘림 규칙 — 케이스별 수치")
    print("=" * 78)
    print(f"  기본 상한 : max_turns={chain.DEFAULT_MAX_HISTORY_TURNS}  "
          f"max_chars={chain.DEFAULT_MAX_HISTORY_CHARS}")
    print()
    print(f"{'케이스':<34}{'입력msg':>8}{'남김msg':>8}{'남김자수':>10}{'첫role':>11}")
    print("-" * 78)

    cases = [
        ("None", None, {}),
        ("빈 목록", [], {}),
        ("1턴 (짧음)", make_history(1), {}),
        ("3턴 (짧음, 상한과 같음)", make_history(3), {}),
        ("6턴 (짧음, 턴 상한 초과)", make_history(6), {}),
        ("3턴 (각 800자, 글자상한 초과)", make_history(3, 800), {}),
        ("assistant 로 시작", [{"role": "assistant", "content": "먼저답"},
                               {"role": "user", "content": "질문"},
                               {"role": "assistant", "content": "답변"}], {}),
        ("role 불일치만", [{"role": "tool", "content": "x"}], {}),
        ("max_turns=0", make_history(3), {"max_turns": 0}),
    ]

    rows = []
    for label, hist, kw in cases:
        out = chain._normalize_history(hist, **kw) if kw else chain._normalize_history(hist)
        n_in = len(hist) if hist else 0
        n_out = len(out)
        chars = sum(len(m["content"]) for m in out)
        first = out[0]["role"] if out else "-"
        rows.append((label, n_in, n_out, chars, first))
        print(f"{label:<34}{n_in:>8}{n_out:>8}{chars:>10}{first:>11}")

    print()
    # --- 불변식 검사 (전부 PASS 여야 정상) ---
    checks = []
    for label, hist, kw in cases:
        out = chain._normalize_history(hist, **kw) if kw else chain._normalize_history(hist)
        mt = kw.get("max_turns", chain.DEFAULT_MAX_HISTORY_TURNS)
        checks.append((f"{label} · msg수 <= max_turns*2",
                       len(out) <= mt * 2))
        checks.append((f"{label} · 글자수 <= max_chars",
                       sum(len(m["content"]) for m in out) <= chain.DEFAULT_MAX_HISTORY_CHARS))
        checks.append((f"{label} · assistant 로 시작 안 함",
                       (not out) or out[0]["role"] == "user"))
        checks.append((f"{label} · role 은 user/assistant 뿐",
                       all(m["role"] in ("user", "assistant") for m in out)))
    n_pass = sum(1 for _, ok in checks if ok)
    print(f"  불변식 검사 : {n_pass}/{len(checks)} PASS")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL  {name}")
    return rows, n_pass, len(checks)


def part2_curve(max_turns_probe=8, chars_per_msg=200):
    print()
    print("=" * 78)
    print(f"2) 히스토리 턴 수 대비 프롬프트 글자 수 (메시지당 약 {chars_per_msg}자)")
    print("=" * 78)
    print(f"{'입력턴':>6}{'입력msg':>9}{'남김msg':>9}{'히스토리자수':>14}"
          f"{'messages총자수':>16}{'증가분':>9}")
    print("-" * 78)

    xs, hist_chars, total_chars, kept = [], [], [], []
    base = None
    for n in range(0, max_turns_probe + 1):
        h = make_history(n, chars_per_msg) if n else None
        msgs = build_messages(h)
        norm = chain._normalize_history(h) if h else []
        hc = sum(len(m["content"]) for m in norm)
        tc = sum(len(m["content"]) for m in msgs)
        if base is None:
            base = tc
        xs.append(n)
        hist_chars.append(hc)
        total_chars.append(tc)
        kept.append(len(norm))
        print(f"{n:>6}{(n * 2):>9}{len(norm):>9}{hc:>14}{tc:>16}{tc - base:>9}")

    print()
    print(f"  히스토리 없음(0턴) messages 총 글자 수 : {base}")
    print(f"  포화 후 최대 messages 총 글자 수       : {max(total_chars)}")
    print(f"  히스토리가 더하는 최대 글자 수         : {max(total_chars) - base}")
    print(f"  글자 상한(max_chars)                   : {chain.DEFAULT_MAX_HISTORY_CHARS}")
    return xs, hist_chars, total_chars, kept


def draw(xs, hist_chars, total_chars, kept, rows, out_path):
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(T("chain.generate_answer 멀티턴 히스토리 검증",
                   "chain.generate_answer multi-turn history check"), fontsize=13)

    a = ax[0]
    a.plot(xs, total_chars, "o-", label=T("messages 총 글자 수", "total messages chars"))
    a.plot(xs, hist_chars, "s--", label=T("히스토리 글자 수", "history chars"))
    a.axhline(chain.DEFAULT_MAX_HISTORY_CHARS, ls=":", color="red",
              label=f"max_chars={chain.DEFAULT_MAX_HISTORY_CHARS}")
    a.axvline(chain.DEFAULT_MAX_HISTORY_TURNS, ls=":", color="gray",
              label=f"max_turns={chain.DEFAULT_MAX_HISTORY_TURNS}")
    for x, y in zip(xs, total_chars):
        a.annotate(str(y), (x, y), fontsize=7, xytext=(0, 5),
                   textcoords="offset points", ha="center")
    a.set_xlabel(T("입력 히스토리 턴 수", "input history turns"))
    a.set_ylabel(T("글자 수", "chars"))
    a.set_title(T("턴이 늘어도 상한에서 포화한다", "saturates at the cap"))
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    a = ax[1]
    labels = [r[0] for r in rows]
    n_in = [r[1] for r in rows]
    n_out = [r[2] for r in rows]
    y = range(len(labels))
    a.barh([i + 0.2 for i in y], n_in, 0.38, label=T("입력 메시지 수", "input msgs"))
    a.barh([i - 0.2 for i in y], n_out, 0.38, label=T("남긴 메시지 수", "kept msgs"))
    for i, (vi, vo) in enumerate(zip(n_in, n_out)):
        a.text(vi + 0.1, i + 0.2, str(vi), va="center", fontsize=7)
        a.text(vo + 0.1, i - 0.2, str(vo), va="center", fontsize=7)
    a.set_yticks(list(y))
    a.set_yticklabels(labels if _FONT_OK else [f"case {i+1}" for i in y], fontsize=8)
    a.invert_yaxis()
    a.set_xlabel(T("메시지 수", "messages"))
    a.set_title(T("케이스별 잘림 결과", "truncation by case"))
    a.legend(fontsize=8)
    a.grid(alpha=.3, axis="x")

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    print()
    print(f"저장 : {out_path.resolve()}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).with_name("verify_history.png")))
    a = ap.parse_args()

    rows, n_pass, n_all = part1_table()
    xs, hc, tc, kept = part2_curve()
    draw(xs, hc, tc, kept, rows, Path(a.out))

    print()
    print("=" * 78)
    print(f"불변식 {n_pass}/{n_all} PASS   "
          f"{'전부 통과' if n_pass == n_all else '실패 있음 — 위 FAIL 줄 확인'}")
    print("=" * 78)
    return 0 if n_pass == n_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
