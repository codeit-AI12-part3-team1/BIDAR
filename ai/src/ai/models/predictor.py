from ai.rag.retriever import retrieve
from ai.rag.chain import generate_answer

def predict(query: str, document_id: str, backend: str = "local"):
    hits = retrieve(question=query, document_id=document_id)
    return generate_answer(question=query, hits=hits, backend=backend)["answer"]