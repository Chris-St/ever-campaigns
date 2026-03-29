from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_campaign_access
from app.models.entities import Campaign, User
from app.schemas.contracts import BillingCheckoutRequest, BillingCheckoutResponse
from app.services.billing import construct_webhook_event, create_checkout_session, stripe_mode


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-checkout", response_model=BillingCheckoutResponse)
def create_checkout(
    payload: BillingCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingCheckoutResponse:
    campaign = require_campaign_access(db, payload.campaign_id, current_user)
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(joinedload(Campaign.merchant))
    )
    try:
        session = create_checkout_session(campaign, current_user)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Unable to create Stripe checkout session") from exc

    campaign.status = "pending_payment"
    campaign.stripe_checkout_session_id = session["id"]
    if session.get("subscription_id"):
        campaign.stripe_subscription_id = session["subscription_id"]
    if session.get("customer_id") and not current_user.stripe_customer_id:
        current_user.stripe_customer_id = session["customer_id"]
    db.commit()

    return BillingCheckoutResponse(
        mode=session["mode"],
        campaign_id=campaign.id,
        activated=False,
        status=campaign.status,
        message="Redirecting to Stripe Checkout. The campaign will activate after Stripe confirms payment.",
        checkout_url=session["url"],
        checkout_session_id=session["id"],
    )


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    payload = await request.body()
    try:
        event = construct_webhook_event(payload, stripe_signature)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload") from exc

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        campaign_id = metadata.get("campaign_id") or data.get("client_reference_id")
        if campaign_id:
            campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id))
            if campaign is not None:
                campaign.status = "active"
                campaign.stripe_checkout_session_id = data.get("id") or campaign.stripe_checkout_session_id
                campaign.stripe_subscription_id = data.get("subscription") or campaign.stripe_subscription_id
                if data.get("customer"):
                    user = db.scalar(select(User).where(User.id == campaign.user_id))
                    if user is not None:
                        user.stripe_customer_id = data.get("customer")
                db.commit()

    elif event_type == "invoice.payment_failed":
        subscription_id = data.get("subscription")
        if subscription_id:
            campaign = db.scalar(
                select(Campaign).where(Campaign.stripe_subscription_id == subscription_id)
            )
            if campaign is not None:
                campaign.status = "paused_manual"
                campaign.listener_status = "paused"
                db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id")
        if subscription_id:
            campaign = db.scalar(
                select(Campaign).where(Campaign.stripe_subscription_id == subscription_id)
            )
            if campaign is not None:
                campaign.status = "canceled"
                campaign.listener_status = "paused"
                db.commit()

    return {"status": "received", "mode": stripe_mode()}
