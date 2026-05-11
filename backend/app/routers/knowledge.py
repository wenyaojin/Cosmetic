import json
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.rag import ingest_document, search_similar
from app.core.logging import get_logger
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = get_logger("knowledge")


class IngestRequest(BaseModel):
    title: str
    content: str
    source: str = ""
    category: str = "general"
    authority_level: int = 4


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    category: str | None = None


@router.post("/ingest")
async def ingest(req: IngestRequest, db: AsyncSession = Depends(get_db)):
    """Ingest a document into the knowledge base."""
    doc_id = await ingest_document(
        db=db,
        title=req.title,
        content=req.content,
        source=req.source,
        category=req.category,
        authority_level=req.authority_level,
    )
    return {"doc_id": str(doc_id), "message": f"Document '{req.title}' ingested successfully"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("general"),
    authority_level: int = Form(4),
    source: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file (txt/md) and ingest into the knowledge base."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    raw = await file.read()
    content = raw.decode("utf-8", errors="ignore")
    title = file.filename.rsplit(".", 1)[0]

    doc_id = await ingest_document(
        db=db,
        title=title,
        content=content,
        source=source or file.filename,
        category=category,
        authority_level=authority_level,
    )
    return {"doc_id": str(doc_id), "message": f"File '{file.filename}' ingested successfully"}


@router.post("/search")
async def search(req: SearchRequest, db: AsyncSession = Depends(get_db)):
    """Search the knowledge base by semantic similarity."""
    results = await search_similar(
        db=db,
        query=req.query,
        top_k=req.top_k,
        category=req.category,
    )
    return {"query": req.query, "results": results}
