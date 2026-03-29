from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    get_current_user,
    get_db,
    require_campaign_access,
)
from app.models.entities import Campaign, Merchant, User
from app.schemas.contracts import (
    OpenClawConfigResponse,
    OpenClawSkillBundleResponse,
)
from app.services.listener import ensure_campaign_api_key
from app.services.openclaw_runtime import build_openclaw_skill_bundle


router = APIRouter(prefix="/api/campaigns", tags=["agent-runtime"])


def load_campaign_with_products(db: Session, campaign_id: str) -> Campaign:
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(joinedload(Campaign.merchant).selectinload(Merchant.products))
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/{campaign_id}/openclaw-skill", response_model=OpenClawSkillBundleResponse)
def get_campaign_openclaw_skill_bundle(
    campaign_id: str,
    format: Literal["skill", "config", "bundle"] = "skill",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OpenClawSkillBundleResponse | OpenClawConfigResponse | PlainTextResponse:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_campaign_with_products(db, campaign_id)
    api_key = ensure_campaign_api_key(campaign)
    db.commit()
    db.refresh(campaign)
    bundle = build_openclaw_skill_bundle(campaign, api_key)
    if format == "skill":
        return PlainTextResponse(
            content=bundle["skill_markdown"],
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{bundle["file_name"]}"',
            },
        )
    if format == "config":
        return JSONResponse(
            content=bundle["config_json"],
            headers={
                "Content-Disposition": f'attachment; filename="{bundle["config_file_name"]}"',
            },
        )
    return OpenClawSkillBundleResponse.model_validate(bundle)
