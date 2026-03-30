from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.entities import (
    AgentEvent,
    AgentResponse,
    Campaign,
    Click,
    Conversion,
    IntentSignal,
    Match,
    Proposal,
    Product,
)
from app.services.billing import stripe_mode
from app.services.endpoints import build_agent_endpoints
from app.services.proposals import build_attribution_confidence_summary, build_proposal_stats


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def relative_time(value: datetime) -> str:
    delta = datetime.now(timezone.utc) - ensure_utc(value)
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m ago"


def compute_campaign_overview(
    db: Session,
    campaign: Campaign,
    agent_api_key_plaintext: str | None = None,
) -> dict:
    matches = db.scalars(
        select(Match).where(Match.campaign_id == campaign.id).options(joinedload(Match.product))
    ).all()
    listener_signals = db.scalars(
        select(IntentSignal).where(IntentSignal.campaign_id == campaign.id)
    ).all()
    listener_responses = db.scalars(
        select(AgentResponse).where(AgentResponse.campaign_id == campaign.id)
    ).all()
    agent_events = db.scalars(
        select(AgentEvent).where(AgentEvent.campaign_id == campaign.id)
    ).all()
    proposals = db.scalars(
        select(Proposal).where(Proposal.campaign_id == campaign.id).options(joinedload(Proposal.product))
    ).all()
    conversions = db.scalars(
        select(Conversion)
        .where(Conversion.campaign_id == campaign.id)
        .options(joinedload(Conversion.product))
    ).all()

    compute_spent = round(
        sum(match.compute_cost for match in matches)
        + sum(signal.scoring_cost for signal in listener_signals)
        + sum(response.generation_cost for response in listener_responses)
        + sum(event.compute_cost_usd for event in agent_events),
        2,
    )
    compute_spent = round(
        compute_spent + sum(proposal.compute_cost_usd for proposal in proposals),
        2,
    )
    revenue = round(sum(conversion.order_value for conversion in conversions), 2)
    return_on_compute = round(revenue / compute_spent, 2) if compute_spent else 0.0
    budget_utilization = round(
        min(compute_spent / campaign.budget_monthly, 1.25) if campaign.budget_monthly else 0.0,
        4,
    )
    cost_events = [(match.created_at, match.compute_cost) for match in matches]
    cost_events.extend((signal.created_at, signal.scoring_cost) for signal in listener_signals)
    cost_events.extend((response.created_at, response.generation_cost) for response in listener_responses)
    cost_events.extend((event.created_at, event.compute_cost_usd) for event in agent_events)
    cost_events.extend((proposal.created_at, proposal.compute_cost_usd) for proposal in proposals)
    projected_monthly_spend = round(project_monthly_spend(cost_events), 2)
    alerts = []
    if budget_utilization >= 1:
        alerts.append("Budget exhausted. Active ranking boost will stop unless you increase the cap.")
    elif budget_utilization >= 0.9:
        alerts.append("90% of budget consumed. Burn rate suggests a top-up soon.")
    elif budget_utilization >= 0.8:
        alerts.append("80% of budget consumed. Watch projected end-of-month spend.")

    compute_series, revenue_series = sparkline_series(
        matches,
        listener_signals,
        listener_responses,
        agent_events,
        proposals,
        conversions,
    )

    campaign.budget_spent = compute_spent
    db.commit()
    proposal_stats = build_proposal_stats(db, campaign.id)
    attribution_confidence = build_attribution_confidence_summary(db, campaign.id)

    return {
        "id": campaign.id,
        "merchant_id": campaign.merchant_id,
        "merchant_slug": campaign.merchant.merchant_slug or "merchant",
        "merchant_name": campaign.merchant.name or "Merchant",
        "domain": campaign.merchant.domain,
        "status": campaign.status,
        "auto_optimize": campaign.auto_optimize,
        "budget_monthly": campaign.budget_monthly,
        "budget_spent": compute_spent,
        "budget_utilization": budget_utilization,
        "projected_monthly_spend": projected_monthly_spend,
        "compute_spent": compute_spent,
        "conversions": len(conversions),
        "revenue": revenue,
        "return_on_compute": return_on_compute,
        "proposals": proposal_stats,
        "attribution_confidence": attribution_confidence,
        "compute_series": compute_series,
        "revenue_series": revenue_series,
        "alerts": alerts,
        "billing": {
            "mode": stripe_mode(),
            "plan_name": f"${campaign.budget_monthly:,.0f}/month compute budget",
            "payment_method": (
                "Using your configured API accounts"
                if stripe_mode() == "self_funded"
                else (
                    "Managed in Stripe Checkout"
                    if campaign.stripe_checkout_session_id or campaign.stripe_subscription_id
                    else "Stripe not connected yet"
                )
            ),
            "status": campaign.status,
            "invoices": build_invoices(campaign),
        },
        "agent_endpoints": build_agent_endpoints(campaign, api_key_plaintext=agent_api_key_plaintext),
    }


