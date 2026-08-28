import math
import os
import sys

import chromadb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from embeddings import KureEmbedder
from ingest import build_index, load_jsonl
from search import search


def gold_chunk_ids(question: dict) -> set[str]:
    ids = set()
    for ev in question["gold_evidence"]:
        ids.update(ev["c0_chunk_ids"])
    return ids


def dcg(relevances: list[int]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    relevances = [1 if rid in gold_ids else 0 for rid in retrieved_ids[:k]]
    idcg = dcg(sorted(relevances, reverse=True))
    return dcg(relevances) / idcg if idcg > 0 else 0.0


def evaluate(collection, embedder, gold_questions: list[dict], k: int = 5) -> dict:
    hits, ndcgs, reciprocal_ranks = [], [], []
    skipped_unanswerable = 0
    scope_violations = 0

    for q in gold_questions:
        if q["answerability"] == "UNANSWERABLE":
            skipped_unanswerable += 1
            continue

        gold_ids = gold_chunk_ids(q)
        # P0: 반드시 정답 문서(selected_document_id) 안에서만 검색 (Hard Filter)
        results = search(collection, embedder, q["question"], selected_document_id=q["document_id"], top_k=k)
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
        "Scope_Violations": scope_violations,  # 반드시 0이어야 함 (search()의 hard filter가 정상이면 항상 0)
    }


PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

if __name__ == "__main__":
    embedder = KureEmbedder(device="cuda")

    # 이미 인덱싱된 컬렉션이 있으면 그대로 재사용 (없을 때만 새로 인덱싱)
    client = chromadb.PersistentClient(path=os.path.join(PROJECT_ROOT, "chroma_db"))
    try:
        collection = client.get_collection("rfp_chunks")
        print(f"기존 인덱스 재사용: {collection.count()}개 청크")
    except Exception:
        print("인덱스가 없어서 새로 생성합니다 (시간이 걸립니다)...")
        collection = build_index(
            os.path.join(PROJECT_ROOT, "data", "RFP100_chunks_C0_DEV_v0.1.jsonl"),
            embedder,
            documents_path=os.path.join(PROJECT_ROOT, "data", "RFP100_documents_DEV_v0.1.jsonl"),
        )

    gold_questions = load_jsonl(os.path.join(PROJECT_ROOT, "data", "gold_questions_sample.jsonl"))

    metrics = evaluate(collection, embedder, gold_questions, k=5)
    for key, value in metrics.items():
        print(f"{key}: {value}")
