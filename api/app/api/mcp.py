from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.entities import Merchant, Product
from app.schemas.contracts import (
    CatalogResponse,
    CompareProductsRequest,
    CompareProductsResponse,
    MCPEnvelope,
    SearchProductsRequest,
    SearchProductsResponse,
)
from app.services.analytics import build_product_detail
from app.services.matching import search_products


router = APIRouter(prefix="/mcp", tags=["mcp"])


def resolve_scope(db: Session, merchant_slug: str | None) -> str:
    if merchant_slug in (None, "all"):
        return "all"

    merchant = db.scalar(
        select(Merchant).where(Merchant.merchant_slug == merchant_slug)
    )
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant MCP server not found")
    return merchant_slug


def list_tools_payload(scope: str) -> dict:
    tools = [
        {
            "name": "search_products",
            "description": "Search the Ever product index with natural language or structured constraints.",
        },
        {
            "name": "get_product",
            "description": "Fetch product detail and structured attributes by product ID.",
        },
    ]
    if scope == "all":
        tools.append(
            {
                "name": "compare_products",
                "description": "Compare multiple products side by side across active merchants.",
            }
        )
    else:
        tools.append(
            {
                "name": "get_catalog",
                "description": "Browse all products from this merchant with optional filters.",
            }
        )
    return {"scope": scope, "tools": tools}


def do_search(
    payload: SearchProductsRequest,
    db: Session,
    merchant_slug: str | None,
) -> SearchProductsResponse:
    scope = resolve_scope(db, merchant_slug)
    query_id, constraints, results = search_products(
        db,
        payload.query,
        payload.constraints,
        limit=payload.limit,
        agent_source=payload.agent_source,
        merchant_slug=None if scope == "all" else scope,
        channel="mcp",
    )
    return SearchProductsResponse(
        query_id=query_id,
        scope=scope,
        constraints=constraints,
        results=results,
    )