def project_monthly_spend(cost_events: list[tuple[datetime, float]]) -> float:
    if not cost_events:
        return 0.0
    now = datetime.now(timezone.utc)
    recent = [cost for created_at, cost in cost_events if ensure_utc(created_at) >= now - timedelta(days=7)]
    if not recent:
        recent = [cost for _, cost in cost_events]
    average_daily_spend = sum(recent) / max(
        len({ensure_utc(created_at).date() for created_at, _ in cost_events}),
        1,
    )
    _, days_in_month = calendar.monthrange(now.year, now.month)
    return average_daily_spend * days_in_month


def sparkline_series(
    matches: list[Match],
    listener_signals: list[IntentSignal],
    listener_responses: list[AgentResponse],
    agent_events: list[AgentEvent],
    proposals: list[Proposal],
    conversions: list[Conversion],
) -> tuple[list[float], list[float]]:
    now = datetime.now(timezone.utc).date()
    compute_map = defaultdict(float)
    revenue_map = defaultdict(float)
    for match in matches:
        compute_map[ensure_utc(match.created_at).date()] += match.compute_cost
    for signal in listener_signals:
        compute_map[ensure_utc(signal.created_at).date()] += signal.scoring_cost
    for response in listener_responses:
        compute_map[ensure_utc(response.created_at).date()] += response.generation_cost
    for event in agent_events:
        compute_map[ensure_utc(event.created_at).date()] += event.compute_cost_usd
    for proposal in proposals:
        compute_map[ensure_utc(proposal.created_at).date()] += proposal.compute_cost_usd
    for conversion in conversions:
        revenue_map[ensure_utc(conversion.created_at).date()] += conversion.order_value

    compute_series = []
    revenue_series = []
    for offset in range(13, -1, -1):
        day = now - timedelta(days=offset)
        compute_series.append(round(compute_map.get(day, 0.0), 2))
        revenue_series.append(round(revenue_map.get(day, 0.0), 2))
    return compute_series, revenue_series


def build_metric_series(db: Session, campaign_id: str, period: str) -> list[dict]:
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id).options(joinedload(Campaign.merchant)))
    if campaign is None:
        return []

    period_map = {"7d": 7, "30d": 30, "90d": 90}
    days = period_map.get(period, 120)
    now = datetime.now(timezone.utc).date()
    start_date = now - timedelta(days=days - 1)

    matches = db.scalars(select(Match).where(Match.campaign_id == campaign_id)).all()
    listener_signals = db.scalars(select(IntentSignal).where(IntentSignal.campaign_id == campaign_id)).all()
    listener_responses = db.scalars(select(AgentResponse).where(AgentResponse.campaign_id == campaign_id)).all()
    agent_events = db.scalars(select(AgentEvent).where(AgentEvent.campaign_id == campaign_id)).all()
    proposals = db.scalars(select(Proposal).where(Proposal.campaign_id == campaign_id)).all()
    conversions = db.scalars(select(Conversion).where(Conversion.campaign_id == campaign_id)).all()
    compute_map = defaultdict(float)
    revenue_map = defaultdict(float)
    conversion_map = defaultdict(int)
    for match in matches:
        compute_map[ensure_utc(match.created_at).date()] += match.compute_cost
    for signal in listener_signals:
        compute_map[ensure_utc(signal.created_at).date()] += signal.scoring_cost
    for response in listener_responses:
        compute_map[ensure_utc(response.created_at).date()] += response.generation_cost
    for event in agent_events:
        compute_map[ensure_utc(event.created_at).date()] += event.compute_cost_usd
    for proposal in proposals:
        compute_map[ensure_utc(proposal.created_at).date()] += proposal.compute_cost_usd
    for conversion in conversions:
        conversion_date = ensure_utc(conversion.created_at).date()
        revenue_map[conversion_date] += conversion.order_value
        conversion_map[conversion_date] += 1

    points = []
    total_days = (now - start_date).days + 1
    for offset in range(total_days):
        day = start_date + timedelta(days=offset)
        points.append(
            {
                "date": day.isoformat(),
                "compute_spend": round(compute_map.get(day, 0.0), 2),
                "revenue": round(revenue_map.get(day, 0.0), 2),
                "conversions": conversion_map.get(day, 0),
            }
        )
    return points


