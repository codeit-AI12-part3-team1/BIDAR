from sentence_transformers import SentenceTransformer


class KureEmbedder:
    """시나리오 A (로컬): nlpai-lab/KURE-v1"""

    def __init__(self, device: str = "cuda"):
        self.model = SentenceTransformer("nlpai-lab/KURE-v1", device=device)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


class OpenAIEmbedder:
    """시나리오 B (API): text-embedding-3-small"""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
