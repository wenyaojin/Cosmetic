from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, chat, knowledge, agent
from app.core.database import get_engine, Base
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("main")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Cosmetic AI Agent",
        version="0.1.0",
        description="医美 AI 智能咨询 Agent API",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(knowledge.router)
    app.include_router(agent.router)

    @app.on_event("startup")
    async def on_startup():
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured, Cosmetic AI Agent started")

    return app


app = create_app()
