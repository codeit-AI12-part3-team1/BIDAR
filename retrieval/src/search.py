import json


def search(collection, embedder, question: str, selected_document_id: str, top_k: int = 5) -> list[dict]:
    """P0 Selected-document scope: selected_document_id는 필수이며 Hard Filter로 적용된다.
    (Similarity Score보다 우선 — 다른 문서 결과가 섞이면 RETRIEVAL_SCOPE_ERROR)
    """
    q_vector = embedder.embed_query(question)

    results = collection.query(
        query_embeddings=[q_vector],
        n_results=top_k,
        where={"document_id": selected_document_id},
    )

    hits = []
    for i, chunk_id in enumerate(results["ids"][0]):
        metadata = results["metadatas"][0][i]
        assert metadata["document_id"] == selected_document_id, "RETRIEVAL_SCOPE_ERROR"
        hits.append(
            {
                "chunk_id": chunk_id,
                "document_id": metadata["document_id"],
                "score": 1 - results["distances"][0][i],  # cosine distance -> similarity
                "text": results["documents"][0][i],
                "section_path": json.loads(metadata.get("section_path", "[]")),
                "requirement_ids": json.loads(metadata.get("requirement_ids", "[]")),
            }
        )
    return hits


if __name__ == "__main__":
    import os

    import chromadb

    from embeddings import KureEmbedder

    PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

    embedder = KureEmbedder(device="cuda")
    client = chromadb.PersistentClient(path=os.path.join(PROJECT_ROOT, "chroma_db"))
    collection = client.get_collection("rfp_chunks")

    for hit in search(collection, embedder, "이 사업의 소요예산은 얼마인가?", selected_document_id="DOC_001"):
        print(hit)
