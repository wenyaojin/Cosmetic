import json
from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.core.logging import get_logger
from app.core.observe import create_span, end_span

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
- 当「权威项目卡片」与「参考资料」冲突时，**以项目卡片为准**（卡片是经过结构化校对的事实，更可靠）
- 不要在回答末尾加免责声明（系统会自动追加）

**回答风格（重要）**：
- 即使用户信息不完整，也要**基于现有信息直接给方案**，不要反复追问。
- 通常列出 2-3 种主流选择（含大致价格、维持时间、主要风险），让用户先有全貌。
- 如果上下文里有「可选追问」，**在回答最末尾**用 1 句话自然提出（例如"如果方便告诉我您的预算，我可以更精准地为您筛选"），**不要单独占段、不要列表化、不要在回答开头问**。
- 如果没有「可选追问」，正常结束即可，不要自己编追问。
"""


def _build_context(state: ConsultState) -> str:
    parts = []

    profile = state.get("user_profile", {})
    if any(v for v in profile.values() if v is not None and v != []):
        parts.append(f"=== 用户信息 ===\n{json.dumps(profile, ensure_ascii=False, indent=2)}")

    vf = state.get("visual_features")
    if vf and vf.get("top_feature"):
        triggered = ", ".join(vf.get("triggered_principles") or []) or "（无）"
        parts.append(
            "=== 用户上传照片的视觉分析（医生 framework：骨/软组织/皮肤 三层）===\n"
            f"主要特征: {vf['top_feature']}（层级: {vf.get('top_layer', 'unknown')}）\n"
            f"触发的临床 principle: {triggered}\n\n"
            f"详细分层观察：\n{vf.get('raw_text', '')}"
        )

    # Project cards come BEFORE retrieved docs so they get higher attention
    # weight and so the system rule above ("cards win over passages") has a
    # clear textual anchor. Each card is already formatted by card_to_context.
    cards = state.get("project_cards", [])
    if cards:
        parts.append(
            "=== 权威项目卡片（结构化事实，优先采信）===\n"
            + "\n\n".join(cards)
        )

    docs = state.get("retrieved_docs", [])
    if docs:
        refs = []
        for i, doc in enumerate(docs, 1):
            meta = doc.get("metadata") or {}
            source_url = meta.get("source_url")
            source_note = f"，链接: {source_url}" if source_url else ""
            refs.append(f"[{i}] 《{doc['title']}》（来源: {doc['source']}，权威等级: L{doc['authority_level']}{source_note}）\n{doc['text']}")
        parts.append("=== 参考资料 ===\n" + "\n\n".join(refs))

    risk_flags = state.get("risk_flags", [])
    if risk_flags:
        parts.append("=== 风险提示 ===\n" + "\n".join(f"⚠ {f}" for f in risk_flags))

    followup = (state.get("followup_hint") or "").strip()
    if followup:
        parts.append(
            "=== 可选追问（在回答最末尾用一句自然的话提出，不要在开头问）===\n"
            + followup
        )

    parts.append(f"=== 用户问题 ===\n{state['user_message']}")
    return "\n\n".join(parts)


async def recommend_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    """Prepare LLM messages; actual LLM call is performed by the router."""
    trace = config["configurable"].get("trace")
    span = create_span(trace, "recommend")
    context = _build_context(state)

    messages = [
        {"role": "system", "content": RECOMMEND_SYSTEM},
    ]
    for msg in state.get("history", []):
        messages.append(msg)
    messages.append({"role": "user", "content": context})

    docs = state.get("retrieved_docs", [])
    citations = [
        {
            "index": i + 1,
            "title": d["title"],
            "source": d["source"],
            "url": (d.get("metadata") or {}).get("source_url", ""),
        }
        for i, d in enumerate(docs)
    ]

    end_span(span, {"citation_count": len(citations)})
    return {
        **state,
        "llm_messages": messages,
        "citations": citations,
        "needs_disclaimer": True,
    }
