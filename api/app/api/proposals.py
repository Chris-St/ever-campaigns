from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_campaign_access
from app.models.entities import User
from app.schemas.contracts import (
    ProposalEditRequest,
    ProposalExecutedRequest,
    ProposalOutcomeRequest,
    ProposalRecord,
    ProposalRejectRequest,
)
from app.services.proposals import (
    approve_proposal,
    edit_proposal,
    list_proposals,
    mark_proposal_executed,
    record_proposal_outcome,
    reject_proposal,
)


router = APIRouter(prefix="/campaigns", tags=["proposals"])


@router.get("/{campaign_id}/proposals", response_model=list[ProposalRecord])
def get_campaign_proposals(
    campaign_id: str,
    status: str = "all",
    sort: str = "newest",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProposalRecord]:
    require_campaign_access(db, campaign_id, current_user)
    return [ProposalRecord.model_validate(item) for item in list_proposals(db, campaign_id, status=status, sort=sort)]


@router.post("/{campaign_id}/proposals/{proposal_id}/approve", response_model=ProposalRecord)
def approve_campaign_proposal(
    campaign_id: str,
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        return ProposalRecord.model_validate(approve_proposal(db, campaign, proposal_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{campaign_id}/proposals/{proposal_id}/reject", response_model=ProposalRecord)
def reject_campaign_proposal(
    campaign_id: str,
    proposal_id: str,
    payload: ProposalRejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        return ProposalRecord.model_validate(
            reject_proposal(db, campaign, proposal_id, reason=payload.reason)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{campaign_id}/proposals/{proposal_id}/edit", response_model=ProposalRecord)
def edit_campaign_proposal(
    campaign_id: str,
    proposal_id: str,
    payload: ProposalEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        return ProposalRecord.model_validate(
            edit_proposal(db, campaign, proposal_id, payload.proposed_response)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{campaign_id}/proposals/{proposal_id}/executed", response_model=ProposalRecord)
def mark_campaign_proposal_executed(
    campaign_id: str,
    proposal_id: str,
    payload: ProposalExecutedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        return ProposalRecord.model_validate(
            mark_proposal_executed(db, campaign, proposal_id, payload.notes)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{campaign_id}/proposals/{proposal_id}/outcome", response_model=ProposalRecord)
def record_campaign_proposal_outcome(
    campaign_id: str,
    proposal_id: str,
    payload: ProposalOutcomeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalRecord:
    campaign = require_campaign_access(db, campaign_id, current_user)
    try:
        return ProposalRecord.model_validate(
            record_proposal_outcome(db, campaign, proposal_id, payload.outcome, payload.notes)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
