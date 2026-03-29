from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.models.entities import AgentEvent, Campaign, Click, Conversion, Product, Proposal
from app.services.memory import record_memory


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def relative_time(value: datetime) -> str:
    delta = utcnow() - ensure_utc(value)
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m ago"


def build_proposal_referral_url(
    product_id: str,
    campaign_id: str,
    proposal_id: str,
    surface: str | None,
    referral_url: str | None = None,
) -> str:
    if referral_url:
        parsed = urlparse(referral_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["pid"] = proposal_id
        query["cid"] = campaign_id
        if surface:
            query["src"] = surface
        return urlunparse(parsed._replace(query=urlencode(query)))
    query = {"cid": campaign_id, "pid": proposal_id}
    if surface:
        query["src"] = surface
    return f"{settings.public_api_url}/go/{product_id}?{urlencode(query)}"


def create_audit_event(
    db: Session,
    campaign_id: str,
    *,
    event_type: str,
    description: str,
    proposal: Proposal | None = None,
    category: str = "proposal",
    source_url: str | None = None,
) -> AgentEvent:
    event = AgentEvent(
        campaign_id=campaign_id,
        event_type=event_type,
        category=category,
        surface=proposal.surface if proposal else None,
        description=description,
        source_url=source_url or (proposal.source_url if proposal else None),
        source_content=proposal.source_content if proposal else None,
        source_author=proposal.source_author if proposal else None,
        target_audience=proposal.source_author if proposal else None,
        product_id=proposal.product_id if proposal else None,
        referral_url=proposal.referral_url if proposal else None,
        response_text=proposal.proposed_response if proposal else None,
        model_provider=proposal.model_provider if proposal else None,
        model_name=proposal.model_name if proposal else None,
        tokens_used=0,
        compute_cost_usd=0.0,
        expected_impact="high"
        if float((proposal.intent_score or {}).get("composite", 0) or 0) >= 80
        else "medium"
        if proposal
        else None,
        details={
            "proposal_id": proposal.id if proposal else None,
            "proposal_status": proposal.status if proposal else None,
            "competition_score": proposal.competition_score if proposal else None,
        },
        created_at=utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def compute_campaign_spend(db: Session, campaign_id: str) -> float:
    proposal_cost = sum(
        db.scalars(select(Proposal.compute_cost_usd).where(Proposal.campaign_id == campaign_id)).all()
    )
    event_cost = sum(
        db.scalars(select(AgentEvent.compute_cost_usd).where(AgentEvent.campaign_id == campaign_id)).all()
    )
    return round(proposal_cost + event_cost, 2)


def budget_remaining(campaign: Campaign) -> float:
    return round(max(campaign.budget_monthly - campaign.budget_spent, 0.0), 2)


def update_campaign_budget_state(db: Session, campaign: Campaign) -> float:
    campaign.budget_spent = compute_campaign_spend(db, campaign.id)
    if campaign.budget_spent >= campaign.budget_monthly:
        campaign.status = "paused_budget"
        campaign.listener_status = "budget_exhausted"
    return budget_remaining(campaign)


def create_proposal_from_event(
    db: Session,
    campaign: Campaign,
    payload: dict[str, Any],
    created_at: datetime,
) -> Proposal:
    proposed_response = (payload.get("proposed_response") or payload.get("response_text") or "").strip()
    if not proposed_response:
        raise ValueError("Proposal events must include proposed_response")

    proposal = Proposal(
        campaign_id=campaign.id,
        product_id=payload.get("product_id"),
        surface=payload.get("surface"),
        source_url=payload.get("source_url"),
        source_content=payload.get("source_content"),
        source_author=payload.get("source_author"),
        source_context=payload.get("source_context"),
        intent_score=payload.get("intent_score", {}) or {},
        action_type=payload.get("action_type") or payload.get("action_taken") or "other",
        proposed_response=proposed_response,
        rationale=payload.get("rationale"),
        execution_instructions=payload.get("execution_instructions"),
        status="proposed",
        model_provider=payload.get("model_provider"),
        model_name=payload.get("model_name"),
        competition_score=float(payload.get("competition_score", 0.0) or 0.0),
        tokens_used=int(payload.get("tokens_used", 0) or 0),
        compute_cost_usd=float(payload.get("compute_cost_usd", 0.0) or 0.0),
        created_at=created_at,
    )
    db.add(proposal)
    db.flush()

    if proposal.product_id:
        proposal.referral_url = build_proposal_referral_url(
            proposal.product_id,
            campaign.id,
            proposal.id,
            proposal.surface,
            payload.get("referral_url"),
        )

    description = (
        f"Generated a {proposal.action_type.replace('_', ' ')} proposal"
        f"{f' on {proposal.surface}' if proposal.surface else ''}."
    )
    create_audit_event(db, campaign.id, event_type="proposal", description=description, proposal=proposal)
    update_campaign_budget_state(db, campaign)
    return proposal


def proposal_clicks(db: Session, proposal_id: str) -> list[Click]:
    return db.scalars(
        select(Click)
        .where(Click.proposal_id == proposal_id)
        .options(joinedload(Click.product), selectinload(Click.conversions))
        .order_by(Click.created_at.desc())
    ).all()


def proposal_conversions(db: Session, proposal_id: str) -> list[Conversion]:
    return db.scalars(
        select(Conversion)
        .join(Click, Conversion.click_id == Click.id)
        .where(Click.proposal_id == proposal_id)
        .options(joinedload(Conversion.product), joinedload(Conversion.click))
        .order_by(Conversion.created_at.desc())
    ).all()


def proposal_attribution_confidence(db: Session, proposal: Proposal) -> str:
    conversions = proposal_conversions(db, proposal.id)
    if conversions:
        return "confirmed"

    clicks = proposal_clicks(db, proposal.id)
    if clicks:
        return "confirmed"

    if proposal.outcome in {"clicked", "converted"}:
        return "estimated"

    if proposal.executed_at and proposal.product_id:
        estimated_conversion = db.scalar(
            select(Conversion)
            .where(
                Conversion.campaign_id == proposal.campaign_id,
                Conversion.product_id == proposal.product_id,
                Conversion.created_at >= proposal.executed_at,
                Conversion.created_at <= ensure_utc(proposal.executed_at) + timedelta(hours=24),
            )
            .order_by(Conversion.created_at.asc())
        )
        if estimated_conversion is not None:
            return "estimated"

    return "unattributed"


def build_proposal_record(db: Session, proposal: Proposal) -> dict[str, Any]:
    product = proposal.product
    clicks = proposal_clicks(db, proposal.id)
    conversions = proposal_conversions(db, proposal.id)
    revenue = round(sum(conversion.order_value for conversion in conversions), 2)
    confidence = proposal_attribution_confidence(db, proposal)
    return {
        "id": proposal.id,
        "campaign_id": proposal.campaign_id,
        "product_id": proposal.product_id,
        "product_name": product.name if product else None,
        "product_image": product.images[0] if product and product.images else None,
        "product_price": product.price if product else None,
        "product_currency": product.currency if product else None,
        "surface": proposal.surface,
        "source_url": proposal.source_url,
        "source_content": proposal.source_content,
        "source_author": proposal.source_author,
        "source_context": proposal.source_context,
        "intent_score": proposal.intent_score or {},
        "action_type": proposal.action_type,
        "proposed_response": proposal.proposed_response,
        "rationale": proposal.rationale,
        "referral_url": proposal.referral_url,
        "execution_instructions": proposal.execution_instructions,
        "status": proposal.status,
        "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
        "rejected_at": proposal.rejected_at.isoformat() if proposal.rejected_at else None,
        "rejection_reason": proposal.rejection_reason,
        "executed_at": proposal.executed_at.isoformat() if proposal.executed_at else None,
        "execution_notes": proposal.execution_notes,
        "outcome": proposal.outcome,
        "outcome_notes": proposal.outcome_notes,
        "outcome_recorded_at": proposal.outcome_recorded_at.isoformat() if proposal.outcome_recorded_at else None,
        "model_provider": proposal.model_provider,
        "model_name": proposal.model_name,
        "competition_score": round(proposal.competition_score or 0.0, 2),
        "tokens_used": proposal.tokens_used,
        "compute_cost_usd": round(proposal.compute_cost_usd, 4),
        "created_at": proposal.created_at.isoformat(),
        "relative_time": relative_time(proposal.created_at),
        "clicks": len(clicks),
        "conversions": len(conversions),
        "revenue": revenue,
        "attribution_confidence": confidence,
    }


def list_proposals(
    db: Session,
    campaign_id: str,
    status: str = "all",
    sort: str = "newest",
) -> list[dict[str, Any]]:
    proposals = db.scalars(
        select(Proposal)
        .where(Proposal.campaign_id == campaign_id)
        .options(joinedload(Proposal.product))
    ).all()
    if status != "all":
        proposals = [proposal for proposal in proposals if proposal.status == status]

    if sort == "intent":
        proposals.sort(
            key=lambda proposal: float((proposal.intent_score or {}).get("composite", 0) or 0),
            reverse=True,
        )
    elif sort == "product":
        proposals.sort(key=lambda proposal: (proposal.product.name if proposal.product else "", proposal.created_at), reverse=True)
    else:
        proposals.sort(key=lambda proposal: proposal.created_at, reverse=True)
    return [build_proposal_record(db, proposal) for proposal in proposals]


def get_proposal(db: Session, campaign_id: str, proposal_id: str) -> Proposal:
    proposal = db.scalar(
        select(Proposal)
        .where(Proposal.id == proposal_id, Proposal.campaign_id == campaign_id)
        .options(joinedload(Proposal.product))
    )
    if proposal is None:
        raise ValueError("Proposal not found")
    return proposal


def approve_proposal(db: Session, campaign: Campaign, proposal_id: str) -> dict[str, Any]:
    proposal = get_proposal(db, campaign.id, proposal_id)
    if proposal.status != "proposed":
        raise ValueError("Only proposed items can be approved")
    proposal.status = "approved"
    proposal.approved_at = utcnow()
    product_name = proposal.product.name if proposal.product else "the product"
    record_memory(
        db,
        campaign,
        kind="approval",
        title="Operator approved a tactic",
        summary=(
            f"The operator approved a {proposal.action_type} on {proposal.surface or 'the web'} "
            f"for {product_name}, signaling that the fit and framing looked credible."
        ),
        confidence=0.72,
        proposal=proposal,
    )
    create_audit_event(
        db,
        campaign.id,
        event_type="proposal_approved",
        description="Approved a proposal for manual execution.",
        proposal=proposal,
    )
    db.commit()
    db.refresh(proposal)
    return build_proposal_record(db, proposal)


def reject_proposal(
    db: Session,
    campaign: Campaign,
    proposal_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    proposal = get_proposal(db, campaign.id, proposal_id)
    if proposal.status != "proposed":
        raise ValueError("Only proposed items can be rejected")
    proposal.status = "rejected"
    proposal.rejected_at = utcnow()
    proposal.rejection_reason = reason.strip() if reason else None
    product_name = proposal.product.name if proposal.product else "the product"
    feedback = proposal.rejection_reason or "The operator did not trust the fit or framing."
    record_memory(
        db,
        campaign,
        kind="rejection",
        title="Operator rejected a tactic",
        summary=(
            f"A proposed {proposal.action_type} on {proposal.surface or 'the web'} for {product_name} "
            f"was rejected. Feedback: {feedback}"
        ),
        confidence=0.85,
        proposal=proposal,
        details={"reason": proposal.rejection_reason},
    )
    create_audit_event(
        db,
        campaign.id,
        event_type="proposal_rejected",
        description="Rejected a proposal.",
        proposal=proposal,
    )
    db.commit()
    db.refresh(proposal)
    return build_proposal_record(db, proposal)


def edit_proposal(
    db: Session,
    campaign: Campaign,
    proposal_id: str,
    proposed_response: str,
) -> dict[str, Any]:
    proposal = get_proposal(db, campaign.id, proposal_id)
    if proposal.status != "proposed":
        raise ValueError("Only proposed items can be edited")
    original = proposal.proposed_response
    proposal.proposed_response = proposed_response.strip()
    if proposal.proposed_response != original:
        record_memory(
            db,
            campaign,
            kind="operator_feedback",
            title="Operator edited proposal copy",
            summary=(
                f"The operator rewrote a {proposal.action_type} on {proposal.surface or 'the web'} "
                "before approval. Prefer the edited tone and framing over the original draft."
            ),
            confidence=0.66,
            proposal=proposal,
            details={
                "original_response": original,
                "edited_response": proposal.proposed_response,
            },
        )
    create_audit_event(
        db,
        campaign.id,
        event_type="proposal_edited",
        description="Edited a proposal before approval.",
        proposal=proposal,
    )
    db.commit()
    db.refresh(proposal)
    return build_proposal_record(db, proposal)


def mark_proposal_executed(
    db: Session,
    campaign: Campaign,
    proposal_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    proposal = get_proposal(db, campaign.id, proposal_id)
    if proposal.status != "approved":
        raise ValueError("Only approved proposals can be marked executed")
    proposal.status = "executed_manually"
    proposal.executed_at = utcnow()
    proposal.execution_notes = notes.strip() if notes else None
    product_name = proposal.product.name if proposal.product else "the product"
    record_memory(
        db,
        campaign,
        kind="execution",
        title="Approved tactic was executed",
        summary=(
            f"The operator manually executed a {proposal.action_type} on {proposal.surface or 'the web'} "
            f"for {product_name}. This tactic was strong enough to move from idea to action."
        ),
        confidence=0.74,
        proposal=proposal,
        details={"execution_notes": proposal.execution_notes},
    )
    create_audit_event(
        db,
        campaign.id,
        event_type="proposal_executed",
        description="Marked a proposal as executed manually.",
        proposal=proposal,
    )
    db.commit()
    db.refresh(proposal)
    return build_proposal_record(db, proposal)


def record_proposal_outcome(
    db: Session,
    campaign: Campaign,
    proposal_id: str,
    outcome: str,
    notes: str | None = None,
) -> dict[str, Any]:
    proposal = get_proposal(db, campaign.id, proposal_id)
    if proposal.status != "executed_manually":
        raise ValueError("Only executed proposals can record outcomes")
    proposal.status = "outcome_recorded"
    proposal.outcome = outcome.strip()
    proposal.outcome_notes = notes.strip() if notes else None
    proposal.outcome_recorded_at = utcnow()
    product_name = proposal.product.name if proposal.product else "the product"
    positive_outcomes = {"clicked", "converted"}
    memory_kind = "positive_outcome" if proposal.outcome in positive_outcomes else proposal.outcome or "outcome"
    record_memory(
        db,
        campaign,
        kind=memory_kind,
        title="Operator recorded an outcome",
        summary=(
            f"A manually executed {proposal.action_type} on {proposal.surface or 'the web'} for {product_name} "
            f"ended with outcome '{proposal.outcome}'."
            f"{f' Notes: {proposal.outcome_notes}' if proposal.outcome_notes else ''}"
        ),
        confidence=0.9 if proposal.outcome in positive_outcomes else 0.8,
        proposal=proposal,
        details={"outcome": proposal.outcome, "notes": proposal.outcome_notes},
    )
    create_audit_event(
        db,
        campaign.id,
        event_type="proposal_outcome_recorded",
        description=f"Recorded proposal outcome: {proposal.outcome}.",
        proposal=proposal,
    )
    db.commit()
    db.refresh(proposal)
    return build_proposal_record(db, proposal)


def build_proposal_stats(db: Session, campaign_id: str) -> dict[str, int]:
    proposals = db.scalars(select(Proposal).where(Proposal.campaign_id == campaign_id)).all()
    return {
        "total": len(proposals),
        "pending": sum(1 for proposal in proposals if proposal.status == "proposed"),
        "approved": sum(1 for proposal in proposals if proposal.approved_at is not None),
        "executed": sum(1 for proposal in proposals if proposal.executed_at is not None),
        "rejected": sum(1 for proposal in proposals if proposal.status == "rejected"),
    }


def build_attribution_confidence_summary(db: Session, campaign_id: str) -> dict[str, int]:
    conversions = db.scalars(
        select(Conversion)
        .where(Conversion.campaign_id == campaign_id)
        .options(joinedload(Conversion.click))
    ).all()
    confirmed = 0
    estimated = 0
    unattributed = 0
    executed_proposals = db.scalars(
        select(Proposal).where(
            Proposal.campaign_id == campaign_id,
            Proposal.executed_at.is_not(None),
        )
    ).all()
    for conversion in conversions:
        if conversion.click and conversion.click.proposal_id:
            confirmed += 1
            continue
        estimate_match = next(
            (
                proposal
                for proposal in executed_proposals
                if proposal.product_id == conversion.product_id
                and ensure_utc(conversion.created_at) >= ensure_utc(proposal.executed_at)
                and ensure_utc(conversion.created_at)
                <= ensure_utc(proposal.executed_at) + timedelta(hours=24)
            ),
            None,
        )
        if estimate_match is not None:
            estimated += 1
        else:
            unattributed += 1
    return {
        "confirmed": confirmed,
        "estimated": estimated,
        "unattributed": unattributed,
    }
