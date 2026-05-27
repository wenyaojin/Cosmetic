import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ProjectCard(Base):
    """
    Structured fact card for a cosmetic-medicine project (e.g., 玻尿酸填充).

    Factual queries (price, duration, contraindications) are answered from
    this table directly, bypassing RAG to avoid hallucination.
    """

    __tablename__ = "project_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    category: Mapped[str] = mapped_column(String(50), default="general", index=True)

    indications: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    contraindications: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    complications: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    duration_months_min: Mapped[int | None] = mapped_column(nullable=True)
    duration_months_max: Mapped[int | None] = mapped_column(nullable=True)
    price_rmb_min: Mapped[int | None] = mapped_column(nullable=True)
    price_rmb_max: Mapped[int | None] = mapped_column(nullable=True)
    recovery_days: Mapped[str | None] = mapped_column(String(64), nullable=True)

    description: Mapped[str] = mapped_column(Text, default="")
    source_doc_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
