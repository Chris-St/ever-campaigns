from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_campaign_access
from app.models.entities import Campaign, User
from app.schemas.contracts import BillingCheckoutRequest, BillingCheckoutResponse
from app.services.seeding import seed_campaign_activity


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-checkout", response_model=BillingCheckoutResponse)
def create_checkout(
    payload: BillingCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingCheckoutResponse:
    campaign = require_campaign_access(db, payload.campaign_id, current_user)
    campaign.status = "active"
    db.commit()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    seed_campaign_activity(db, campaign)
    return BillingCheckoutResponse(
        mode="demo",
        campaign_id=campaign.id,
        activated=True,
        message="Campaign activated in demo billing mode. Stripe hooks can replace this flow later.",
        checkout_url=None,
    )


@router.post("/webhooks/stripe")
def stripe_webhook() -> dict[str, str]:
    return {"status": "received"}