def build_product_rows(db: Session, campaign: Campaign) -> list[dict]:
    listener_signals = db.scalars(
        select(IntentSignal).where(IntentSignal.campaign_id == campaign.id)
    ).all()
    listener_responses = db.scalars(
        select(AgentResponse).where(AgentResponse.campaign_id == campaign.id)
    ).all()
    agent_events = db.scalars(
        select(AgentEvent).where(AgentEvent.campaign_id == campaign.id)
    ).all()
    proposals = db.scalars(
        select(Proposal).where(Proposal.campaign_id == campaign.id)
    ).all()
    products = db.scalars(
        select(Product)
        .where(Product.merchant_id == campaign.merchant_id)
        .options(
            selectinload(Product.matches),
            selectinload(Product.clicks),
            selectinload(Product.conversions),
        )
    ).all()
    rows = []
    for product in products:
        matches = [match for match in product.matches if match.campaign_id == campaign.id]
        product_signals = [signal for signal in listener_signals if signal.product_id == product.id]
        product_responses = [response for response in listener_responses if response.product_id == product.id]
        product_events = [event for event in agent_events if event.product_id == product.id]
        product_proposals = [proposal for proposal in proposals if proposal.product_id == product.id]
        clicks = [click for click in product.clicks if click.campaign_id == campaign.id]
        conversions = [conversion for conversion in product.conversions if conversion.campaign_id == campaign.id]
        compute_spent = (
            sum(match.compute_cost for match in matches)
            + sum(signal.scoring_cost for signal in product_signals)
            + sum(response.generation_cost for response in product_responses)
            + sum(event.compute_cost_usd for event in product_events)
            + sum(proposal.compute_cost_usd for proposal in product_proposals)
        )
        revenue = sum(conversion.order_value for conversion in conversions)
        roc = round(revenue / compute_spent, 2) if compute_spent else 0.0
        status = "stable"
        if roc >= 3.0 or len(conversions) >= 15:
            status = "top"
        elif roc < 1.5:
            status = "watch"
        rows.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "currency": product.currency,
                "image": product.images[0] if product.images else None,
                "matches": len(matches) + len(product_signals) + len(product_events) + len(product_proposals),
                "clicks": len(clicks),
                "conversions": len(conversions),
                "revenue": round(revenue, 2),
                "return_on_compute": roc,
                "status": status,
            }
        )
    rows.sort(key=lambda row: (row["revenue"], row["return_on_compute"]), reverse=True)
    return rows


