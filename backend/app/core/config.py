from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_env: str = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://cosmetic:cosmetic_dev_pwd@localhost:5432/cosmetic"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM (OpenAI-compatible: DeepSeek / Qwen DashScope / etc.)
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"

    # Embedding
    embedding_provider: str = "siliconflow"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_dim: int = 1024

    # Reranker
    reranker_api_key: str = ""
    reranker_base_url: str = "https://api.siliconflow.cn/v1"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Langfuse
    langfuse_host: str = "http://localhost:3001"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # RAG enhancements (toggle per technique for ablation studies)
    use_query_rewrite: bool = True
    use_hyde: bool = True
    use_small_to_big: bool = True
    use_structured_kb: bool = True

    # Query rewriting
    query_rewrite_n: int = 4  # number of rewrites per query

    # Small-to-big chunking
    child_chunk_size: int = 256
    child_chunk_overlap: int = 32
    parent_chunk_size: int = 1536
    parent_chunk_overlap: int = 128

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
