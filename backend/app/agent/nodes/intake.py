import json
from langchain_core.runnables import RunnableConfig
from app.core.llm import get_llm_client
from app.core.logging import get_logger
from app.core.observe import create_span, end_span
from app.agent.state import ConsultState

logger = get_logger("agent.intake")

# Strings that signal the user wants a recommendation NOW, no more questions.
# Matched as substring; we accept some false positives ("不知道具体问题" ≈ "let it go")
# because the cost of over-asking is far higher than the cost of giving a generic answer.
BYPASS_PHRASES = (
    "先给方案", "先给一", "给个方案", "给一个方案", "给一套方案", "给我方案", "给我一套",
    "推荐一下", "推荐下", "有什么推荐", "推荐什么",
    "直接说", "直接推荐", "直接给",
    "随便", "无所谓", "都行", "都可以",
    "不清楚", "不知道", "不太知道", "不了解", "不太了解", "没了解过", "之前不了解", "不太清楚",
    "没有", "都没有",  # 用户回应"有没有过敏/禁忌"时的常见答复
    "先来", "先看看", "看看就行", "先了解",
)


def _is_bypass(msg: str) -> bool:
    return any(p in msg for p in BYPASS_PHRASES)


def _assistant_turns(history: list[dict]) -> int:
    """Count assistant messages already in this session — proxy for 'rounds asked'."""
    return sum(1 for m in history if m.get("role") == "assistant")


INTAKE_PROMPT = """你是医美咨询助手的意图分析模块。分析用户消息，返回 JSON（不要 markdown 代码块）。

任务：
1. 识别用户意图（intent）
2. 从消息中提取用户信息（profile）
3. 可选：建议一个**最关键**的追问问题（followup_question）

意图分类：
- "科普"：询问某个项目是什么、原理、效果等知识性问题
- "项目咨询"：对特定项目有兴趣，想了解适不适合自己
- "方案推荐"：希望根据自己的情况推荐合适的项目
- "术后护理"：已做过项目，询问护理或并发症问题
- "闲聊"：与医美无关的闲聊
- "拒答"：涉及具体诊断、开药、处方等需要执业医师的问题

**重要原则**：
- 默认**不要追问**。基于用户已有的信息直接给方案是首选体验。
- followup_question 是**可选**的"温柔询问"，会被追加在方案末尾（不会阻塞回答）。
- 只有当**完全无法判断方向**时（例如用户只说"我想变美"）才填 followup_question。
- 如果填，**只问一个最关键的问题**（一句话），绝不一次问多个。
- 已经有基础诉求（如"鼻子塌"、"脸上有斑"）就**不要再追问**，直接走方案。

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
    "followup_question": ""或"一句话最关键的追问"
}"""


async def intake_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    trace = config["configurable"].get("trace")
    span = create_span(trace, "intake", state["user_message"])
    llm = get_llm_client()

    user_msg = state["user_message"]
    history = state.get("history", [])
    rounds_done = _assistant_turns(history)

    # Path 1: bypass phrase — skip LLM entirely, go straight to recommend.
    if _is_bypass(user_msg):
        logger.info("Intake bypass: user signal detected, skipping intake LLM")
        end_span(span, {"bypass": True, "rounds_done": rounds_done})
        return {
            **state,
            "intent": "方案推荐",
            "profile_complete": True,
            "followup_hint": "",
        }

    messages = [
        {"role": "system", "content": INTAKE_PROMPT},
    ]
    for msg in history:
        messages.append(msg)
    messages.append({"role": "user", "content": user_msg})

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
            "followup_hint": "",
        }

    profile = state.get("user_profile", {})
    new_profile = result.get("profile", {})
    for k, v in new_profile.items():
        if v is not None and v != [] and v != "":
            profile[k] = v

    intent = result.get("intent", "科普")
    followup = (result.get("followup_question") or "").strip()

    # Path 2: already asked once — suppress further followups even if LLM proposes one.
    if rounds_done >= 1 and followup:
        logger.info("Intake round cap reached, dropping followup question")
        followup = ""

    end_span(span, {"intent": intent, "rounds_done": rounds_done, "has_followup": bool(followup)})
    return {
        **state,
        "intent": intent,
        "user_profile": profile,
        "profile_complete": True,  # always continue to recommend
        "followup_hint": followup,
    }
