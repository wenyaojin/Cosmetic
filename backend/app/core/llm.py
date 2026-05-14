from openai import AsyncOpenAI
from app.core.config import get_settings, Settings
from app.core.observe import create_generation
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
        trace=None,
        generation_name: str = "llm_chat",
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content or ""
        usage = None
        if resp.usage:
            usage = {
                "input": resp.usage.prompt_tokens,
                "output": resp.usage.completion_tokens,
                "total": resp.usage.total_tokens,
            }
        create_generation(trace, generation_name, self._model, messages, content, usage)
        return content

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        trace=None,
        generation_name: str = "llm_chat_stream",
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        full_content = []
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_content.append(delta)
                yield delta

        create_generation(trace, generation_name, self._model, messages, "".join(full_content))


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
