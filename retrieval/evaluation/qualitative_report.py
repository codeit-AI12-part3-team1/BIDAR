import os
import sys

import chromadb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from embeddings import KureEmbedder
from eval import gold_chunk_ids
from ingest import load_jsonl
from search import search

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def truncate(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[:n] + "..."


def build_report(collection, embedder, gold_questions: list[dict], k: int = 5) -> str:
    lines = ["# Retrieval 정성 평가 리포트\n"]

    for q in gold_questions:
        lines.append(f"## [{q['question_id']}] {q['question']}")
        lines.append(f"- 문서: {q['document_id']} / 답변가능여부: {q['answerability']} / evidence_logic: {q.get('evidence_logic')}")
        lines.append(f"- Gold Answer: {q['gold_answer']}")

        if q["answerability"] == "UNANSWERABLE":
            gold_ids = set()
        else:
            gold_ids = gold_chunk_ids(q)
            lines.append(f"- Gold Chunk IDs: {sorted(gold_ids)}")

        hits = search(collection, embedder, q["question"], selected_document_id=q["document_id"], top_k=k)

        lines.append(f"\n**검색된 top-{k}**")
        lines.append("| 순위 | 정답여부 | chunk_id | score | 내용 미리보기 |")
        lines.append("|---|---|---|---|---|")
        for rank, hit in enumerate(hits, start=1):
            mark = "✅" if hit["chunk_id"] in gold_ids else ""
            lines.append(
                f"| {rank} | {mark} | {hit['chunk_id']} | {hit['score']:.3f} | {truncate(hit['text'])} |"
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


if __name__ == "__main__":
    embedder = KureEmbedder(device="cuda")

    client = chromadb.PersistentClient(path=os.path.join(PROJECT_ROOT, "chroma_db"))
    collection = client.get_collection("rfp_chunks")

    gold_questions = load_jsonl(os.path.join(PROJECT_ROOT, "data", "gold_questions_sample.jsonl"))
    report = build_report(collection, embedder, gold_questions, k=5)

    report_path = os.path.join(os.path.dirname(__file__), "qualitative_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"{report_path} 생성 완료")
