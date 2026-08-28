import json
import os

import chromadb

from embeddings import KureEmbedder
from ingest import load_jsonl
from search import search

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def export_results(
    collection,
    embedder,
    gold_questions: list[dict],
    output_path: str,
    top_k: int = 5,
):
    with open(output_path, "w", encoding="utf-8") as f:
        for q in gold_questions:
            if q["answerability"] == "UNANSWERABLE":
                hits = []  # 문서에 답이 없는 질문 -> 검색 결과 없이 그대로 전달 (Generation이 Abstention 처리)
            else:
                hits = search(
                    collection,
                    embedder,
                    q["question"],
                    selected_document_id=q["document_id"],
                    top_k=top_k,
                )

            record = {
                "question_id": q["question_id"],
                "selected_document_id": q["document_id"],
                "question": q["question"],
                "hits": hits,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"저장 완료: {output_path} ({len(gold_questions)}개 질문)")


if __name__ == "__main__":
    embedder = KureEmbedder(device="cuda")
    client = chromadb.PersistentClient(path=os.path.join(PROJECT_ROOT, "chroma_db"))
    collection = client.get_collection("rfp_chunks")

    gold_questions = load_jsonl(os.path.join(PROJECT_ROOT, "data", "gold_questions_sample.jsonl"))
    export_results(
        collection, embedder, gold_questions, os.path.join(PROJECT_ROOT, "retrieval_results.jsonl")
    )
