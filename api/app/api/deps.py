from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token, verify_api_key
from app.db.session import SessionLocal
from app.models.entities import Campaign, Merchant, User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001
        raise credentials_error from exc

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_error
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise credentials_error
    return user


def require_campaign_access(db: Session, campaign_id: str, user: User) -> Campaign:
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id))
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def require_merchant_access(db: Session, merchant_id: str, user: User) -> Merchant:
    merchant = db.scalar(select(Merchant).where(Merchant.id == merchant_id))
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.owner_user_id and merchant.owner_user_id != user.id:
        owned_campaign = db.scalar(
            select(Campaign).where(Campaign.user_id == user.id, Campaign.merchant_id == merchant.id)
        )
        if owned_campaign is None:
            raise HTTPException(status_code=403, detail="Merchant belongs to a different account")
    return merchant


def get_campaign_by_api_key(
    campaign_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Campaign:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing campaign API key",
        )
    api_key = authorization.split(" ", 1)[1].strip()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(joinedload(Campaign.merchant).selectinload(Merchant.products))
    )
    if campaign is None or not verify_api_key(api_key, campaign.listener_api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid campaign API key",
        )
    return campaign
