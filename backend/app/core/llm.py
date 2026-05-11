from openai import AsyncOpenAI
from app.core.config import get_settings, Settings
from typing import AsyncIterator


class LLMClient:
    """LLM client wrapper (OpenAI SDK compatible: DeepSeek / Qwen / etc.)."""

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._client = AsyncOpenAI(
            api_key=s.llm_api_key,
            base_url=s.llm_base_url,
        )
        self._model = s.llm_model

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
