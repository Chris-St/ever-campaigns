from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user, get_db, require_campaign_access
from app.models.entities import Campaign, Merchant, User
from app.schemas.contracts import (
    ListenerAnalytics,
    ListenerConfigUpdateRequest,
    ListenerStatus,
    ReviewQueueItem,
    ReviewResponseEditRequest,
)
from app.services.listener import (
    approve_response,
    build_listener_analytics,
    build_listener_status,
    edit_response,
    reject_response,
    review_queue,
    start_listener,
    stop_listener,
    update_listener_config,
)


router = APIRouter(prefix="/campaigns", tags=["listener"])


def load_listener_campaign(db: Session, campaign_id: str) -> Campaign | None:
    return db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(joinedload(Campaign.merchant).selectinload(Merchant.products))
    )


@router.post("/{campaign_id}/listener/start", response_model=ListenerStatus)
def start_campaign_listener(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListenerStatus:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return ListenerStatus.model_validate(start_listener(db, campaign))


@router.post("/{campaign_id}/listener/stop", response_model=ListenerStatus)
def stop_campaign_listener(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListenerStatus:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return ListenerStatus.model_validate(stop_listener(db, campaign))


@router.get("/{campaign_id}/listener/status", response_model=ListenerStatus)
def get_campaign_listener_status(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListenerStatus:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return ListenerStatus.model_validate(build_listener_status(db, campaign))


@router.put("/{campaign_id}/listener/config", response_model=ListenerStatus)
def put_campaign_listener_config(
    campaign_id: str,
    payload: ListenerConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListenerStatus:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return ListenerStatus.model_validate(update_listener_config(db, campaign, payload.model_dump(exclude_none=True)))


@router.get("/{campaign_id}/review", response_model=list[ReviewQueueItem])
def get_campaign_review_queue(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewQueueItem]:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return [ReviewQueueItem.model_validate(item) for item in review_queue(db, campaign)]


@router.post("/{campaign_id}/review/{response_id}/approve", response_model=ReviewQueueItem)
def approve_campaign_response(
    campaign_id: str,
    response_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewQueueItem:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        return ReviewQueueItem.model_validate(approve_response(db, campaign, response_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{campaign_id}/review/{response_id}/reject", response_model=ReviewQueueItem)
def reject_campaign_response(
    campaign_id: str,
    response_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewQueueItem:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        return ReviewQueueItem.model_validate(reject_response(db, campaign, response_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{campaign_id}/review/{response_id}/edit", response_model=ReviewQueueItem)
def edit_campaign_response(
    campaign_id: str,
    response_id: str,
    payload: ReviewResponseEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewQueueItem:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        return ReviewQueueItem.model_validate(edit_response(db, campaign, response_id, payload.response_text))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{campaign_id}/listener/analytics", response_model=ListenerAnalytics)
def get_campaign_listener_analytics(
    campaign_id: str,
    period: str = "7d",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListenerAnalytics:
    require_campaign_access(db, campaign_id, current_user)
    campaign = load_listener_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return ListenerAnalytics.model_validate(build_listener_analytics(db, campaign, period=period))
