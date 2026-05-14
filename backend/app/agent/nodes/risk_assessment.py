import json
from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.core.llm import get_llm_client
from app.core.logging import get_logger
from app.core.observe import create_span, end_span

logger = get_logger("agent.risk")

RISK_PROMPT = """你是医美风险评估模块。根据用户信息和检索到的资料，评估风险。

用户信息：
{profile}

用户想了解的项目/问题：
{query}

参考资料中的禁忌症信息：
{contraindications}

请返回 JSON（不要 markdown 代码块）：
{{
    "risk_flags": ["具体风险点列表，没有风险则为空数组"],
    "risk_level": "low|medium|high",
    "advice": "简短风险建议"
}}"""


async def risk_assessment_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    trace = config["configurable"].get("trace")
    span = create_span(trace, "risk_assessment")
    profile = state.get("user_profile", {})
    docs = state.get("retrieved_docs", [])

    if not profile and not docs:
        end_span(span, {"skipped": True})
        return {**state, "risk_flags": []}

    contra_texts = []
    for doc in docs:
        text = doc.get("text", "")
        if "禁忌" in text or "风险" in text or "并发" in text:
            contra_texts.append(text[:300])

    if not contra_texts and not any(profile.get(k) for k in ("allergies", "contraindications")):
        end_span(span, {"skipped": True})
        return {**state, "risk_flags": []}

    llm = get_llm_client()
    prompt = RISK_PROMPT.format(
        profile=json.dumps(profile, ensure_ascii=False),
        query=state.get("user_message", ""),
        contraindications="\n---\n".join(contra_texts) if contra_texts else "无相关信息",
    )

    raw = await llm.chat([{"role": "user", "content": prompt}], temperature=0.1, trace=trace, generation_name="risk_assessment")

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(cleaned)
        risk_flags = result.get("risk_flags", [])
    except (json.JSONDecodeError, IndexError):
        logger.warning("Risk parse failed. Raw: %s", raw[:200])
        risk_flags = []

    end_span(span, {"risk_flags": risk_flags})
    return {**state, "risk_flags": risk_flags}
