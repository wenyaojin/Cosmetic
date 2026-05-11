from openai import AsyncOpenAI
from app.core.config import get_settings, Settings


class EmbeddingClient:
    """Embedding client for bge-large-zh via OpenAI-compatible API."""

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._client = AsyncOpenAI(
            api_key=s.embedding_api_key,
            base_url=s.embedding_base_url,
        )
        self._model = s.embedding_model
        self.dim = s.embedding_dim

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await self._client.embeddings.create(
                model=self._model,
                input=batch,
            )
            results.extend([d.embedding for d in resp.data])
        return results


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
