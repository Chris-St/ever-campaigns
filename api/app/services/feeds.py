from __future__ import annotations

import gzip
import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Merchant


def get_merchant_with_products(db: Session, merchant_id: str) -> Merchant | None:
    return db.scalar(
        select(Merchant)
        .where(Merchant.id == merchant_id)
        .options(selectinload(Merchant.products))
    )


def build_acp_records(merchant: Merchant) -> list[dict]:
    records = []
    for product in merchant.products:
        if product.status != "active":
            continue
        records.append(
            {
                "product_id": product.id,
                "merchant_id": merchant.id,
                "merchant_slug": merchant.merchant_slug,
                "title": product.name,
                "description": product.description,
                "price": product.price,
                "currency": product.currency,
                "category": product.category,
                "subcategory": product.subcategory,
                "source_url": product.source_url,
                "image": product.images[0] if product.images else None,
                "attributes": product.attributes,
                "availability": "in_stock",
                "channel": "acp",
            }
        )
    return records


def build_acp_feed_bytes(merchant: Merchant) -> bytes:
    lines = [json.dumps(record, ensure_ascii=True) for record in build_acp_records(merchant)]
    return gzip.compress("\n".join(lines).encode("utf-8"))


def build_ucp_feed_payload(merchant: Merchant) -> dict:
    products = []
    for product in merchant.products:
        if product.status != "active":
            continue
        products.append(
            {
                "id": product.id,
                "title": product.name,
                "description": product.description,
                "price": {
                    "amount": product.price,
                    "currency": product.currency,
                },
                "merchant": {
                    "id": merchant.id,
                    "slug": merchant.merchant_slug,
                    "name": merchant.name,
                    "domain": merchant.domain,
                },
                "category": product.category,
                "subcategory": product.subcategory,
                "url": product.source_url,
                "images": product.images,
                "attributes": product.attributes,
                "channel": "ucp",
            }
        )
    return {
        "merchant_id": merchant.id,
        "merchant_slug": merchant.merchant_slug,
        "generated_for": "ucp",
        "products": products,
    }
