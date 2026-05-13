import httpx
from app.core.config import get_settings, Settings
from app.core.logging import get_logger

logger = get_logger("reranker")


class RerankerClient:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._api_key = s.reranker_api_key
        self._base_url = s.reranker_base_url.rstrip("/")
        self._model = s.reranker_model

    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[dict]:
        if not self._api_key:
            logger.warning("Reranker API key not set, skipping rerank")
            return [
                {"index": i, "relevance_score": 1.0 - i * 0.01}
                for i in range(min(top_n, len(documents)))
            ]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results


_reranker_client: RerankerClient | None = None


def get_reranker_client() -> RerankerClient:
    global _reranker_client
    if _reranker_client is None:
        _reranker_client = RerankerClient()
    return _reranker_client
