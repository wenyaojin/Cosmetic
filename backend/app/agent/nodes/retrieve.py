from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.services.rag import search_enhanced
from app.services.structured_kb import find_relevant_cards, card_to_context
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

    docs = await search_enhanced(db, query, top_k=5, trace=trace)
    logger.info("Retrieved %d docs for query: %s", len(docs), query[:80])

    cards = await find_relevant_cards(db, query, limit=3)
    if cards:
        card_contexts = [card_to_context(c) for c in cards]
        logger.info("Matched %d structured project cards", len(cards))
    else:
        card_contexts = []

    end_span(span, {"doc_count": len(docs), "card_count": len(cards)})
    return {
        **state,
        "retrieved_docs": docs,
        "project_cards": card_contexts,
    }

