from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile
import httpx
from pypdf import PdfReader
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.core.config import settings
from app.models.entities import Campaign, CampaignContextItem


UPLOAD_ROOT = BASE_DIR / ".runtime" / "campaign-context"
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".mpeg", ".wav", ".webm", ".ogg"}
SOCIAL_HOSTS = {
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "www.tiktok.com": "tiktok",
    "twitter.com": "x",
    "www.twitter.com": "x",
    "x.com": "x",
    "www.x.com": "x",
    "reddit.com": "reddit",
    "www.reddit.com": "reddit",
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "www.facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
    "pinterest.com": "pinterest",
    "www.pinterest.com": "pinterest",
}


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


def normalize_context_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        raise ValueError("Context URL cannot be empty")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        raise ValueError("That URL does not look valid yet.")
    return candidate


def detect_platform(url: str) -> str | None:
    hostname = (urlparse(url).hostname or "").lower()
    return SOCIAL_HOSTS.get(hostname)


def extract_text_from_html(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (
        soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    )
    title_text = (
        title.get("content", "").strip() if title and title.get("content") else (soup.title.string.strip() if soup.title and soup.title.string else None)
    )
    description_tag = (
        soup.find("meta", property="og:description")
        or soup.find("meta", attrs={"name": "description"})
        or soup.find("meta", attrs={"name": "twitter:description"})
    )
    description_text = description_tag.get("content", "").strip() if description_tag else ""

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    fragments: list[str] = []
    seen: set[str] = set()
    for node in soup.select("h1, h2, h3, p, li, blockquote"):
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text or len(text) < 24:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        fragments.append(text)
        if len(" ".join(fragments)) > 12_000:
            break

    narrative = truncate_text(" ".join(fragments), 12_000)
    sections = []
    if title_text:
        sections.append(f"Page title: {title_text}")
    if description_text:
        sections.append(f"Meta description: {description_text}")
    if narrative:
        sections.append(f"Extracted page text: {narrative}")
    return title_text, "\n\n".join(section for section in sections if section).strip()


def fetch_url_context(url: str) -> dict[str, Any]:
    normalized_url = normalize_context_url(url)
    platform = detect_platform(normalized_url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
    }
    with httpx.Client(follow_redirects=True, timeout=20.0, headers=headers) as client:
        response = client.get(normalized_url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    final_url = str(response.url)
    if "html" in content_type or not content_type:
        title, extracted_text = extract_text_from_html(response.text)
    else:
        title = None
        extracted_text = truncate_text(response.text, 12_000)
    if not extracted_text.strip():
        extracted_text = "Ever reached this URL but could not extract useful readable text from it yet."
    return {
        "url": final_url,
        "platform": platform,
        "title": title or (urlparse(final_url).hostname or "Imported URL"),
        "content_type": content_type or None,
        "content_text": truncate_text(extracted_text, 24_000),
    }


def require_openai_key() -> str:
    if not settings.openai_api_key:
        raise ValueError("Voice-note transcription requires OPENAI_API_KEY in api/.env.")
    return settings.openai_api_key


def transcribe_audio_bytes(filename: str, raw_bytes: bytes, mime_type: str | None = None) -> str:
    api_key = require_openai_key()
    files = {
        "file": (
            filename or "voice-note.webm",
            raw_bytes,
            mime_type or "application/octet-stream",
        )
    }
    data = {
        "model": settings.openai_transcription_model,
    }
    response = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        data=data,
        files=files,
        timeout=90.0,
    )
    response.raise_for_status()
    payload = response.json()
    transcript = str(payload.get("text") or "").strip()
    if not transcript:
        raise ValueError("OpenAI did not return a transcript for this voice note.")
    return transcript


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


def create_url_context_item(
    db: Session,
    campaign: Campaign,
    *,
    url: str,
    title: str | None = None,
    kind: str = "social_profile",
) -> CampaignContextItem:
    fetched = fetch_url_context(url)
    resolved_kind = kind if kind != "social_profile" or fetched["platform"] else "url"
    resolved_title = (title or fetched["title"] or "Imported URL").strip()
    details = {
        "url": fetched["url"],
        "platform": fetched["platform"],
        "content_type": fetched["content_type"],
    }
    item = CampaignContextItem(
        campaign_id=campaign.id,
        kind=resolved_kind,
        title=resolved_title,
        source_name=fetched["url"],
        mime_type=fetched["content_type"],
        content_text=fetched["content_text"],
        summary=summarize_context_text(resolved_title, fetched["content_text"]),
        details={key: value for key, value in details.items() if value},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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


async def create_voice_context_item(
    db: Session,
    campaign: Campaign,
    upload: UploadFile,
) -> CampaignContextItem:
    raw_bytes = await upload.read()
    if not raw_bytes:
        raise ValueError("Voice note was empty")
    suffix = Path(upload.filename or "voice-note.webm").suffix.lower()
    if upload.content_type and not upload.content_type.startswith("audio/") and suffix not in AUDIO_EXTENSIONS:
        raise ValueError("Voice note upload must be an audio file")
    storage_path = build_storage_path(campaign.id, upload.filename or "voice-note.webm")
    storage_path.write_bytes(raw_bytes)
    transcript = truncate_text(
        transcribe_audio_bytes(upload.filename or storage_path.name, raw_bytes, upload.content_type),
        24_000,
    )
    title = (upload.filename or "Voice note").strip()
    item = CampaignContextItem(
        campaign_id=campaign.id,
        kind="voice_note",
        title=title,
        source_name=upload.filename,
        mime_type=upload.content_type,
        content_text=transcript,
        summary=summarize_context_text(title, transcript),
        storage_path=str(storage_path),
        details={
            "size_bytes": len(raw_bytes),
            "transcription_model": settings.openai_transcription_model,
        },
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
