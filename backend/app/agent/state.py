from typing import TypedDict, Literal, Annotated
from operator import add


class UserProfile(TypedDict, total=False):
    age: int | None
    gender: str | None
    skin_type: str | None
    budget: str | None
    allergies: list[str]
    contraindications: list[str]
    concerns: list[str]
    prior_treatments: list[str]


class Citation(TypedDict):
    index: int
    title: str
    source: str


class ConsultState(TypedDict, total=False):
    user_message: str
    session_id: str
    history: list[dict]

    intent: Literal["科普", "项目咨询", "方案推荐", "术后护理", "闲聊", "拒答"] | None
    user_profile: UserProfile
    profile_complete: bool

    retrieved_docs: list[dict]
    risk_flags: list[str]

    response: str
    llm_messages: list[dict]
    citations: list[Citation]
    needs_disclaimer: bool
    blocked: bool
    block_reason: str
