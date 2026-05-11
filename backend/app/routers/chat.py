import json
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from app.models.schemas import ChatRequest
from app.core.llm import get_llm_client
from app.core.database import get_db
from app.services.rag import search_similar
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = get_logger("chat")

SYSTEM_PROMPT = """你是一个专业的医美咨询助手。你的职责是：
1. 回答用户关于医美项目的科普问题
2. 根据用户情况提供项目推荐建议
3. 提醒潜在风险和禁忌症
4. 引导用户前往正规医疗机构面诊

重要规则：
- 你不是医生，不做诊断，不开处方
- 回答必须客观、有依据
- 如果提供了参考资料，必须基于资料回答并标注引用 [1][2]
- 如果没有相关资料，诚实告知"暂无相关资料"
- 每次回答末尾附上免责声明：「本回答仅供科普参考，不构成医疗建议。任何医美项目请前往正规医疗机构面诊评估。」
"""


def _build_rag_prompt(query: str, docs: list[dict]) -> str:
    if not docs:
        return query

    refs = []
    for i, doc in enumerate(docs, 1):
        refs.append(f"[{i}] 《{doc['title']}》（来源: {doc['source']}，权威等级: L{doc['authority_level']}）\n{doc['text']}")
    context = "\n\n".join(refs)

    return f"""请基于以下参考资料回答用户问题。回答中必须用 [1][2] 等标注引用了哪条资料。

=== 参考资料 ===
{context}

=== 用户问题 ===
{query}"""


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Non-streaming chat with RAG."""
    llm = get_llm_client()

    docs = await search_similar(db, req.message, top_k=5)
    user_content = _build_rag_prompt(req.message, docs)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        reply = await llm.chat(messages)
        citations = [{"index": i + 1, "title": d["title"], "source": d["source"]} for i, d in enumerate(docs)]
        return {"message": reply, "citations": citations, "session_id": req.session_id}
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM service unavailable")


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE streaming chat with RAG."""
    llm = get_llm_client()

    docs = await search_similar(db, req.message, top_k=5)
    user_content = _build_rag_prompt(req.message, docs)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    citations = [{"index": i + 1, "title": d["title"], "source": d["source"]} for i, d in enumerate(docs)]

    async def event_generator():
        try:
            yield {"event": "citations", "data": json.dumps({"citations": citations}, ensure_ascii=False)}
            async for token in llm.chat_stream(messages):
                yield {"event": "token", "data": json.dumps({"text": token}, ensure_ascii=False)}
            yield {"event": "done", "data": json.dumps({"session_id": req.session_id})}
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            yield {"event": "error", "data": json.dumps({"detail": "LLM service unavailable"})}

    return EventSourceResponse(event_generator())
