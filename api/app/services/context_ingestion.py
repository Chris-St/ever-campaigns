from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.models.entities import Campaign, CampaignContextItem


UPLOAD_ROOT = BASE_DIR / ".runtime" / "campaign-context"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    return cleaned.strip("-") or "context-file"


def truncate_text(value: str, limit: int = 8_000) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def summarize_context_text(title: str, content: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    summary = " ".join(sentence for sentence in sentences[:3] if sentence.strip())
    if not summary:
        summary = truncate_text(content, 220)
    return truncate_text(f"{title}: {summary}".strip(), 260)


def extract_text_from_pdf(raw_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(raw_bytes))
    pages = []
    for page in reader.pages[:20]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n".join(pages)


def extract_text_from_upload(filename: str, content_type: str | None, raw_bytes: bytes) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        try:
            return extract_text_from_pdf(raw_bytes)
        except Exception:
            return ""
    if lower_name.endswith((".json", ".jsonl")):
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
            return json.dumps(parsed, indent=2)
        except Exception:
            return raw_bytes.decode("utf-8", errors="ignore")
    return raw_bytes.decode("utf-8", errors="ignore")


def build_storage_path(campaign_id: str, filename: str) -> Path:
    campaign_dir = UPLOAD_ROOT / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    return campaign_dir / f"{uuid4().hex[:12]}-{sanitize_filename(filename)}"


def serialize_context_item(item: CampaignContextItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "campaign_id": item.campaign_id,
        "kind": item.kind,
        "title": item.title,
        "source_name": item.source_name,
        "mime_type": item.mime_type,
        "content_text": item.content_text,
        "summary": item.summary,
        "storage_path": item.storage_path,
        "details": item.details or {},
        "created_at": item.created_at.isoformat(),
    }


def list_context_items(db: Session, campaign_id: str) -> list[CampaignContextItem]:
    return db.scalars(
        select(CampaignContextItem)
        .where(CampaignContextItem.campaign_id == campaign_id)
        .order_by(CampaignContextItem.created_at.desc())
    ).all()


def build_context_seed_summary(db: Session, campaign_id: str) -> tuple[str, list[dict[str, Any]]]:
    items = list_context_items(db, campaign_id)
    if not items:
        return (
            "No seeded context uploaded yet. Work from the catalog, agent brain, and memory until the operator adds more context.",
            [],
        )
    recent_items = []
    for item in items[:6]:
        serialized = serialize_context_item(item)
        serialized["content_text"] = truncate_text(serialized["content_text"], 4_000)
        recent_items.append(serialized)
    summary_bits = [
        f"{len(items)} seeded context item{'s' if len(items) != 1 else ''}",
        *(str(item.get("summary")) for item in recent_items[:3] if item.get("summary")),
    ]
    return " | ".join(summary_bits), recent_items


def create_text_context_item(
    db: Session,
    campaign: Campaign,
    *,
    title: str,
    content: str,
    kind: str = "note",
    source_name: str | None = None,
    mime_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> CampaignContextItem:
    cleaned_content = truncate_text(content, 24_000)
    if not cleaned_content.strip():
        raise ValueError("Context content cannot be empty")
    item = CampaignContextItem(
        campaign_id=campaign.id,
        kind=kind,
        title=title.strip() or "Context note",
        source_name=source_name,
        mime_type=mime_type,
        content_text=cleaned_content,
        summary=summarize_context_text(title.strip() or "Context note", cleaned_content),
        details=details or {},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


async def create_file_context_item(
    db: Session,
    campaign: Campaign,
    upload: UploadFile,
) -> CampaignContextItem:
    raw_bytes = await upload.read()
    if not raw_bytes:
        raise ValueError("Uploaded file was empty")
    storage_path = build_storage_path(campaign.id, upload.filename or "context-upload")
    storage_path.write_bytes(raw_bytes)
    extracted_text = truncate_text(
        extract_text_from_upload(upload.filename or storage_path.name, upload.content_type, raw_bytes),
        24_000,
    )
    if not extracted_text.strip():
        extracted_text = "The file was uploaded successfully, but Ever could not extract readable text from it yet."
    item = CampaignContextItem(
        campaign_id=campaign.id,
        kind="file",
        title=(upload.filename or storage_path.name).strip(),
        source_name=upload.filename,
        mime_type=upload.content_type,
        content_text=extracted_text,
        summary=summarize_context_text(upload.filename or "Uploaded file", extracted_text),
        storage_path=str(storage_path),
        details={"size_bytes": len(raw_bytes)},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
