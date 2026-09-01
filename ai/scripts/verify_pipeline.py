# -*- coding: utf-8 -*-
"""ai/scripts/verify_pipeline.py - 검색 결과 -> 생성기 배선을 GPU 없이 검증한다.

실제 모델을 안 올리고, chain 의 토크나이저/모델 자리에 기록용 대역을 끼워
generate_answer() 를 끝까지 돌린다. 확인하는 것:

  1. hits 가 chain 의 입력 계약을 만족하는가 (chunk_id / score / text)
  2. 5개 청크 본문이 프롬프트에 전부 들어가는가
  3. section_path / requirement_ids 가 프롬프트에 채워지는가 (비면 "-" 로 나온다)
  4. 프롬프트 길이가 컨텍스트 윈도우(32,768) 안에 드는가
  5. history 를 넣으면 system 과 현재 질문 사이에 끼는가
  6. 모델 출력 JSON 이 {answer, sources, abstained} 로 파싱되는가

    python ai/scripts/verify_pipeline.py --hits ../retrieval_hits_chroma.jsonl
    python ai/scripts/verify_pipeline.py --hits ... --gold "<Gold jsonl 경로>"

GPU 도, 모델 다운로드도 필요 없다. 실제 생성까지 보려면 노트북을 돌려야 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # ai/scripts/
AI_ROOT = HERE.parent                           # ai/
sys.path.insert(0, str(AI_ROOT / "src"))

CONTEXT_WINDOW = 32_768


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class SpyTok:
    """apply_chat_template 에 들어온 messages 를 그대로 붙잡아 둔다."""

    pad_token_id = 0
    eos_token_id = 0

    def __init__(self):
        self.messages = None
        self.text = ""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True,
                            enable_thinking=True):
        self.messages = messages
        self.text = "\n".join(f"<|{m['role']}|>\n{m['content']}" for m in messages)
        return self.text

    def __call__(self, text, return_tensors=None):
        # 실제 토크나이즈는 하지 않는다. 길이만 대략 잡아 프롬프트 크기를 본다.
        return _Enc({"input_ids": _Ids(max(1, len(text) // 2))})

    def decode(self, ids, skip_special_tokens=True):
        return self.reply


class _Ids:
    """torch 텐서 대신 shape 와 슬라이싱만 흉내낸다."""

    def __init__(self, n):
        self.n = n
        self.shape = (1, n)

    def __getitem__(self, i):
        return list(range(self.n))


class _Enc(dict):
    def to(self, device):
        return self


class SpyModel:
    device = "cpu"

    def generate(self, **kw):
        n_in = kw["input_ids"].shape[-1]
        return [list(range(n_in + 8))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hits", required=True, help="retrieval_hits*.jsonl")
    ap.add_argument("--gold", default=None, help="Gold 질문 jsonl (있으면 실제 질문을 쓴다)")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--fig", default=None, help="그림 저장 경로 (기본: ai/scripts/fig_pipeline.png)")
    a = ap.parse_args()

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    print("=" * 74)
    print("verify_pipeline.py - 검색 결과 -> 생성기 배선 검증 (GPU 불필요)")
    print("=" * 74)

    from ai.rag import chain

    rows = read_jsonl(a.hits)
    print(f"\n[입력] {a.hits}")
    print(f"  문항 {len(rows)}건")
    keys = sorted(rows[0]["hits"][0].keys()) if rows and rows[0]["hits"] else []
    print(f"  hit 키 {keys}")
    need = {"chunk_id", "score", "text"}
    missing = need - set(keys)
    if missing:
        print(f"  !! chain 입력 계약에 필요한 키가 없다: {sorted(missing)}")

    questions = {}
    if a.gold:
        for q in read_jsonl(a.gold):
            questions[q["question_id"]] = q["question"]
        print(f"  Gold 질문 {len(questions)}건 로드")

    tok, model = SpyTok(), SpyModel()
    chain._tok, chain._model = tok, model
    tok.reply = json.dumps(
        {"answer": "테스트 답변", "sources": [{"chunk_id": "X"}], "abstained": False},
        ensure_ascii=False,
    )

    print(f"\n[검증] 문항별 프롬프트 구성")
    print(f"  {'qid':<7}{'hits':>5}{'본문포함':>9}{'섹션':>6}{'요구ID':>7}{'프롬프트자':>11}{'파싱':>6}")

    stats = []
    fails = []
    for r in rows:
        qid = r["question_id"]
        hits = r["hits"][: a.top_k]
        question = questions.get(qid, f"({qid} 질문 텍스트 없음)")

        out = chain.generate_answer(question, hits, document_id=hits[0]["document_id"] if hits else None,
                                    top_k=a.top_k)

        user_msg = tok.messages[-1]["content"]
        n_text_in = sum(1 for h in hits if h.get("text") and h["text"][:40] in user_msg)
        n_id_in = sum(1 for h in hits if h["chunk_id"] in user_msg)
        n_sec = sum(1 for h in hits if h.get("section_path"))
        n_req = sum(1 for h in hits if h.get("requirement_ids"))
        n_chars = len(tok.text)
        parse_ok = set(out.keys()) == {"answer", "sources", "abstained"}

        ok = (n_id_in == len(hits)) and (n_text_in == len(hits)) and parse_ok
        if not ok:
            fails.append(qid)
        stats.append({"qid": qid, "n_hits": len(hits), "text_in": n_text_in,
                      "id_in": n_id_in, "sec": n_sec, "req": n_req,
                      "chars": n_chars, "parse": parse_ok})
        print(f"  {qid:<7}{len(hits):>5}{n_text_in:>9}{n_sec:>6}{n_req:>7}{n_chars:>11,}{'O' if parse_ok else 'X':>6}")

    print(f"\n[검증] history 주입")
    hist = [{"role": "user", "content": "앞선 질문"},
            {"role": "assistant", "content": "앞선 답변"}]
    chain.generate_answer("그럼 그 기간은?", rows[0]["hits"][: a.top_k],
                          document_id=rows[0]["hits"][0]["document_id"],
                          top_k=a.top_k, history=hist)
    roles = [m["role"] for m in tok.messages]
    print(f"  history 없음 -> ['system', 'user'] / 있음 -> {roles}")
    hist_ok = roles == ["system", "user", "assistant", "user"]
    print(f"  system 과 현재 질문 사이에 끼는가 : {'PASS' if hist_ok else 'FAIL'}")

    n_sec_total = sum(s["sec"] for s in stats)
    n_req_total = sum(s["req"] for s in stats)
    n_hits_total = sum(s["n_hits"] for s in stats)
    max_chars = max(s["chars"] for s in stats)

    print("\n" + "=" * 74)
    print("판정")
    print("=" * 74)
    checks = [
        ("hits 가 chain 입력 계약 충족", not missing, f"필요 키 {sorted(need)}"),
        ("chunk_id 가 프롬프트에 전부 들어감",
         all(s["id_in"] == s["n_hits"] for s in stats),
         f"{sum(s['id_in'] for s in stats)}/{n_hits_total}"),
        ("청크 본문이 프롬프트에 전부 들어감",
         all(s["text_in"] == s["n_hits"] for s in stats),
         f"{sum(s['text_in'] for s in stats)}/{n_hits_total}"),
        ("출력 파싱 {answer, sources, abstained}",
         all(s["parse"] for s in stats), f"{sum(s['parse'] for s in stats)}/{len(stats)}"),
        ("history 주입 위치", hist_ok, str(roles)),
        (f"프롬프트 길이 여유 (컨텍스트 {CONTEXT_WINDOW:,} 토큰)",
         max_chars < CONTEXT_WINDOW * 2,
         f"최대 {max_chars:,}자"),
    ]
    for label, passed, note in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}   -- {note}")

    print(f"\n  section_path 채워진 hit : {n_sec_total}/{n_hits_total}")
    print(f"  requirement_ids 채워진 hit : {n_req_total}/{n_hits_total}")
    if n_sec_total == 0:
        print("   -> 프롬프트의 (section: - / requirement: -) 는 이 때문이다.")
        print("      retriever.retrieve() 로 뽑은 hits 에는 채워져 있다.")

    # ---- 그림 ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        ok_font = False
        for f_ in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"):
            if any(f_.lower() in ff.name.lower() for ff in font_manager.fontManager.ttflist):
                plt.rcParams["font.family"] = f_; ok_font = True; break
        plt.rcParams["axes.unicode_minus"] = False
        T = (lambda k, e: k) if ok_font else (lambda k, e: e)

        import numpy as np
        qids = [s["qid"] for s in stats]
        y = np.arange(len(qids))
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))

        a0 = ax[0]
        a0.barh(y, [s["chars"] for s in stats], color="#1565c0")
        a0.set_yticks(y); a0.set_yticklabels(qids, fontsize=8); a0.invert_yaxis()
        a0.set_xlabel(T("프롬프트 글자 수", "prompt chars")); a0.grid(axis="x", alpha=.3)
        a0.set_title(T(f"문항별 프롬프트 길이 (최대 {max_chars:,}자)",
                       f"prompt length per question (max {max_chars:,})"), fontsize=10)

        a1 = ax[1]
        w = 0.4
        a1.barh(y - w / 2, [s["id_in"] for s in stats], w, color="#2e7d32", label="chunk_id")
        a1.barh(y + w / 2, [s["text_in"] for s in stats], w, color="#ef6c00", label="text")
        a1.set_yticks(y); a1.set_yticklabels(qids, fontsize=8); a1.invert_yaxis()
        a1.set_xlim(0, a.top_k + 0.5); a1.legend(fontsize=8); a1.grid(axis="x", alpha=.3)
        a1.set_title(T(f"프롬프트에 들어간 청크 수 (기대 {a.top_k})",
                       f"chunks embedded in prompt (expect {a.top_k})"), fontsize=10)

        fig.tight_layout()
        figp = Path(a.fig) if a.fig else HERE / "fig_pipeline.png"
        fig.savefig(figp, dpi=130)
        print(f"\n그림 : {figp}")
    except Exception as e:
        print(f"\n그림 생략 ({type(e).__name__}: {e})")

    allok = all(p for _, p, _ in checks)
    print()
    if allok:
        print("  배선은 정상이다. 실제 생성(모델 호출)은 GPU 에서 노트북으로 확인해야 한다.")
    else:
        print(f"  실패 문항: {fails or '(판정표 참고)'}")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
