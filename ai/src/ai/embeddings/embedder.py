"""ai.embeddings.embedder - 임베딩 모델 래퍼.

시나리오 A(로컬): nlpai-lab/KURE-v1, dim=1024, normalize_embeddings=True
시나리오 B(API) : text-embedding-3-small

색인과 질의는 반드시 같은 모델·같은 정규화 설정을 써야 한다.
정규화된 벡터에서 cosine 유사도 = 내적이므로, 색인 컬렉션은 hnsw:space="cosine" 으로 만든다.
"""

from __future__ import annotations

KURE_MODEL_ID = "nlpai-lab/KURE-v1"
KURE_DIM = 1024


class KureEmbedder:
    """시나리오 A (로컬): nlpai-lab/KURE-v1"""

    model_id = KURE_MODEL_ID
    dim = KURE_DIM

    def __init__(self, device: str = "cuda"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(KURE_MODEL_ID, device=device)

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


class OpenAIEmbedder:
    """시나리오 B (API): text-embedding-3-small"""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model_id = model

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            resp = self.client.embeddings.create(
                model=self.model_id, input=texts[i : i + batch_size]
            )
            out.extend(d.embedding for d in resp.data)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
