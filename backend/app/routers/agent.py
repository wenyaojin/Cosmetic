import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import ChatRequest
from app.core.database import get_db
from app.core.llm import get_llm_client
from app.agent.graph import run_agent
from app.agent.nodes.disclaim import DISCLAIMER
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1", tags=["agent"])
logger = get_logger("agent_router")

LLM_TEMPERATURE = 0.5


def _is_early_return(state: dict) -> bool:
    """True if graph already produced a final response without invoking LLM."""
    return state.get("blocked", False) or not state.get("profile_complete", True)


@router.post("/agent/chat")
async def agent_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Full agent pipeline: graph builds context, router invokes LLM."""
    try:
        state = await run_agent(
            user_message=req.message,
            db=db,
            session_id=req.session_id or "",
        )

        if _is_early_return(state):
            return {
                "message": state.get("response", ""),
                "citations": [],
                "intent": state.get("intent"),
                "risk_flags": [],
                "blocked": state.get("blocked", False),
                "session_id": req.session_id,
            }

        llm = get_llm_client()
        response = await llm.chat(state["llm_messages"], temperature=LLM_TEMPERATURE)

        if state.get("needs_disclaimer", False) and DISCLAIMER.strip() not in response:
            response += DISCLAIMER

        return {
            "message": response,
            "citations": state.get("citations", []),
            "intent": state.get("intent"),
            "risk_flags": state.get("risk_flags", []),
            "blocked": False,
            "session_id": req.session_id,
        }
    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Agent processing failed")


@router.post("/agent/chat/stream")
async def agent_chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Same pipeline, but streams the final LLM tokens via SSE."""
    state = await run_agent(
        user_message=req.message,
        db=db,
        session_id=req.session_id or "",
    )

    async def event_generator():
        try:
            yield {"event": "status", "data": json.dumps({"intent": state.get("intent")}, ensure_ascii=False)}

            if _is_early_return(state):
                yield {"event": "token", "data": json.dumps({"text": state.get("response", "")}, ensure_ascii=False)}
                yield {"event": "done", "data": json.dumps({
                    "session_id": req.session_id,
                    "blocked": state.get("blocked", False),
                    "needs_more_info": not state.get("profile_complete", True),
                })}
                return

            yield {"event": "citations", "data": json.dumps({"citations": state.get("citations", [])}, ensure_ascii=False)}

            llm = get_llm_client()
            async for token in llm.chat_stream(state["llm_messages"], temperature=LLM_TEMPERATURE):
                yield {"event": "token", "data": json.dumps({"text": token}, ensure_ascii=False)}

            if state.get("needs_disclaimer", False):
                yield {"event": "token", "data": json.dumps({"text": DISCLAIMER}, ensure_ascii=False)}

            yield {"event": "done", "data": json.dumps({"session_id": req.session_id})}

        except Exception as e:
            logger.error("Agent stream error: %s", e, exc_info=True)
            yield {"event": "error", "data": json.dumps({"detail": "Agent processing failed"})}

    return EventSourceResponse(event_generator())