def build_activity_feed(
    db: Session,
    campaign_id: str,
    limit: int = 50,
    event_type: str = "all",
) -> list[dict]:
    matches = db.scalars(
        select(Match)
        .where(Match.campaign_id == campaign_id)
        .options(joinedload(Match.product), joinedload(Match.query))
    ).all()
    agent_events = db.scalars(
        select(AgentEvent)
        .where(AgentEvent.campaign_id == campaign_id)
        .options(joinedload(AgentEvent.product))
    ).all()
    clicks = db.scalars(
        select(Click)
        .where(Click.campaign_id == campaign_id)
        .options(
            joinedload(Click.product),
            joinedload(Click.match).joinedload(Match.query),
            joinedload(Click.response),
        )
    ).all()
    conversions = db.scalars(
        select(Conversion)
        .where(Conversion.campaign_id == campaign_id)
        .options(joinedload(Conversion.product), joinedload(Conversion.click).joinedload(Click.response))
    ).all()

    events = []
    normalized_filter = event_type.lower()
    if normalized_filter in ("all", "match"):
        for match in matches:
            query_text = match.query.query_text if match.query else "agent query"
            events.append(
                {
                    "id": match.id,
                    "event_type": "match",
                    "channel": match.channel,
                    "title": f"Agent matched '{match.product.name}'",
                    "detail": f"Query: '{query_text}' via {match.channel.upper()}",
                    "timestamp": match.created_at.isoformat(),
                    "relative_time": relative_time(match.created_at),
                    "product_id": match.product_id,
                    "product_name": match.product.name,
                    "surface": match.channel,
                    "category": "match",
                    "compute_cost": match.compute_cost,
                }
            )
    if normalized_filter in ("all", "action", "strategy", "response", "proposal"):
        for agent_event in agent_events:
            if agent_event.event_type == "strategy_update":
                event_bucket = "strategy"
            elif agent_event.event_type.startswith("proposal"):
                event_bucket = "proposal"
            else:
                event_bucket = "action"
            if normalized_filter not in ("all", "response") and normalized_filter != event_bucket:
                continue
            if normalized_filter == "response" and agent_event.event_type != "action":
                continue
            title = (
                "Strategy update"
                if agent_event.event_type == "strategy_update"
                else "Proposal update"
                if agent_event.event_type.startswith("proposal_")
                else "New proposal"
                if agent_event.event_type == "proposal"
                else f"{(agent_event.category or 'action').replace('_', ' ').title()} on {agent_event.surface or 'other'}"
            )
            events.append(
                {
                    "id": agent_event.id,
                    "event_type": agent_event.event_type,
                    "channel": "autonomous_agent",
                    "category": agent_event.category,
                    "surface": agent_event.surface,
                    "title": title,
                    "detail": agent_event.description,
                    "timestamp": agent_event.created_at.isoformat(),
                    "relative_time": relative_time(agent_event.created_at),
                    "product_id": agent_event.product_id,
                    "product_name": agent_event.product.name if agent_event.product else None,
                    "compute_cost": agent_event.compute_cost_usd,
                    "expected_impact": agent_event.expected_impact,
                    "source_url": agent_event.source_url,
                    "proposal_id": agent_event.details.get("proposal_id") if agent_event.details else None,
                    "proposal_status": agent_event.details.get("proposal_status") if agent_event.details else None,
                    "model_provider": agent_event.model_provider,
                    "model_name": agent_event.model_name,
                }
            )

    if normalized_filter in ("all", "click"):
        for click in clicks:
            if click.source == "proposal":
                detail = f"Viewed via a manually executed proposal on {click.surface or 'the web'}"
            elif click.source in {"intent_listener", "autonomous_agent"}:
                detail = f"Viewed via {click.surface or 'social'} autonomous agent activity"
            else:
                agent_name = click.match.query.agent_source if click.match and click.match.query else "an agent"
                detail = f"Surfaced via {agent_name} on {click.channel.upper()}"
            events.append(
                {
                    "id": click.id,
                    "event_type": "click",
                    "channel": click.channel,
                    "category": "click",
                    "surface": click.surface,
                    "title": f"Click: consumer viewed {click.product.name}",
                    "detail": detail,
                    "timestamp": click.created_at.isoformat(),
                    "relative_time": relative_time(click.created_at),
                    "product_id": click.product_id,
                    "product_name": click.product.name,
                }
            )

    if normalized_filter in ("all", "conversion"):
        for conversion in conversions:
            if conversion.click and conversion.click.source == "proposal":
                detail = (
                    f"${conversion.order_value:,.2f} attributed revenue from a tracked proposal"
                )
            elif conversion.click and conversion.click.source in {"intent_listener", "autonomous_agent"}:
                detail = (
                    f"${conversion.order_value:,.2f} attributed revenue from "
                    f"{(conversion.click.surface or 'agent').title()} activity"
                )
            else:
                detail = f"${conversion.order_value:,.2f} attributed revenue on {conversion.channel.upper()}"
            events.append(
                {
                    "id": conversion.id,
                    "event_type": "conversion",
                    "channel": conversion.channel,
                    "category": "conversion",
                    "surface": conversion.click.surface if conversion.click else None,
                    "title": f"Conversion: {conversion.product.name} purchased",
                    "detail": detail,
                    "timestamp": conversion.created_at.isoformat(),
                    "relative_time": relative_time(conversion.created_at),
                    "product_id": conversion.product_id,
                    "product_name": conversion.product.name,
                }
            )

    events.sort(key=lambda item: item["timestamp"], reverse=True)
    return events[:limit]


