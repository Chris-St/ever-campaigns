from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import AgentMemory, Campaign, Click, Conversion, Proposal


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


def record_memory(
    db: Session,
    campaign: Campaign,
    *,
    kind: str,
    title: str,
    summary: str,
    confidence: float = 0.6,
    proposal: Proposal | None = None,
    product_id: str | None = None,
    surface: str | None = None,
    action_type: str | None = None,
    source_url: str | None = None,
    details: dict[str, Any] | None = None,
) -> AgentMemory:
    memory = AgentMemory(
        campaign_id=campaign.id,
        proposal_id=proposal.id if proposal else None,
        product_id=product_id or (proposal.product_id if proposal else None),
        kind=kind,
        title=title.strip(),
        summary=summary.strip(),
        surface=surface or (proposal.surface if proposal else None),
        action_type=action_type or (proposal.action_type if proposal else None),
        source_url=source_url or (proposal.source_url if proposal else None),
        details=details or {},
        confidence=max(0.0, min(confidence, 1.0)),
        created_at=utcnow(),
    )
    db.add(memory)
    db.flush()
    return memory


def serialize_memory(memory: AgentMemory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "kind": memory.kind,
        "title": memory.title,
        "summary": memory.summary,
        "surface": memory.surface,
        "action_type": memory.action_type,
        "product_id": memory.product_id,
        "confidence": round(memory.confidence, 2),
        "created_at": memory.created_at.isoformat(),
        "relative_time": relative_time(memory.created_at),
    }


def _list_memories(db: Session, campaign_id: str, limit: int = 40) -> list[AgentMemory]:
    return db.scalars(
        select(AgentMemory)
        .where(AgentMemory.campaign_id == campaign_id)
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
    ).all()


def _stringify_proposal(proposal: Proposal) -> str:
    product_name = proposal.product.name if proposal.product else "the product"
    surface = proposal.surface or "the web"
    return f"{proposal.action_type} on {surface} for {product_name}"


def _derive_fallback_memories(db: Session, campaign_id: str) -> list[dict[str, Any]]:
    proposals = db.scalars(
        select(Proposal)
        .where(Proposal.campaign_id == campaign_id)
        .options(joinedload(Proposal.product))
        .order_by(Proposal.created_at.desc())
        .limit(24)
    ).all()
    derived: list[dict[str, Any]] = []

    converted = [proposal for proposal in proposals if proposal.outcome == "converted"]
    if converted:
        best = converted[0]
        derived.append(
            {
                "id": f"derived-win-{best.id}",
                "kind": "conversion_win",
                "title": "Converted proposal",
                "summary": f"{_stringify_proposal(best)} produced a recorded conversion.",
                "surface": best.surface,
                "action_type": best.action_type,
                "product_id": best.product_id,
                "confidence": 0.9,
                "created_at": (best.outcome_recorded_at or best.created_at).isoformat(),
                "relative_time": relative_time(best.outcome_recorded_at or best.created_at),
            }
        )

    rejected = [proposal for proposal in proposals if proposal.status == "rejected"]
    if rejected:
        latest = rejected[0]
        note = latest.rejection_reason or "The operator did not trust the fit or framing."
        derived.append(
            {
                "id": f"derived-loss-{latest.id}",
                "kind": "rejection",
                "title": "Rejected proposal",
                "summary": f"{_stringify_proposal(latest)} was rejected. Feedback: {note}",
                "surface": latest.surface,
                "action_type": latest.action_type,
                "product_id": latest.product_id,
                "confidence": 0.7,
                "created_at": (latest.rejected_at or latest.created_at).isoformat(),
                "relative_time": relative_time(latest.rejected_at or latest.created_at),
            }
        )

    executed = [proposal for proposal in proposals if proposal.executed_at is not None]
    if executed:
        latest = executed[0]
        derived.append(
            {
                "id": f"derived-exec-{latest.id}",
                "kind": "execution",
                "title": "Executed tactic",
                "summary": f"{_stringify_proposal(latest)} made it through approval and manual execution.",
                "surface": latest.surface,
                "action_type": latest.action_type,
                "product_id": latest.product_id,
                "confidence": 0.65,
                "created_at": latest.executed_at.isoformat(),
                "relative_time": relative_time(latest.executed_at),
            }
        )
    return derived


def build_memory_summary(db: Session, campaign: Campaign) -> dict[str, Any]:
    memories = _list_memories(db, campaign.id)
    items = [serialize_memory(memory) for memory in memories[:8]]
    if not items:
        items = _derive_fallback_memories(db, campaign.id)

    wins = [
        item["summary"]
        for item in items
        if item["kind"] in {"conversion_win", "positive_outcome", "approval", "execution"}
    ][:4]
    cautions = [
        item["summary"]
        for item in items
        if item["kind"] in {"rejection", "negative_outcome", "no_response"}
    ][:4]
    operator_feedback = [
        item["summary"]
        for item in items
        if item["kind"] in {"approval", "rejection", "operator_feedback", "execution"}
    ][:4]

    if wins:
        summary = (
            f"Memory is active. Strongest known patterns: {' '.join(wins[:2])}"
        )
    elif cautions:
        summary = (
            f"Memory is active. Current caution signals: {' '.join(cautions[:2])}"
        )
    else:
        summary = (
            "Memory is active but still shallow. Use early operator feedback, clicks, and conversions "
            "to learn what drives sales more efficiently than compute cost."
        )

    return {
        "enabled": True,
        "summary": summary,
        "winning_patterns": wins,
        "caution_patterns": cautions,
        "operator_feedback": operator_feedback,
        "recent_items": items,
    }


def remember_conversion(
    db: Session,
    campaign: Campaign,
    *,
    conversion: Conversion,
    click: Click | None = None,
    proposal: Proposal | None = None,
) -> None:
    linked_proposal = proposal or (click.proposal if click and click.proposal else None)
    if linked_proposal is None:
        return
    product_name = linked_proposal.product.name if linked_proposal.product else "the product"
    title = "Confirmed conversion"
    summary = (
        f"{linked_proposal.action_type} on {linked_proposal.surface or 'the web'} for {product_name} "
        f"led to a recorded conversion worth {conversion.order_value:.2f}."
    )
    record_memory(
        db,
        campaign,
        kind="conversion_win",
        title=title,
        summary=summary,
        confidence=0.95,
        proposal=linked_proposal,
        details={
            "conversion_id": conversion.id,
            "order_value": conversion.order_value,
        },
    )
