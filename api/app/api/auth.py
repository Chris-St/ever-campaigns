from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import Campaign, User
from app.schemas.contracts import AuthRequest, AuthResponse, CurrentUser


router = APIRouter(prefix="/auth", tags=["auth"])


def build_current_user_payload(db: Session, user: User) -> CurrentUser:
    campaigns = db.scalars(
        select(Campaign)
        .where(Campaign.user_id == user.id)
        .options(joinedload(Campaign.merchant))
        .order_by(Campaign.created_at.desc())
    ).all()

    return CurrentUser(
        id=user.id,
        email=user.email,
        campaigns=[
            {
                "id": campaign.id,
                "merchant_id": campaign.merchant_id,
                "merchant_slug": campaign.merchant.merchant_slug,
                "merchant_name": campaign.merchant.name or campaign.merchant.domain,
                "domain": campaign.merchant.domain,
                "status": campaign.status,
                "budget_monthly": campaign.budget_monthly,
                "budget_spent": campaign.budget_spent,
            }
            for campaign in campaigns
        ],
    )


@router.post("/signup", response_model=AuthResponse)
def signup(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with that email already exists")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        access_token=create_access_token(user.id),
        user=build_current_user_payload(db, user),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return AuthResponse(
        access_token=create_access_token(user.id),
        user=build_current_user_payload(db, user),
    )


@router.get("/me", response_model=CurrentUser)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    return build_current_user_payload(db, current_user)
