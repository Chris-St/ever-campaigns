from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.entities import Campaign, Match, Merchant, Product, Query


def parse_query(query: str) -> dict[str, Any]:
    lower_query = query.lower()
    constraints: dict[str, Any] = {
        "activities": [],
        "keywords": [],
    }
    max_price_match = re.search(r"(?:under|below|less than)\s*\$?(\d+)", lower_query)
    if max_price_match:
        constraints["max_price"] = float(max_price_match.group(1))

    category_map = {
        "underwear": "athletic_underwear",
        "thong": "athletic_underwear",
        "lounge": "loungewear",
        "recovery": "loungewear",
        "sleep": "loungewear",
    }
    for keyword, category in category_map.items():
        if keyword in lower_query:
            constraints["category"] = category
            break

    subcategory_map = {
        "thong": "thong",
        "short": "boyshort",
        "tee": "t-shirt",
        "shirt": "t-shirt",
    }
    for keyword, subcategory in subcategory_map.items():
        if keyword in lower_query:
            constraints["subcategory"] = subcategory
            break

    for activity in [
        "running",
        "lifting",
        "cycling",
        "jumping",
        "yoga",
        "pilates",
        "walking",
        "sleep",
        "lounge",
        "recovery",
    ]:
        if activity in lower_query:
            constraints["activities"].append(activity)

    if "women" in lower_query or "woman" in lower_query:
        constraints["gender"] = "women"
    elif "men" in lower_query or "man" in lower_query:
        constraints["gender"] = "men"

    if "canada" in lower_query:
        constraints["ships_to"] = "CA"
    elif "us" in lower_query or "united states" in lower_query:
        constraints["ships_to"] = "US"

    if "organic" in lower_query:
        constraints["keywords"].append("organic")
    if "breathable" in lower_query:
        constraints["keywords"].append("breathable")
    if "soft" in lower_query:
        constraints["keywords"].append("soft")

    return constraints


def merge_constraints(
    natural_query: str | None,
    explicit_constraints: dict[str, Any],
) -> dict[str, Any]:
    merged = parse_query(natural_query or "")
    for key, value in explicit_constraints.items():
        if value in (None, "", [], {}):
            continue
        if key == "activities":
            merged.setdefault("activities", [])
            merged["activities"] = list(dict.fromkeys([*merged["activities"], *value]))
        else:
            merged[key] = value
    return merged


def score_product(
    product: Product,
    merchant: Merchant,
    constraints: dict[str, Any],
    campaign: Campaign | None,
) -> tuple[float, str]:
    if not passes_hard_constraints(product, constraints):
        return 0.0, ""

    activities = product.attributes.get("activities", [])
    features = product.attributes.get("key_features", [])
    score_components = {
        "fit": 0.0,
        "price": 0.0,
        "trust": min(merchant.trust_score, 100.0),
        "freshness": freshness_score(product),
        "campaign_boost": 18.0 if campaign and campaign.status == "active" else 0.0,
    }
    matched_reasons: list[str] = []

    if constraints.get("category") and product.category == constraints["category"]:
        score_components["fit"] += 34.0
        matched_reasons.append(product.category.replace("_", " "))
    elif not constraints.get("category"):
        score_components["fit"] += 18.0

    if constraints.get("subcategory") and product.subcategory == constraints["subcategory"]:
        score_components["fit"] += 22.0
        matched_reasons.append(product.subcategory.replace("_", " "))

    requested_activities = constraints.get("activities", [])
    overlap = len(set(requested_activities).intersection(activities))
    if requested_activities:
        score_components["fit"] += overlap * 11.0
        if overlap:
            matched_reasons.append(f"built for {', '.join(requested_activities[:2])}")
    else:
        score_components["fit"] += 10.0

    if constraints.get("gender") and product.attributes.get("gender") == constraints["gender"]:
        score_components["fit"] += 12.0

    max_price = constraints.get("max_price")
    if max_price:
        price_ratio = min(product.price / max_price, 1.0)
        score_components["price"] = 30.0 * (1.0 - price_ratio * 0.75)
        if product.price <= max_price:
            matched_reasons.append(f"under ${int(max_price)}")
    else:
        score_components["price"] = max(10.0, 34.0 - product.price / 2.2)

    for keyword in constraints.get("keywords", []):
        if keyword in " ".join(features).lower() or keyword in (product.description or "").lower():
            score_components["fit"] += 5.0
            matched_reasons.append(keyword)

    score = (
        score_components["fit"] * 0.40
        + score_components["price"] * 0.30
        + score_components["trust"] * 0.20
        + score_components["freshness"] * 0.10
        + score_components["campaign_boost"]
    )
    reason = ", ".join(dict.fromkeys(matched_reasons[:3])) or "strong structured fit"
    return round(min(score, 99.0), 2), reason


