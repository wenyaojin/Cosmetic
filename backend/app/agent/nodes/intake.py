import json
from langchain_core.runnables import RunnableConfig
from app.core.llm import get_llm_client
from app.core.logging import get_logger
from app.core.observe import create_span, end_span
from app.agent.state import ConsultState

logger = get_logger("agent.intake")

INTAKE_PROMPT = """你是医美咨询助手的意图分析模块。分析用户消息，返回 JSON（不要 markdown 代码块）。

任务：
1. 识别用户意图（intent）
2. 从消息中提取用户信息（profile）
3. 判断是否还需要收集更多信息（need_more_info）

意图分类：
- "科普"：询问某个项目是什么、原理、效果等知识性问题
- "项目咨询"：对特定项目有兴趣，想了解适不适合自己
- "方案推荐"：希望根据自己的情况推荐合适的项目
- "术后护理"：已做过项目，询问护理或并发症问题
- "闲聊"：与医美无关的闲聊
- "拒答"：涉及具体诊断、开药、处方等需要执业医师的问题

返回格式：
{
    "intent": "科普|项目咨询|方案推荐|术后护理|闲聊|拒答",
    "profile": {
        "age": null或数字,
        "gender": null或"男"/"女",
        "skin_type": null或描述,
        "budget": null或描述,
        "allergies": [],
        "contraindications": [],
        "concerns": [],
        "prior_treatments": []
    },
    "need_more_info": true/false,
    "missing_fields": ["缺少的字段描述"],
    "followup_question": "如果need_more_info为true，这里填要追问的问题"
}"""


async def intake_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    trace = config["configurable"].get("trace")
    span = create_span(trace, "intake", state["user_message"])
    llm = get_llm_client()

    messages = [
        {"role": "system", "content": INTAKE_PROMPT},
    ]
    for msg in state.get("history", []):
        messages.append(msg)
    messages.append({"role": "user", "content": state["user_message"]})

    raw = await llm.chat(messages, temperature=0.1, trace=trace, generation_name="intake")

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        logger.warning("Intake parse failed, defaulting to 科普. Raw: %s", raw[:200])
        end_span(span, {"error": "parse_failed"})
        return {
            **state,
            "intent": "科普",
            "profile_complete": True,
        }

    profile = state.get("user_profile", {})
    new_profile = result.get("profile", {})
    for k, v in new_profile.items():
        if v is not None and v != [] and v != "":
            profile[k] = v

    intent = result.get("intent", "科普")
    need_more = result.get("need_more_info", False)

    if need_more and intent in ("方案推荐", "项目咨询"):
        followup = result.get("followup_question", "请问您的年龄和主要诉求是什么？")
        end_span(span, {"intent": intent, "profile_complete": False})
        return {
            **state,
            "intent": intent,
            "user_profile": profile,
            "profile_complete": False,
            "response": followup,
        }

    end_span(span, {"intent": intent, "profile_complete": True})
    return {
        **state,
        "intent": intent,
        "user_profile": profile,
        "profile_complete": True,
    }
