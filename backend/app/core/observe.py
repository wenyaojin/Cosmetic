from langfuse import Langfuse
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("observe")

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    global _langfuse
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return None
    if "xxxx" in s.langfuse_public_key:
        return None
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
        logger.info("Langfuse initialized: %s", s.langfuse_host)
    return _langfuse


def create_trace(session_id: str, user_message: str):
    lf = get_langfuse()
    if not lf:
        return None
    return lf.trace(
        session_id=session_id,
        input=user_message,
        metadata={"source": "agent_chat"},
    )


def create_span(trace, name: str, input_data=None):
    if not trace:
        return None
    return trace.span(name=name, input=input_data)


def end_span(span, output_data=None):
    if span:
        span.end(output=output_data)


def create_generation(trace, name: str, model: str, messages: list[dict], completion: str, usage: dict | None = None):
    if not trace:
        return
    trace.generation(
        name=name,
        model=model,
        input=messages,
        output=completion,
        usage=usage,
    )


def flush():
    if _langfuse:
        _langfuse.flush()