def passes_hard_constraints(product: Product, constraints: dict[str, Any]) -> bool:
    max_price = constraints.get("max_price")
    if max_price and product.price > max_price:
        return False

    required_ship = constraints.get("ships_to")
    ships_to = product.attributes.get("ships_to", [])
    if required_ship and required_ship not in ships_to:
        return False

    requested_category = constraints.get("category")
    if requested_category and product.category and requested_category != product.category:
        if requested_category == "athletic_underwear" and product.category != "athletic_underwear":
            return False

    return True


def freshness_score(product: Product) -> float:
    last_crawled = product.last_crawled
    if last_crawled.tzinfo is None:
        last_crawled = last_crawled.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - last_crawled).days, 0)
    return max(30.0, 100.0 - age_days * 2.5)


def search_products(
    db: Session,
    natural_query: str | None,
    explicit_constraints: dict[str, Any],
    limit: int = 5,
    agent_source: str = "Claude",
    merchant_slug: str | None = None,
    channel: str = "mcp",
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    constraints = merge_constraints(natural_query, explicit_constraints)
    product_query = (
        select(Product)
        .where(Product.status == "active")
        .options(joinedload(Product.merchant))
    )
    if merchant_slug:
        product_query = product_query.join(Merchant).where(Merchant.merchant_slug == merchant_slug)

    products = db.scalars(product_query).all()
    active_campaigns = {
        campaign.merchant_id: campaign
        for campaign in db.scalars(select(Campaign).where(Campaign.status == "active")).all()
    }

    ranked_results = []
    for product in products:
        merchant = product.merchant
        if merchant is None or merchant.status != "active":
            continue
        campaign = active_campaigns.get(product.merchant_id)
        score, reason = score_product(product, merchant, constraints, campaign)
        if score <= 0:
            continue
        ranked_results.append(
            {
                "product": product,
                "merchant": merchant,
                "campaign": campaign,
                "score": score,
                "reason": reason,
            }
        )

    ranked_results.sort(key=lambda item: item["score"], reverse=True)
    ranked_results = ranked_results[: max(1, min(limit, 10))]

    query = Query(
        query_text=natural_query,
        constraints=constraints,
        results_count=len(ranked_results),
        agent_source=agent_source,
        channel=channel,
    )
    db.add(query)
    db.flush()

    response_payload = []
    for index, result in enumerate(ranked_results, start=1):
        product = result["product"]
        campaign = result["campaign"]
        compute_cost = round(0.32 + result["score"] * 0.045, 2)
        match = Match(
            query_id=query.id,
            product_id=product.id,
            campaign_id=campaign.id if campaign else None,
            score=result["score"],
            position=index,
            compute_cost=compute_cost,
            channel=channel,
        )
        db.add(match)
        if campaign:
            campaign.budget_spent = round(campaign.budget_spent + compute_cost, 2)

        response_payload.append(
            {
                "product_id": product.id,
                "merchant_id": result["merchant"].id,
                "merchant_slug": result["merchant"].merchant_slug,
                "merchant_name": result["merchant"].name or "Merchant",
                "name": product.name,
                "price": product.price,
                "currency": product.currency,
                "category": product.category,
                "subcategory": product.subcategory,
                "score": result["score"],
                "reason": result["reason"],
                "images": product.images,
                "source_url": product.source_url,
                "redirect_url": f"{settings.public_api_url}/go/{product.id}?q={query.id}",
            }
        )

    db.commit()
    return query.id, constraints, response_payload
