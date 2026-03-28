from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_merchant_access
from app.models.entities import Merchant, Product, User
from app.schemas.contracts import (
    ConfirmProductsRequest,
    StoreScanRequest,
    StoreScanResponse,
    StructuredProductPayload,
)
from app.services.crawler import scan_store
from app.services.endpoints import assign_merchant_slug
from app.services.seeding import sync_products_for_merchant
from app.services.structuring import structure_products


router = APIRouter(tags=["onboarding"])


@router.post("/stores/scan", response_model=StoreScanResponse)
def scan_store_route(
    payload: StoreScanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreScanResponse:
    crawl_result = scan_store(payload.url)
    structured_products = structure_products(
        crawl_result["raw_products"],
        crawl_result["domain"],
    )
    if not structured_products:
        raise HTTPException(status_code=400, detail="No products found for that store")

    merchant = db.scalar(
        select(Merchant)
        .where(Merchant.domain == crawl_result["domain"])
        .options(joinedload(Merchant.products))
    )
    if merchant is None:
        merchant = Merchant(
            owner_user_id=current_user.id,
            domain=crawl_result["domain"],
            name=crawl_result["name"],
            platform=crawl_result["platform"],
            ships_to=crawl_result["ships_to"],
            trust_score=84.0 if "biaundies.com" in crawl_result["domain"] else 67.0,
            last_crawled=datetime.now(timezone.utc),
        )
        db.add(merchant)
        db.flush()
        merchant.products = []
    else:
        if merchant.owner_user_id is None:
            merchant.owner_user_id = current_user.id
        merchant.name = crawl_result["name"]
        merchant.platform = crawl_result["platform"]
        merchant.ships_to = crawl_result["ships_to"]
        merchant.last_crawled = datetime.now(timezone.utc)

    assign_merchant_slug(db, merchant)

    products = sync_products_for_merchant(db, merchant, structured_products)
    db.commit()

    return StoreScanResponse(
        merchant_id=merchant.id,
        merchant_slug=merchant.merchant_slug,
        domain=merchant.domain,
        name=merchant.name or crawl_result["name"],
        ships_to=merchant.ships_to,
        products=[StructuredProductPayload.model_validate(product) for product in products],
    )


@router.put("/stores/{merchant_id}/products", response_model=StoreScanResponse)
def confirm_products(
    merchant_id: str,
    payload: ConfirmProductsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreScanResponse:
    merchant = require_merchant_access(db, merchant_id, current_user)
    merchant = db.scalar(
        select(Merchant)
        .where(Merchant.id == merchant.id)
        .options(joinedload(Merchant.products))
    )
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    structured_products = [product.model_dump() for product in payload.products]
    products = sync_products_for_merchant(db, merchant, structured_products)
    db.commit()

    return StoreScanResponse(
        merchant_id=merchant.id,
        merchant_slug=merchant.merchant_slug,
        domain=merchant.domain,
        name=merchant.name or merchant.domain,
        ships_to=merchant.ships_to,
        products=[StructuredProductPayload.model_validate(product) for product in products],
    )
