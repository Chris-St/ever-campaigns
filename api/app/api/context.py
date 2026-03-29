from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_campaign_access
from app.models.entities import User
from app.schemas.contracts import ContextItemRecord, ContextNoteRequest
from app.services.context_ingestion import (
    create_file_context_item,
    create_text_context_item,
    list_context_items,
    serialize_context_item,
)


router = APIRouter(prefix="/campaigns", tags=["context"])


@router.get("/{campaign_id}/context", response_model=list[ContextItemRecord])
def get_campaign_context(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContextItemRecord]:
    campaign = require_campaign_access(db, campaign_id, current_user)
    return [ContextItemRecord.model_validate(serialize_context_item(item)) for item in list_context_items(db, campaign.id)]


@router.post("/{campaign_id}/context/notes", response_model=ContextItemRecord)
def create_campaign_context_note(
    campaign_id: str,
    payload: ContextNoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContextItemRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        item = create_text_context_item(
            db,
            campaign,
            title=payload.title,
            content=payload.content,
            kind=payload.kind,
            details={"source": "operator"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContextItemRecord.model_validate(serialize_context_item(item))


@router.post("/{campaign_id}/context/upload", response_model=ContextItemRecord)
async def upload_campaign_context_file(
    campaign_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContextItemRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        item = await create_file_context_item(db, campaign, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContextItemRecord.model_validate(serialize_context_item(item))
