from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.services.rag import search_hybrid
from app.core.logging import get_logger
from app.core.observe import create_span, end_span

logger = get_logger("agent.retrieve")


async def retrieve_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    trace = config["configurable"].get("trace")
    span = create_span(trace, "retrieve", state["user_message"])
    db = config["configurable"]["db"]

    query = state["user_message"]

    concerns = state.get("user_profile", {}).get("concerns", [])
    if concerns:
        query = f"{query} {' '.join(concerns)}"

    docs = await search_hybrid(db, query, top_k=5)
    logger.info("Retrieved %d docs for query: %s", len(docs), query[:80])

    end_span(span, {"doc_count": len(docs)})
    return {**state, "retrieved_docs": docs}
