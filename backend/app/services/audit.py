from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from app.core.logging import get_logger

logger = get_logger("audit")


async def log_event(db: AsyncSession, session_id=None, event_type: str = "", detail: dict | None = None):
    entry = AuditLog(session_id=session_id, event_type=event_type, detail=detail)
    db.add(entry)
    logger.info("Audit [%s] session=%s detail=%s", event_type, session_id, detail)
