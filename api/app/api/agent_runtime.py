from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.core.security import verify_api_key
from app.models.entities import Campaign, Merchant
from app.schemas.contracts import (
    AgentConfigResponse,
    AgentEventRequest,
    AgentEventResponse,
)
from app.services.listener import build_agent_config, record_agent_event


router = APIRouter(prefix="/api/campaigns", tags=["agent-runtime"])


def get_agent_campaign(
    campaign_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Campaign:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing campaign API key",
        )
    api_key = authorization.split(" ", 1)[1].strip()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(joinedload(Campaign.merchant).selectinload(Merchant.products))
    )
    if campaign is None or not verify_api_key(api_key, campaign.listener_api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid campaign API key",
        )
    return campaign


@router.get("/{campaign_id}/agent-config", response_model=AgentConfigResponse)
def get_campaign_agent_config(
    campaign: Campaign = Depends(get_agent_campaign),
    db: Session = Depends(get_db),
) -> AgentConfigResponse:
    payload = build_agent_config(campaign)
    db.commit()
    return AgentConfigResponse.model_validate(payload)


@router.post("/{campaign_id}/events", response_model=AgentEventResponse)
def post_campaign_agent_event(
    payload: AgentEventRequest,
    campaign: Campaign = Depends(get_agent_campaign),
    db: Session = Depends(get_db),
) -> AgentEventResponse:
    result = record_agent_event(db, campaign, payload.model_dump())
    return AgentEventResponse.model_validate(result)
