"""ai/scripts/evaluate.py — RAG 검색 품질 평가.

    python ai/scripts/evaluate.py \\
        --gold ai/data/processed/gold_questions_sample.jsonl \\
        [--report] [--export retrieval_results.jsonl]

기본으로 Hit@k / nDCG@k / MRR / Scope Violations 를 계산해 출력한다.
--report 를 주면 질문별 정성 평가 마크다운 리포트를 추가로 생성하고,
--export 를 주면 질문별 원시 검색 결과(hits)를 JSONL로 저장한다.
(지표 정의: docs/RETRIEVAL_HANDOFF_v0.1.md 4장)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from ai.ingestion.loaders import load_jsonl
from ai.rag.retriever import retrieve

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ai/
DATA_DIR = PROJECT_ROOT / "data"


def gold_chunk_ids(question: dict) -> set[str]:
    ids = set()
    for ev in question["gold_evidence"]:
        ids.update(ev["c0_chunk_ids"])
    return ids


def _dcg(relevances: list[int]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    relevances = [1 if rid in gold_ids else 0 for rid in retrieved_ids[:k]]
    idcg = _dcg(sorted(relevances, reverse=True))
    return _dcg(relevances) / idcg if idcg > 0 else 0.0


def evaluate(gold_questions: list[dict], k: int = 5) -> dict:
    hits, ndcgs, reciprocal_ranks = [], [], []
    skipped_unanswerable = 0
    scope_violations = 0

    for q in gold_questions:
        if q["answerability"] == "UNANSWERABLE":
            skipped_unanswerable += 1
            continue

        gold_ids = gold_chunk_ids(q)
        # P0: 반드시 정답 문서(document_id) 안에서만 검색 (Hard Filter)
        results = retrieve(q["question"], top_k=k, document_id=q["document_id"])
        retrieved_ids = [r["chunk_id"] for r in results]

        scope_violations += sum(1 for r in results if r["document_id"] != q["document_id"])

        if q["evidence_logic"] == "ALL":
            hit = gold_ids.issubset(set(retrieved_ids))
        else:  # ANY
            hit = len(gold_ids & set(retrieved_ids)) > 0
        hits.append(hit)

        ndcgs.append(ndcg_at_k(retrieved_ids, gold_ids, k))

        rank = next((i + 1 for i, rid in enumerate(retrieved_ids) if rid in gold_ids), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)

    n = len(hits)
    return {
        "n_questions": n,
        "skipped_unanswerable": skipped_unanswerable,
        f"Hit@{k}": sum(hits) / n,
        f"nDCG@{k}": sum(ndcgs) / n,
        "MRR": sum(reciprocal_ranks) / n,
        "Scope_Violations": scope_violations,  # 반드시 0이어야 함 (retrieve()의 hard filter가 정상이면 항상 0)
    }


def _truncate(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[:n] + "..."


def build_qualitative_report(gold_questions: list[dict], k: int = 5) -> str:
    lines = ["# Retrieval 정성 평가 리포트\n"]

    for q in gold_questions:
        lines.append(f"## [{q['question_id']}] {q['question']}")
        lines.append(
            f"- 문서: {q['document_id']} / 답변가능여부: {q['answerability']} "
            f"/ evidence_logic: {q.get('evidence_logic')}"
        )
        lines.append(f"- Gold Answer: {q['gold_answer']}")

        if q["answerability"] == "UNANSWERABLE":
            gold_ids = set()
        else:
            gold_ids = gold_chunk_ids(q)
            lines.append(f"- Gold Chunk IDs: {sorted(gold_ids)}")

        hits = retrieve(q["question"], top_k=k, document_id=q["document_id"])

        lines.append(f"\n**검색된 top-{k}**")
        lines.append("| 순위 | 정답여부 | chunk_id | score | 내용 미리보기 |")
        lines.append("|---|---|---|---|---|")
        for rank, hit in enumerate(hits, start=1):
            mark = "✅" if hit["chunk_id"] in gold_ids else ""
            lines.append(
                f"| {rank} | {mark} | {hit['chunk_id']} | {hit['score']:.3f} | {_truncate(hit['text'])} |"
            )

        if q["answerability"] == "UNANSWERABLE":
            lines.append(
                "\n> ⚠️ 이 질문은 원래 '문서에 없음'이 정답입니다. "
                "위 top-5가 그럴듯해 보인다면, 검색이 억지로 관련 없는 내용을 끌어온 건 아닌지 직접 확인 필요."
            )
        elif not any(h["chunk_id"] in gold_ids for h in hits):
            lines.append("\n> ❌ RETRIEVAL_ERROR — Gold Chunk가 top-5 안에 전혀 없음")
        elif hits[0]["chunk_id"] not in gold_ids:
            lines.append("\n> ⚠️ 정답이 1위가 아님 — 왜 다른 청크가 더 높은 점수를 받았는지 확인 필요")

        lines.append("\n---\n")

    return "\n".join(lines)


def export_results(gold_questions: list[dict], output_path: str, top_k: int = 5) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for q in gold_questions:
            if q["answerability"] == "UNANSWERABLE":
                hits = []  # 문서에 답이 없는 질문 -> 검색 결과 없이 그대로 전달 (Generation이 Abstention 처리)
            else:
                hits = retrieve(q["question"], top_k=top_k, document_id=q["document_id"])

            record = {
                "question_id": q["question_id"],
                "selected_document_id": q["document_id"],
                "question": q["question"],
                "hits": hits,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"저장 완료: {output_path} ({len(gold_questions)}개 질문)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieval 품질 평가 (Hit@k/nDCG@k/MRR) + 선택적 정성 리포트/원시 결과 export"
    )
    parser.add_argument("--gold", default=str(DATA_DIR / "processed" / "gold_questions_sample.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", action="store_true", help="정성 평가 마크다운 리포트도 생성한다")
    parser.add_argument(
        "--report-path", default=str(Path(__file__).parent / "qualitative_report.md")
    )
    parser.add_argument("--export", default=None, help="질문별 원시 검색 결과(hits)를 저장할 JSONL 경로")
    args = parser.parse_args()

    gold_questions = load_jsonl(args.gold)

    metrics = evaluate(gold_questions, k=args.top_k)
    for key, value in metrics.items():
        print(f"{key}: {value}")

    if args.report:
        report = build_qualitative_report(gold_questions, k=args.top_k)
        Path(args.report_path).write_text(report, encoding="utf-8")
        print(f"{args.report_path} 생성 완료")

    if args.export:
        export_results(gold_questions, args.export, top_k=args.top_k)


if __name__ == "__main__":
    main()
