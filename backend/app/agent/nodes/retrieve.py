from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.services.rag import search_similar
from app.core.logging import get_logger

logger = get_logger("agent.retrieve")


async def retrieve_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    db = config["configurable"]["db"]

    query = state["user_message"]

    concerns = state.get("user_profile", {}).get("concerns", [])
    if concerns:
        query = f"{query} {' '.join(concerns)}"

    docs = await search_similar(db, query, top_k=5)
    logger.info("Retrieved %d docs for query: %s", len(docs), query[:80])

    return {**state, "retrieved_docs": docs}
