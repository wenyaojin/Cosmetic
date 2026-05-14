from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.core.logging import get_logger
from app.core.observe import create_span, end_span

logger = get_logger("agent.safety")

BLOCKED_INTENTS = {"拒答"}

DIAGNOSIS_KEYWORDS = [
    "帮我诊断", "我是不是得了", "帮我看看是什么病",
    "开个处方", "开点药", "该吃什么药",
    "能治好吗", "能治愈吗", "保证效果",
]

REFUSAL_RESPONSE = (
    "抱歉，您的问题涉及具体医疗诊断或处方，这超出了我的能力范围。"
    "建议您前往正规医疗机构，由执业医师进行面诊评估。\n\n"
    "本回答仅供科普参考，不构成医疗建议。"
)


async def safety_gate_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    trace = config["configurable"].get("trace")
    span = create_span(trace, "safety_gate", state.get("user_message"))

    if state.get("intent") in BLOCKED_INTENTS:
        end_span(span, {"blocked": True, "reason": "intent_blocked"})
        return {
            **state,
            "blocked": True,
            "block_reason": "intent_blocked",
            "response": REFUSAL_RESPONSE,
        }

    msg = state.get("user_message", "")
    for kw in DIAGNOSIS_KEYWORDS:
        if kw in msg:
            logger.info("Safety gate blocked: keyword '%s'", kw)
            end_span(span, {"blocked": True, "reason": f"keyword:{kw}"})
            return {
                **state,
                "blocked": True,
                "block_reason": f"keyword:{kw}",
                "response": REFUSAL_RESPONSE,
            }

    end_span(span, {"blocked": False})
    return {**state, "blocked": False}
