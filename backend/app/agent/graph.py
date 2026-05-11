from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.state import ConsultState
from app.agent.nodes.intake import intake_node
from app.agent.nodes.safety_gate import safety_gate_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.risk_assessment import risk_assessment_node
from app.agent.nodes.recommend import recommend_node
from app.core.logging import get_logger

logger = get_logger("agent.graph")


def _route_after_intake(state: ConsultState) -> str:
    if not state.get("profile_complete", True):
        return END
    if state.get("intent") == "闲聊":
        return "recommend"
    return "safety_gate"


def _route_after_safety(state: ConsultState) -> str:
    if state.get("blocked", False):
        return END
    return "retrieve"


def build_graph():
    graph = StateGraph(ConsultState)

    graph.add_node("intake", intake_node)
    graph.add_node("safety_gate", safety_gate_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("risk_assessment", risk_assessment_node)
    graph.add_node("recommend", recommend_node)

    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", _route_after_intake, {END: END, "safety_gate": "safety_gate", "recommend": "recommend"})
    graph.add_conditional_edges("safety_gate", _route_after_safety, {END: END, "retrieve": "retrieve"})
    graph.add_edge("retrieve", "risk_assessment")
    graph.add_edge("risk_assessment", "recommend")
    graph.add_edge("recommend", END)

    return graph.compile()


_GRAPH = build_graph()


async def run_agent(user_message: str, db: AsyncSession, session_id: str = "", history: list[dict] | None = None) -> ConsultState:
    """Run the full agent pipeline."""
    initial_state: ConsultState = {
        "user_message": user_message,
        "session_id": session_id,
        "history": history or [],
        "intent": None,
        "user_profile": {},
        "profile_complete": False,
        "retrieved_docs": [],
        "risk_flags": [],
        "response": "",
        "llm_messages": [],
        "citations": [],
        "needs_disclaimer": False,
        "blocked": False,
        "block_reason": "",
    }

    return await _GRAPH.ainvoke(
        initial_state,
        config={"configurable": {"db": db}},
    )
