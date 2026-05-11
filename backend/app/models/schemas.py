from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str