def build_product_detail(db: Session, product_id: str) -> dict | None:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            joinedload(Product.merchant),
            selectinload(Product.matches).joinedload(Match.query),
            selectinload(Product.clicks),
            selectinload(Product.conversions),
        )
    )
    if product is None:
        return None

    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.merchant_id == product.merchant_id)
        .order_by(Campaign.created_at.desc())
    )
    if campaign is None:
        return None

    rows = build_product_rows(db, campaign)
    performance = next((row for row in rows if row["product_id"] == product.id), None)
    if performance is None:
        performance = {
            "product_id": product.id,
            "name": product.name,
            "price": product.price,
            "currency": product.currency,
            "image": product.images[0] if product.images else None,
            "matches": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "return_on_compute": 0.0,
            "status": "stable",
        }

    matched_queries = []
    campaign_matches = [match for match in product.matches if match.campaign_id == campaign.id]
    campaign_matches.sort(key=lambda match: match.created_at, reverse=True)
    for match in campaign_matches[:12]:
        matched_queries.append(
            {
                "query_text": match.query.query_text or "agent query",
                "agent_source": match.query.agent_source if match.query else None,
                "score": round(match.score, 2),
                "timestamp": match.created_at.isoformat(),
                "constraint_matches": extract_constraint_breakdown(product, match),
            }
        )

    return {
        "id": product.id,
        "merchant_id": product.merchant_id,
        "source_url": product.source_url,
        "name": product.name,
        "category": product.category,
        "subcategory": product.subcategory,
        "price": product.price,
        "currency": product.currency,
        "description": product.description,
        "attributes": product.attributes,
        "images": product.images,
        "performance": performance,
        "matched_queries": matched_queries,
    }


def extract_constraint_breakdown(product: Product, match: Match) -> list[str]:
    query_constraints = match.query.constraints if match.query else {}
    breakdown = []
    if query_constraints.get("category") and product.category == query_constraints["category"]:
        breakdown.append(f"category: {product.category.replace('_', ' ')}")
    if query_constraints.get("subcategory") and product.subcategory == query_constraints["subcategory"]:
        breakdown.append(f"subcategory: {product.subcategory.replace('_', ' ')}")
    if query_constraints.get("activities"):
        overlap = set(query_constraints["activities"]).intersection(product.attributes.get("activities", []))
        if overlap:
            breakdown.append(f"activity fit: {', '.join(sorted(overlap))}")
    if query_constraints.get("max_price"):
        breakdown.append(f"price fit: ${product.price:,.0f} <= ${query_constraints['max_price']:,.0f}")
    if query_constraints.get("ships_to"):
        breakdown.append(f"ships to: {query_constraints['ships_to']}")
    return breakdown or ["high overall fit"]


def build_invoices(campaign: Campaign) -> list[dict]:
    if stripe_mode() == "self_funded":
        return []
    if not campaign.stripe_checkout_session_id and not campaign.stripe_subscription_id:
        return []
    invoice_status = "paid" if campaign.status == "active" else "open" if campaign.status == "pending_payment" else "canceled"
    return [
        {
            "id": campaign.stripe_subscription_id or campaign.stripe_checkout_session_id or f"inv_{campaign.id[:8]}",
            "date": campaign.created_at.date().isoformat(),
            "amount": round(campaign.budget_monthly, 2),
            "status": invoice_status,
        }
    ]
