import uuid
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.session import Session, Message
from app.core.logging import get_logger

logger = get_logger("session")

MAX_HISTORY_TURNS = 20


async def get_or_create_session(db: AsyncSession, session_id: str | None) -> tuple[uuid.UUID, dict]:
    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            sid = None
        if sid:
            result = await db.execute(select(Session).where(Session.id == sid))
            session = result.scalar_one_or_none()
            if session:
                return session.id, session.user_profile or {}

    session = Session()
    db.add(session)
    await db.flush()
    logger.info("Created new session %s", session.id)
    return session.id, {}


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    intent: str | None = None,
    citations: list | None = None,
) -> None:
    count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.session_id == session_id)
    )
    seq = count_result.scalar() or 0

    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        citations={"items": citations} if citations else None,
        seq=seq,
    )
    db.add(msg)


async def get_history(db: AsyncSession, session_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.seq.asc())
        .limit(MAX_HISTORY_TURNS * 2)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


async def update_session_profile(db: AsyncSession, session_id: uuid.UUID, profile: dict) -> None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session:
        existing = session.user_profile or {}
        for k, v in profile.items():
            if v is not None and v != [] and v != "":
                existing[k] = v
        session.user_profile = existing


async def list_sessions(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Session).order_by(Session.updated_at.desc()).limit(50)
    )
    sessions = result.scalars().all()

    out = []
    for s in sessions:
        first_msg = await db.execute(
            select(Message.content)
            .where(Message.session_id == s.id, Message.role == "user")
            .order_by(Message.seq.asc())
            .limit(1)
        )
        title_row = first_msg.scalar_one_or_none()
        title = (title_row[:30] + "…") if title_row and len(title_row) > 30 else (title_row or "新对话")
        out.append({
            "id": str(s.id),
            "title": title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        })
    return out


async def delete_session(db: AsyncSession, session_id: str) -> dict | None:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None
    result = await db.execute(select(Session).where(Session.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        return None
    msg_result = await db.execute(delete(Message).where(Message.session_id == sid))
    await db.execute(delete(Session).where(Session.id == sid))
    await db.commit()
    return {
        "session_id": str(sid),
        "messages_deleted": msg_result.rowcount,
    }
