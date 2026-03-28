from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.entities import Campaign, Product, User
from app.schemas.contracts import ProductDetailResponse
from app.services.analytics import build_product_detail


router = APIRouter(prefix="/products", tags=["products"])


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductDetailResponse:
    product = db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    campaign = db.scalar(
        select(Campaign).where(
            Campaign.user_id == current_user.id,
            Campaign.merchant_id == product.merchant_id,
        )
    )
    if campaign is None:
        raise HTTPException(status_code=403, detail="You do not have access to this product")

    detail = build_product_detail(db, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product detail unavailable")
    return ProductDetailResponse.model_validate(detail)
