"""
Batch ingest Markdown/text documents from a folder into the knowledge base.

Supports optional YAML frontmatter for metadata:

    ---
    title: 玻尿酸品牌对比
    category: projects
    authority_level: 2
    source: 中华医学会指南
    ---

    正文内容...

Files without frontmatter use the filename (without extension) as title.

Usage:
    cd Q:/Cosmetic/backend
    python -m scripts.batch_ingest <folder_path> [--category general] [--authority-level 4] [--source ""] [--dry-run]

Examples:
    python -m scripts.batch_ingest ../knowledge/注射填充 --category projects --authority-level 2
    python -m scripts.batch_ingest ../knowledge --dry-run
"""
import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import yaml
from sqlalchemy import text

from app.core.database import get_engine, get_session_factory, Base
from app.services.rag import ingest_document
from app.core.logging import get_logger

logger = get_logger("batch_ingest")

SUPPORTED_EXTENSIONS = {".md", ".txt"}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a document."""
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, text

    return meta, parts[2].strip()


def parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def source_from_meta(meta: dict, default_source: str) -> str:
    source = meta.get("source") or meta.get("source_doc") or default_source
    source_url = meta.get("source_url")
    if source and source_url:
        return f"{source} | {source_url}"
    return source_url or source or ""


def metadata_from_frontmatter(meta: dict, file_path: Path) -> dict:
    metadata = {k: normalize_metadata_value(v) for k, v in meta.items()}
    metadata.setdefault("file_path", str(file_path))
    metadata.setdefault("source_url", meta.get("source_url", ""))
    metadata.setdefault("nmpa_status", meta.get("nmpa_status", ""))
    metadata.setdefault("nmpa_no", meta.get("nmpa_no", ""))
    metadata.setdefault("sub_category", meta.get("sub_category", ""))
    metadata.setdefault("tags", meta.get("tags", []))
    metadata.setdefault("compliance_review", meta.get("compliance_review", "pending"))
    return metadata


def normalize_metadata_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_metadata_value(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_metadata_value(v) for k, v in value.items()}
    return value


def collect_files(folder: Path) -> list[Path]:
    """Recursively collect all supported files, sorted by name."""
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(folder.rglob(f"*{ext}"))
    return sorted(files)


async def ingest_file(
    db,
    file_path: Path,
    default_category: str,
    default_authority: int,
    default_source: str,
) -> dict:
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    meta, body = parse_frontmatter(raw)

    if not body.strip():
        return {"file": str(file_path), "status": "skipped", "reason": "empty content"}

    title = meta.get("title", file_path.stem)
    category = meta.get("category", default_category)
    authority_level = meta.get("authority_level", default_authority)
    source = source_from_meta(meta, default_source or file_path.name)
    metadata = metadata_from_frontmatter(meta, file_path)
    published_at = parse_date(meta.get("published_at") or meta.get("last_updated"))

    existing_id = await find_existing_document(db, metadata)
    if existing_id:
        return {"file": str(file_path), "status": "skipped", "reason": f"already ingested: {existing_id}"}

    doc_id = await ingest_document(
        db=db,
        title=title,
        content=body,
        source=source,
        category=category,
        authority_level=authority_level,
        published_at=published_at,
        metadata=metadata,
    )
    return {"file": str(file_path), "status": "ingested", "doc_id": str(doc_id), "title": title}


async def find_existing_document(db, metadata: dict) -> str | None:
    pmid = metadata.get("pmid")
    source_url = metadata.get("source_url")
    if not pmid and not source_url:
        return None

    clauses = []
    params = {}
    if pmid:
        clauses.append("metadata ->> 'pmid' = :pmid")
        params["pmid"] = str(pmid)
    if source_url:
        clauses.append("metadata ->> 'source_url' = :source_url")
        params["source_url"] = str(source_url)

    sql = "SELECT id FROM documents WHERE " + " OR ".join(clauses) + " LIMIT 1"
    result = await db.execute(text(sql), params)
    doc_id = result.scalar_one_or_none()
    return str(doc_id) if doc_id else None


async def main():
    parser = argparse.ArgumentParser(description="Batch ingest documents into knowledge base")
    parser.add_argument("folder", type=str, help="Path to folder containing .md/.txt files")
    parser.add_argument("--category", default="general", help="Default category (default: general)")
    parser.add_argument("--authority-level", type=int, default=4, help="Default authority level 1-4 (default: 4)")
    parser.add_argument("--source", default="", help="Default source label")
    parser.add_argument("--dry-run", action="store_true", help="List files without ingesting")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory")
        sys.exit(1)

    files = collect_files(folder)
    if not files:
        print(f"No .md/.txt files found in '{folder}'")
        sys.exit(0)

    print(f"Found {len(files)} file(s) in '{folder}'")

    if args.dry_run:
        for f in files:
            raw = f.read_text(encoding="utf-8", errors="ignore")
            meta, body = parse_frontmatter(raw)
            title = meta.get("title", f.stem)
            chars = len(body.strip())
            print(f"  {f.relative_to(folder)}  →  title='{title}'  chars={chars}")
        print(f"\nDry run complete. Use without --dry-run to ingest.")
        return

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    success = 0
    skipped = 0
    failed = 0

    async with factory() as db:
        for f in files:
            try:
                result = await ingest_file(db, f, args.category, args.authority_level, args.source)
                if result["status"] == "ingested":
                    success += 1
                    print(f"  ✓ {f.name} → '{result['title']}'")
                else:
                    skipped += 1
                    print(f"  - {f.name} (skipped: {result['reason']})")
            except Exception as e:
                failed += 1
                print(f"  ✗ {f.name} → error: {e}")
                logger.error("Failed to ingest %s: %s", f, e, exc_info=True)

    print(f"\nDone: {success} ingested, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