def do_get_product(db: Session, product_id: str, merchant_slug: str | None) -> dict:
    scope = resolve_scope(db, merchant_slug)
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(joinedload(Product.merchant))
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if scope != "all" and product.merchant.merchant_slug != scope:
        raise HTTPException(status_code=404, detail="Product not found for this merchant")

    detail = build_product_detail(db, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product detail unavailable")
    return detail


def do_compare_products(
    db: Session,
    payload: CompareProductsRequest,
    merchant_slug: str | None,
) -> CompareProductsResponse:
    scope = resolve_scope(db, merchant_slug)
    query = select(Product).where(Product.id.in_(payload.product_ids))
    products = db.scalars(query.options(joinedload(Product.merchant))).all()
    if scope != "all":
        products = [
            product
            for product in products
            if product.merchant.merchant_slug == scope
        ]
    return CompareProductsResponse(
        products=[
            {
                "id": product.id,
                "merchant_id": product.merchant_id,
                "merchant_slug": product.merchant.merchant_slug,
                "name": product.name,
                "price": product.price,
                "currency": product.currency,
                "category": product.category,
                "subcategory": product.subcategory,
                "attributes": product.attributes,
            }
            for product in products
        ]
    )


def do_get_catalog(
    db: Session,
    merchant_slug: str,
    category: str | None = None,
    subcategory: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> CatalogResponse:
    scope = resolve_scope(db, merchant_slug)
    if scope == "all":
        raise HTTPException(status_code=400, detail="Catalog browsing must target a specific merchant")

    query = (
        select(Product)
        .join(Merchant)
        .where(
            Merchant.merchant_slug == scope,
            Product.status == "active",
        )
    )
    if category:
        query = query.where(Product.category == category)
    if subcategory:
        query = query.where(Product.subcategory == subcategory)

    products = db.scalars(query.options(joinedload(Product.merchant))).all()
    total = len(products)
    products = products[offset : offset + max(1, min(limit, 100))]
    return CatalogResponse(
        scope=scope,
        total=total,
        products=[
            {
                "product_id": product.id,
                "merchant_id": product.merchant_id,
                "merchant_slug": product.merchant.merchant_slug,
                "name": product.name,
                "price": product.price,
                "currency": product.currency,
                "category": product.category,
                "subcategory": product.subcategory,
                "images": product.images,
                "source_url": product.source_url,
            }
            for product in products
        ],
    )


@router.get("/tools")
def list_tools() -> dict:
    return list_tools_payload("all")


@router.get("/all/tools")
def list_tools_all() -> dict:
    return list_tools_payload("all")


@router.get("/{merchant_slug}/tools")
def list_tools_scoped(merchant_slug: str, db: Session = Depends(get_db)) -> dict:
    scope = resolve_scope(db, merchant_slug)
    return list_tools_payload(scope)


@router.post("/tools/search_products", response_model=SearchProductsResponse)
def search_products_tool(
    payload: SearchProductsRequest,
    db: Session = Depends(get_db),
) -> SearchProductsResponse:
    return do_search(payload, db, None)


@router.post("/all/tools/search_products", response_model=SearchProductsResponse)
def search_products_all_tool(
    payload: SearchProductsRequest,
    db: Session = Depends(get_db),
) -> SearchProductsResponse:
    return do_search(payload, db, "all")


@router.post("/{merchant_slug}/tools/search_products", response_model=SearchProductsResponse)
def search_products_scoped_tool(
    merchant_slug: str,
    payload: SearchProductsRequest,
    db: Session = Depends(get_db),
) -> SearchProductsResponse:
    return do_search(payload, db, merchant_slug)


@router.get("/tools/get_product/{product_id}")
def get_product_tool(product_id: str, db: Session = Depends(get_db)) -> dict:
    return do_get_product(db, product_id, None)


@router.get("/all/tools/get_product/{product_id}")
def get_product_all_tool(product_id: str, db: Session = Depends(get_db)) -> dict:
    return do_get_product(db, product_id, "all")


@router.get("/{merchant_slug}/tools/get_product/{product_id}")
def get_product_scoped_tool(
    merchant_slug: str,
    product_id: str,
    db: Session = Depends(get_db),
) -> dict:
    return do_get_product(db, product_id, merchant_slug)


@router.post("/tools/compare_products", response_model=CompareProductsResponse)
def compare_products_tool(
    payload: CompareProductsRequest,
    db: Session = Depends(get_db),
) -> CompareProductsResponse:
    return do_compare_products(db, payload, None)


@router.post("/all/tools/compare_products", response_model=CompareProductsResponse)
def compare_products_all_tool(
    payload: CompareProductsRequest,
    db: Session = Depends(get_db),
) -> CompareProductsResponse:
    return do_compare_products(db, payload, "all")


@router.get("/{merchant_slug}/tools/get_catalog", response_model=CatalogResponse)
def get_catalog_tool(
    merchant_slug: str,
    category: str | None = Query(default=None),
    subcategory: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CatalogResponse:
    return do_get_catalog(
        db,
        merchant_slug,
        category=category,
        subcategory=subcategory,
        limit=limit,
        offset=offset,
    )


@router.post("")
def mcp_rpc(payload: MCPEnvelope, db: Session = Depends(get_db)) -> dict:
    if payload.method == "tools/list":
        return {"jsonrpc": "2.0", "id": payload.id, "result": list_tools_payload("all")}

    if payload.method == "tools/call":
        tool_name = payload.params.get("name")
        arguments = payload.params.get("arguments", {})
        if tool_name == "search_products":
            result = do_search(SearchProductsRequest(**arguments), db, None)
        elif tool_name == "get_product":
            result = do_get_product(db, arguments["product_id"], None)
        elif tool_name == "compare_products":
            result = do_compare_products(db, CompareProductsRequest(**arguments), None)
        else:
            raise HTTPException(status_code=404, detail="Unknown tool")
        return {"jsonrpc": "2.0", "id": payload.id, "result": result}

    raise HTTPException(status_code=400, detail="Unsupported MCP method")


@router.post("/all")
def mcp_rpc_all(payload: MCPEnvelope, db: Session = Depends(get_db)) -> dict:
    if payload.method == "tools/list":
        return {"jsonrpc": "2.0", "id": payload.id, "result": list_tools_payload("all")}

    if payload.method == "tools/call":
        tool_name = payload.params.get("name")
        arguments = payload.params.get("arguments", {})
        if tool_name == "search_products":
            result = do_search(SearchProductsRequest(**arguments), db, "all")
        elif tool_name == "get_product":
            result = do_get_product(db, arguments["product_id"], "all")
        elif tool_name == "compare_products":
            result = do_compare_products(db, CompareProductsRequest(**arguments), "all")
        else:
            raise HTTPException(status_code=404, detail="Unknown tool")
        return {"jsonrpc": "2.0", "id": payload.id, "result": result}

    raise HTTPException(status_code=400, detail="Unsupported MCP method")


@router.post("/{merchant_slug}")
def mcp_rpc_scoped(
    merchant_slug: str,
    payload: MCPEnvelope,
    db: Session = Depends(get_db),
) -> dict:
    scope = resolve_scope(db, merchant_slug)
    if payload.method == "tools/list":
        return {"jsonrpc": "2.0", "id": payload.id, "result": list_tools_payload(scope)}

    if payload.method == "tools/call":
        tool_name = payload.params.get("name")
        arguments = payload.params.get("arguments", {})
        if tool_name == "search_products":
            result = do_search(SearchProductsRequest(**arguments), db, scope)
        elif tool_name == "get_product":
            result = do_get_product(db, arguments["product_id"], scope)
        elif tool_name == "get_catalog":
            result = do_get_catalog(
                db,
                scope,
                category=arguments.get("category"),
                subcategory=arguments.get("subcategory"),
                limit=arguments.get("limit", 20),
                offset=arguments.get("offset", 0),
            )
        else:
            raise HTTPException(status_code=404, detail="Unknown tool")
        return {"jsonrpc": "2.0", "id": payload.id, "result": result}

    raise HTTPException(status_code=400, detail="Unsupported MCP method")
