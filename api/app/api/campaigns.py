from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_campaign_access, require_merchant_access
from app.models.entities import Campaign, User
from app.schemas.contracts import (
    ActivityEntry,
    AgentEndpoints,
    CampaignAgentKeyResponse,
    CampaignCreateRequest,
    CampaignOverview,
    CampaignUpdateRequest,
    ProductPerformanceRow,
    TimeSeriesPoint,
)
from app.services.analytics import (
    build_activity_feed,
    build_metric_series,
    build_product_rows,
    compute_campaign_overview,
)
from app.services.listener import ensure_campaign_api_key


router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("/create", response_model=CampaignOverview)
def create_campaign(
    payload: CampaignCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CampaignOverview:
    merchant = require_merchant_access(db, payload.merchant_id, current_user)
    plaintext_api_key: str | None = None
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.user_id == current_user.id,
            Campaign.merchant_id == merchant.id,
        )
    )
    if campaign is None:
        campaign = Campaign(
            merchant_id=merchant.id,
            user_id=current_user.id,
            budget_monthly=payload.budget_monthly,
            auto_optimize=payload.auto_optimize,
            status="pending_payment",
        )
        plaintext_api_key = ensure_campaign_api_key(campaign)
        db.add(campaign)
    else:
        campaign.budget_monthly = payload.budget_monthly
        campaign.auto_optimize = payload.auto_optimize
        if campaign.status == "paused":
            campaign.status = "pending_payment"
        plaintext_api_key = ensure_campaign_api_key(campaign)

    db.commit()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    return CampaignOverview.model_validate(
        compute_campaign_overview(db, campaign, agent_api_key_plaintext=plaintext_api_key)
    )


@router.get("/{campaign_id}", response_model=CampaignOverview)
def get_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CampaignOverview:
    campaign = require_campaign_access(db, campaign_id, current_user)
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    return CampaignOverview.model_validate(compute_campaign_overview(db, campaign))


@router.get("/{campaign_id}/endpoints", response_model=AgentEndpoints)
def get_campaign_endpoints(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentEndpoints:
    campaign = require_campaign_access(db, campaign_id, current_user)
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    overview = compute_campaign_overview(db, campaign)
    return AgentEndpoints.model_validate(overview["agent_endpoints"])


@router.post("/{campaign_id}/agent-key/regenerate", response_model=CampaignAgentKeyResponse)
def regenerate_campaign_agent_key(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CampaignAgentKeyResponse:
    campaign = require_campaign_access(db, campaign_id, current_user)
    plaintext_api_key = ensure_campaign_api_key(campaign, regenerate=True)
    db.commit()
    return CampaignAgentKeyResponse(
        api_key=plaintext_api_key,
        api_key_preview=f"ek_live_****{plaintext_api_key[-4:]}",
    )


@router.get("/{campaign_id}/metrics", response_model=list[TimeSeriesPoint])
def get_campaign_metrics(
    campaign_id: str,
    period: str = "30d",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TimeSeriesPoint]:
    require_campaign_access(db, campaign_id, current_user)
    return [TimeSeriesPoint.model_validate(point) for point in build_metric_series(db, campaign_id, period)]


@router.get("/{campaign_id}/products", response_model=list[ProductPerformanceRow])
def get_campaign_products(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductPerformanceRow]:
    campaign = require_campaign_access(db, campaign_id, current_user)
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    return [ProductPerformanceRow.model_validate(row) for row in build_product_rows(db, campaign)]


@router.get("/{campaign_id}/activity", response_model=list[ActivityEntry])
def get_campaign_activity(
    campaign_id: str,
    limit: int = 50,
    event_type: str = "all",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityEntry]:
    require_campaign_access(db, campaign_id, current_user)
    return [
        ActivityEntry.model_validate(entry)
        for entry in build_activity_feed(db, campaign_id, limit=limit, event_type=event_type)
    ]


@router.put("/{campaign_id}", response_model=CampaignOverview)
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CampaignOverview:
    campaign = require_campaign_access(db, campaign_id, current_user)
    if payload.budget_monthly is not None:
        campaign.budget_monthly = payload.budget_monthly
    if payload.status is not None:
        campaign.status = payload.status
    if payload.auto_optimize is not None:
        campaign.auto_optimize = payload.auto_optimize
    db.commit()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    return CampaignOverview.model_validate(compute_campaign_overview(db, campaign))
