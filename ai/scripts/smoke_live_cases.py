"""ai/scripts/smoke_live_cases.py - LIVE v0.3 handoff 가 요구하는 Retriever 스모크.

    python ai/scripts/smoke_live_cases.py --cases "<...>/handoff/SMOKE_CASES_DEV_v0.3.json"

데이터팀이 준 5개 케이스(질문 + 정답 청크 id)를 그대로 돌려서
  1. 정답 청크가 top-k 안에 들어오는가
  2. Hard Scope violation 이 0 인가
를 확인한다. HANDOFF_ACCEPTANCE_REPORT 의 `R/G_COMPATIBILITY = PENDING` 을
PASS 로 바꾸려면 이 결과가 필요하다 (RETRIEVER_HANDOFF_v0.3.md).

색인을 먼저 만들고, 그 색인을 가리키도록 환경변수를 맞춘 뒤 실행해야 한다.
    AI_RETRIEVER_PERSIST_DIR / AI_RETRIEVER_COLLECTION
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai.ingestion.loaders import load_jsonl
from ai.rag.retriever import COLLECTION_NAME, PERSIST_DIR, load_retriever, retrieve


def _collection_ids(document_id: str) -> list[str]:
    """이 문서가 색인에 갖고 있는 청크 id. 반환 건수가 적은 게 정상인지 판단하는 데 쓴다."""
    import ai.rag.retriever as retriever_module

    load_retriever()
    return retriever_module._collection.get(
        where={"document_id": document_id}, include=[]
    )["ids"]


def load_provenance_maps(package_dir: str) -> tuple[dict, set]:
    """block_id -> document_id 와 provenance 가 존재하는 document_id 집합.

    RUNTIME_SMOKE_RUNBOOK 의 PASS 조건에
    "chunk -> block -> document -> provenance 역추적 5/5" 가 들어 있다.
    """
    root = Path(package_dir)
    block_owner: dict[str, str] = {}
    for name in ("data/dev/LIVE_blocks_DEV_v0.3.jsonl", "data/val/LIVE_blocks_VAL_v0.3.jsonl"):
        path = root / name
        if path.exists():
            for block in load_jsonl(str(path)):
                block_owner[block["block_id"]] = block["document_id"]

    provenance_docs: set[str] = set()
    path = root / "metadata/LIVE_provenance_v0.3.jsonl"
    if path.exists():
        for row in load_jsonl(str(path)):
            doc_id = row.get("document_id") or row.get("canonical_doc_id")
            if doc_id:
                provenance_docs.add(doc_id)

    return block_owner, provenance_docs


def main() -> None:
    ap = argparse.ArgumentParser(description="LIVE v0.3 Retriever 스모크")
    ap.add_argument("--cases", required=True, help="SMOKE_CASES_DEV_v0.3.json 경로")
    ap.add_argument("--package-dir", default=None,
                    help="handoff 패키지 루트. 주면 chunk->block->document->provenance "
                         "역추적까지 검증한다 (RUNTIME_SMOKE_RUNBOOK PASS 조건)")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    with open(args.cases, encoding="utf-8") as f:
        cases = json.load(f)

    block_owner, provenance_docs = ({}, set())
    if args.package_dir:
        block_owner, provenance_docs = load_provenance_maps(args.package_dir)
        print(f"역추적 자료 : block {len(block_owner)}개 / provenance 문서 {len(provenance_docs)}개")

    print(f"색인 : {PERSIST_DIR} / {COLLECTION_NAME}")
    print(f"케이스 {len(cases)}건 / top_k={args.top_k}\n")

    passed = 0
    scope_violations = 0
    returned_full = 0
    trace_ok = 0
    reciprocal_ranks = []

    for case in cases:
        oracle = set(case["oracle_chunk_ids"])
        hits = retrieve(case["question"], top_k=args.top_k, document_id=case["document_id"])
        found = [h["chunk_id"] for h in hits]

        scope_violations += sum(1 for h in hits if h["document_id"] != case["document_id"])
        # 문서에 청크가 top_k 보다 적으면 그만큼만 나오는 게 정상이다
        # (실측: LVS001 문서는 청크가 3개뿐이라 top-5 를 채울 수 없다).
        # 그래서 "정확히 top_k 개"가 아니라 "가능한 만큼 다 나왔는가"로 본다.
        available = len(_collection_ids(case["document_id"]))
        returned_full += len(hits) == min(args.top_k, available)

        # oracle 이 여러 개인 케이스는 전부 들어와야 통과로 본다 (multi-fact 케이스)
        ok = oracle.issubset(set(found))
        passed += ok
        rank = next((i + 1 for i, cid in enumerate(found) if cid in oracle), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)

        # chunk -> block -> document -> provenance 역추적
        trace = "건너뜀"
        if block_owner:
            problems = []
            for h in hits:
                if not h["block_ids"]:
                    problems.append(f"{h['chunk_id']}: block_ids 없음")
                for block_id in h["block_ids"]:
                    owner = block_owner.get(block_id)
                    if owner is None:
                        problems.append(f"{block_id}: blocks 에 없음")
                    elif owner != h["document_id"]:
                        problems.append(f"{block_id}: 다른 문서 소속({owner})")
            if case["document_id"] not in provenance_docs:
                problems.append(f"{case['document_id']}: provenance 행 없음")
            trace = "OK" if not problems else "실패 - " + "; ".join(problems[:3])
            trace_ok += not problems

        print(f"[{case['case_id']}] {'PASS' if ok else 'FAIL'}  ({case['purpose']})")
        print(f"  질문     : {case['question']}")
        print(f"  정답청크 : {sorted(oracle)}")
        print(f"  최초순위 : {rank if rank else '없음'}")
        print(f"  역추적   : {trace}")
        for h in hits:
            mark = " <-- 정답" if h["chunk_id"] in oracle else ""
            print(f"    {h['rank']}. {h['chunk_id']}  score={h['score']:.4f}{mark}")
        print()

    # RUNTIME_SMOKE_RUNBOOK_v0.3.md 의 PASS 조건 순서대로 출력한다.
    n = len(cases)
    mrr = sum(reciprocal_ranks) / n if n else 0.0
    print("=" * 60)
    print(f"Top-{args.top_k} 반환          : {returned_full}/{n}  (문서 청크 수가 적으면 그만큼만)")
    print(f"정답 청크 포함        : {passed}/{n}")
    print(f"MRR                   : {mrr:.4f}")
    print(f"Hard Scope violation  : {scope_violations}  (0 이어야 함)")
    if block_owner:
        print(f"provenance 역추적     : {trace_ok}/{n}")
    else:
        print("provenance 역추적     : 건너뜀 (--package-dir 를 주면 검증한다)")
    print("Final Holdout access  : 0  (이 스크립트는 holdout 을 읽지 않는다)")

    ok = (returned_full == n and passed == n and scope_violations == 0
          and (not block_owner or trace_ok == n))
    print(f"\nRetriever 측 R/G_COMPATIBILITY 근거: {'PASS' if ok else 'FAIL'}")
    print("  (Generation input schema / Citation invalid ID 는 생성기 쪽에서 확인해야 한다)")
    if not ok:
        print("\n  주의: RUNBOOK 지침 - 이 5건을 보고 반복 튜닝하지 말고")
        print("        DATA / RETRIEVAL / GENERATION / CITATION 중 원인을 먼저 귀속할 것")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
