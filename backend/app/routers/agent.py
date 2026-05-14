import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import ChatRequest
from app.core.database import get_db
from app.core.llm import get_llm_client
from app.agent.graph import run_agent
from app.core.observe import create_trace, flush
from app.agent.nodes.disclaim import DISCLAIMER
from app.services.session import get_or_create_session, save_message, get_history, update_session_profile, list_sessions
from app.services.audit import log_event
from app.core.sanitizer import mask_pii, check_output
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1", tags=["agent"])
logger = get_logger("agent_router")

LLM_TEMPERATURE = 0.5


def _is_early_return(state: dict) -> bool:
    return state.get("blocked", False) or not state.get("profile_complete", True)


@router.post("/agent/chat")
async def agent_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Full agent pipeline with multi-turn session support."""
    try:
        session_id, saved_profile = await get_or_create_session(db, req.session_id)
        history = await get_history(db, session_id)

        sanitized_message = mask_pii(req.message)
        if sanitized_message != req.message:
            await log_event(db, session_id, "pii_masked", {"original_length": len(req.message)})

        await save_message(db, session_id, "user", sanitized_message)

        trace = create_trace(str(session_id), sanitized_message)

        state = await run_agent(
            user_message=sanitized_message,
            db=db,
            session_id=str(session_id),
            history=history,
            trace=trace,
        )

        if saved_profile:
            merged = {**saved_profile, **state.get("user_profile", {})}
            state["user_profile"] = merged

        if state.get("blocked"):
            await log_event(db, session_id, "blocked", {"reason": state.get("block_reason")})

        if _is_early_return(state):
            response_text = state.get("response", "")
            await save_message(db, session_id, "assistant", response_text, intent=state.get("intent"))
            if state.get("user_profile"):
                await update_session_profile(db, session_id, state["user_profile"])
            await db.commit()
            if trace:
                trace.update(output=response_text[:500])
                flush()
            return {
                "message": response_text,
                "citations": [],
                "intent": state.get("intent"),
                "risk_flags": [],
                "blocked": state.get("blocked", False),
                "session_id": str(session_id),
            }

        llm = get_llm_client()
        response = await llm.chat(state["llm_messages"], temperature=LLM_TEMPERATURE, trace=trace, generation_name="recommend_chat")

        forbidden = check_output(response)
        if forbidden:
            await log_event(db, session_id, "forbidden_output", {"words": forbidden})

        if state.get("needs_disclaimer", False) and DISCLAIMER.strip() not in response:
            response += DISCLAIMER

        await save_message(
            db, session_id, "assistant", response,
            intent=state.get("intent"),
            citations=state.get("citations"),
        )
        if state.get("user_profile"):
            await update_session_profile(db, session_id, state["user_profile"])
        await db.commit()

        if trace:
            trace.update(output=response[:500])
            flush()

        return {
            "message": response,
            "citations": state.get("citations", []),
            "intent": state.get("intent"),
            "risk_flags": state.get("risk_flags", []),
            "blocked": False,
            "session_id": str(session_id),
        }
    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Agent processing failed")


@router.post("/agent/chat/stream")
async def agent_chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Agent pipeline with streaming + multi-turn session."""
    session_id, saved_profile = await get_or_create_session(db, req.session_id)
    history = await get_history(db, session_id)

    sanitized_message = mask_pii(req.message)
    if sanitized_message != req.message:
        await log_event(db, session_id, "pii_masked", {"original_length": len(req.message)})

    await save_message(db, session_id, "user", sanitized_message)

    trace = create_trace(str(session_id), sanitized_message)

    state = await run_agent(
        user_message=sanitized_message,
        db=db,
        session_id=str(session_id),
        history=history,
        trace=trace,
    )

    if saved_profile:
        merged = {**saved_profile, **state.get("user_profile", {})}
        state["user_profile"] = merged

    if state.get("blocked"):
        await log_event(db, session_id, "blocked", {"reason": state.get("block_reason")})

    async def event_generator():
        try:
            yield {"event": "status", "data": json.dumps({"intent": state.get("intent"), "session_id": str(session_id)}, ensure_ascii=False)}

            if _is_early_return(state):
                response_text = state.get("response", "")
                yield {"event": "token", "data": json.dumps({"text": response_text}, ensure_ascii=False)}
                yield {"event": "done", "data": json.dumps({
                    "session_id": str(session_id),
                    "blocked": state.get("blocked", False),
                    "needs_more_info": not state.get("profile_complete", True),
                })}
                await save_message(db, session_id, "assistant", response_text, intent=state.get("intent"))
                if state.get("user_profile"):
                    await update_session_profile(db, session_id, state["user_profile"])
                await db.commit()
                return

            yield {"event": "citations", "data": json.dumps({"citations": state.get("citations", [])}, ensure_ascii=False)}

            llm = get_llm_client()
            full_response = []
            async for token in llm.chat_stream(state["llm_messages"], temperature=LLM_TEMPERATURE, trace=trace, generation_name="recommend_stream"):
                full_response.append(token)
                yield {"event": "token", "data": json.dumps({"text": token}, ensure_ascii=False)}

            if state.get("needs_disclaimer", False):
                full_response.append(DISCLAIMER)
                yield {"event": "token", "data": json.dumps({"text": DISCLAIMER}, ensure_ascii=False)}

            yield {"event": "done", "data": json.dumps({"session_id": str(session_id)})}

            response_text = "".join(full_response)

            forbidden = check_output(response_text)
            if forbidden:
                await log_event(db, session_id, "forbidden_output", {"words": forbidden})

            await save_message(
                db, session_id, "assistant", response_text,
                intent=state.get("intent"),
                citations=state.get("citations"),
            )
            if state.get("user_profile"):
                await update_session_profile(db, session_id, state["user_profile"])
            await db.commit()

            if trace:
                trace.update(output=response_text[:500])
                flush()

        except Exception as e:
            logger.error("Agent stream error: %s", e, exc_info=True)
            yield {"event": "error", "data": json.dumps({"detail": "Agent processing failed"})}

    return EventSourceResponse(event_generator())


@router.get("/sessions")
async def get_sessions(db: AsyncSession = Depends(get_db)):
    """List all sessions with their first user message as title."""
    sessions = await list_sessions(db)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve conversation history for a session."""
    history = await get_history(db, session_id)
    return {"session_id": session_id, "messages": history}
