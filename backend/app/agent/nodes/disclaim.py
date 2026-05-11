from app.agent.state import ConsultState

DISCLAIMER = "\n\n---\n*本回答仅供科普参考，不构成医疗建议。任何医美项目请前往正规医疗机构面诊评估。*"


async def disclaim_node(state: ConsultState) -> ConsultState:
    response = state.get("response", "")
    if state.get("needs_disclaimer", False) and DISCLAIMER.strip() not in response:
        response += DISCLAIMER
    return {**state, "response": response}
