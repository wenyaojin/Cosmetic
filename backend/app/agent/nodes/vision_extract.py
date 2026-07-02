from langchain_core.runnables import RunnableConfig
from app.agent.state import ConsultState
from app.core.logging import get_logger
from app.core.observe import create_span, end_span
from app.services.vision import extract_visual_features

logger = get_logger("agent.vision_extract")


async def vision_extract_node(state: ConsultState, config: RunnableConfig) -> ConsultState:
    """Run V2 vision extraction if the user uploaded an image; otherwise pass through.

    Vision failure is non-fatal: visual_features stays None and downstream nodes
    operate on the text-only path.
    """
    image = state.get("user_image")
    if not image:
        return state

    trace = config["configurable"].get("trace")
    span = create_span(trace, "vision_extract")

    features = await extract_visual_features(image)

    if features is None:
        logger.info("vision_extract: VLM returned None, continuing text-only")
        end_span(span, {"vision_used": False})
        return {**state, "visual_features": None}

    end_span(span, {
        "vision_used": True,
        "top_layer": features.get("top_layer"),
        "top_feature": features.get("top_feature"),
        "latency_sec": features.get("latency_sec"),
    })
    return {**state, "visual_features": features}
