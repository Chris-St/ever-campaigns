from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.db.session import SessionLocal
from app.services.feeds import (
    build_acp_feed_bytes,
    build_acp_records,
    build_ucp_feed_payload,
    get_merchant_with_products,
)


router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/{merchant_id}/acp.jsonl.gz")
def get_acp_feed(merchant_id: str) -> Response:
    db = SessionLocal()
    try:
        merchant = get_merchant_with_products(db, merchant_id)
        if merchant is None:
            raise HTTPException(status_code=404, detail="Merchant not found")
        return Response(
            content=build_acp_feed_bytes(merchant),
            media_type="application/gzip",
            headers={
                "Content-Disposition": f'inline; filename="{merchant.merchant_slug or merchant.id}-acp.jsonl.gz"'
            },
        )
    finally:
        db.close()


@router.get("/{merchant_id}/acp-preview.json")
def get_acp_preview(merchant_id: str) -> JSONResponse:
    db = SessionLocal()
    try:
        merchant = get_merchant_with_products(db, merchant_id)
        if merchant is None:
            raise HTTPException(status_code=404, detail="Merchant not found")
        return JSONResponse(
            {
                "merchant_id": merchant.id,
                "merchant_slug": merchant.merchant_slug,
                "generated_for": "acp",
                "products": build_acp_records(merchant),
            }
        )
    finally:
        db.close()


@router.get("/{merchant_id}/ucp.json")
def get_ucp_feed(merchant_id: str) -> JSONResponse:
    db = SessionLocal()
    try:
        merchant = get_merchant_with_products(db, merchant_id)
        if merchant is None:
            raise HTTPException(status_code=404, detail="Merchant not found")
        return JSONResponse(build_ucp_feed_payload(merchant))
    finally:
        db.close()


@router.get("/{merchant_id}/ucp-preview.json")
def get_ucp_preview(merchant_id: str) -> JSONResponse:
    return get_ucp_feed(merchant_id)
