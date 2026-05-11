import json
from app.agent.state import ConsultState
from app.core.logging import get_logger

logger = get_logger("agent.recommend")

RECOMMEND_SYSTEM = """你是一个专业的医美咨询助手。你的职责是：
1. 基于参考资料准确回答用户问题
2. 根据用户个人信息提供个性化建议
3. 提醒潜在风险和禁忌症
4. 回答中使用 [1][2] 标注引用了哪条参考资料

重要规则：
- 你不是医生，不做诊断，不开处方
- 回答必须基于提供的参考资料，不要编造信息
- 如果参考资料不足以回答，诚实说明"暂无相关资料"
- 不要在回答末尾加免责声明（系统会自动追加）
"""


def _build_context(state: ConsultState) -> str:
    parts = []

    profile = state.get("user_profile", {})
    if any(v for v in profile.values() if v is not None and v != []):
        parts.append(f"=== 用户信息 ===\n{json.dumps(profile, ensure_ascii=False, indent=2)}")

    docs = state.get("retrieved_docs", [])
    if docs:
        refs = []
        for i, doc in enumerate(docs, 1):
            refs.append(f"[{i}] 《{doc['title']}》（来源: {doc['source']}，权威等级: L{doc['authority_level']}）\n{doc['text']}")
        parts.append("=== 参考资料 ===\n" + "\n\n".join(refs))

    risk_flags = state.get("risk_flags", [])
    if risk_flags:
        parts.append("=== 风险提示 ===\n" + "\n".join(f"⚠ {f}" for f in risk_flags))

    parts.append(f"=== 用户问题 ===\n{state['user_message']}")
    return "\n\n".join(parts)


async def recommend_node(state: ConsultState) -> ConsultState:
    """Prepare LLM messages; actual LLM call is performed by the router."""
    context = _build_context(state)

    messages = [
        {"role": "system", "content": RECOMMEND_SYSTEM},
    ]
    for msg in state.get("history", []):
        messages.append(msg)
    messages.append({"role": "user", "content": context})

    docs = state.get("retrieved_docs", [])
    citations = [{"index": i + 1, "title": d["title"], "source": d["source"]} for i, d in enumerate(docs)]

    return {
        **state,
        "llm_messages": messages,
        "citations": citations,
        "needs_disclaimer": True,
    }
