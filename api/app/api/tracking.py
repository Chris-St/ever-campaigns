from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.entities import AgentEvent, AgentResponse, Click, Conversion, Match, Product
from app.schemas.contracts import ShopifyOrderWebhook


router = APIRouter(tags=["tracking"])


@router.get("/go/{product_id}")
def redirect_to_product(
    product_id: str,
    q: str | None = None,
    src: str | None = None,
    iid: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    product = db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if iid:
        response = db.scalar(select(AgentResponse).where(AgentResponse.id == iid))
        if response is not None:
            click = Click(
                match_id=None,
                product_id=product_id,
                campaign_id=response.campaign_id,
                channel="intent_listener",
                source="intent_listener",
                surface=src or response.surface,
                response_id=response.id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(click)
            db.commit()
        else:
            agent_event = db.scalar(select(AgentEvent).where(AgentEvent.id == iid))
            if agent_event is not None:
                click = Click(
                    match_id=None,
                    product_id=product_id,
                    campaign_id=agent_event.campaign_id,
                    channel="autonomous_agent",
                    source="autonomous_agent",
                    surface=src or agent_event.surface,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(click)
                db.commit()
    elif q:
        match = db.scalar(
            select(Match)
            .where(Match.product_id == product_id, Match.query_id == q)
            .order_by(Match.created_at.desc())
        )
        click = Click(
            match_id=match.id if match else None,
            product_id=product_id,
            campaign_id=match.campaign_id if match else None,
            channel=match.channel if match else "mcp",
            source=match.channel if match else "mcp",
            surface=src,
            created_at=datetime.now(timezone.utc),
        )
        db.add(click)
        db.commit()

    return RedirectResponse(product.source_url or "/")


@router.post("/webhooks/shopify/order")
def shopify_order_webhook(
    payload: ShopifyOrderWebhook,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    product = db.scalar(select(Product).where(Product.id == payload.product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    click = None
    if payload.query_id:
        click = db.scalar(
            select(Click)
            .join(Match, Click.match_id == Match.id, isouter=True)
            .where(Click.product_id == payload.product_id, Match.query_id == payload.query_id)
            .options(joinedload(Click.match))
            .order_by(Click.created_at.desc())
        )
    if click is None:
        candidate_clicks = db.scalars(
            select(Click)
            .where(Click.product_id == payload.product_id, Click.campaign_id == payload.campaign_id)
            .order_by(Click.created_at.desc())
        ).all()
        if candidate_clicks:
            click = max(
                candidate_clicks,
                key=lambda candidate: (
                    candidate.source in {"intent_listener", "autonomous_agent"},
                    candidate.created_at,
                ),
            )

    conversion = Conversion(
        click_id=click.id if click else None,
        product_id=payload.product_id,
        campaign_id=payload.campaign_id,
        order_value=payload.order_value,
        channel=click.channel if click else "mcp",
    )
    db.add(conversion)
    db.commit()
    return {"status": "recorded"}
