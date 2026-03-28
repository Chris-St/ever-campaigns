from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import Campaign, Click, Conversion, Match, Merchant, Product, Query


def make_svg_data_uri(title: str, accent: str, secondary: str) -> str:
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 720'>
      <defs>
        <linearGradient id='bg' x1='0' x2='1' y1='0' y2='1'>
          <stop offset='0%' stop-color='{accent}' />
          <stop offset='100%' stop-color='{secondary}' />
        </linearGradient>
      </defs>
      <rect width='720' height='720' rx='64' fill='url(#bg)' />
      <circle cx='540' cy='168' r='124' fill='rgba(255,255,255,0.18)' />
      <path d='M120 460C236 332 356 268 558 296' fill='none' stroke='rgba(255,255,255,0.34)' stroke-width='28' stroke-linecap='round' />
      <text x='64' y='578' fill='white' font-size='40' font-family='Arial, Helvetica, sans-serif'>EVER x BIA</text>
      <text x='64' y='646' fill='white' font-size='60' font-weight='700' font-family='Arial, Helvetica, sans-serif'>{title}</text>
    </svg>
    """
    return f"data:image/svg+xml;utf8,{quote(svg)}"


DEMO_BIA_PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "High Movement Thong",
        "price": 32.0,
        "currency": "CAD",
        "category": "athletic_underwear",
        "subcategory": "thong",
        "description": (
            "A high-intensity performance thong built for running, lifting, cycling, "
            "and jumping with breathable mesh support."
        ),
        "source_url": "https://biaundies.com/products/high-movement-thong",
        "images": [make_svg_data_uri("High Movement Thong", "#0F766E", "#0F172A")],
        "attributes": {
            "material": "mesh_woven",
            "activities": ["running", "lifting", "cycling", "jumping"],
            "gender": "women",
            "sizes": ["S", "M", "L", "XL"],
            "ships_to": ["CA", "US"],
            "free_shipping": True,
            "made_in": "Canada",
            "key_features": [
                "4-way stretch",
                "stays in place during high-intensity movement",
                "sweat-wicking",
                "breathable",
            ],
            "target_customer": "Women looking for secure, breathable underwear during intense workouts.",
            "sustainability_indicators": ["made_in_canada"],
        },
    },
    {
        "name": "Supersoft Thong",
        "price": 30.0,
        "currency": "CAD",
        "category": "athletic_underwear",
        "subcategory": "thong",
        "description": (
            "An ultra-soft thong tuned for yoga, pilates, walking, and low-intensity days "
            "with a graceful fit."
        ),
        "source_url": "https://biaundies.com/products/supersoft-thong",
        "images": [make_svg_data_uri("Supersoft Thong", "#155E75", "#1E293B")],
        "attributes": {
            "material": "modal_blend",
            "activities": ["yoga", "pilates", "walking", "low-intensity"],
            "gender": "women",
            "sizes": ["S", "M", "L", "XL"],
            "ships_to": ["CA", "US"],
            "free_shipping": True,
            "made_in": "Canada",
            "key_features": [
                "ultra-soft hand feel",
                "graceful fit",
                "flows with movement",
                "optimized for low intensity",
            ],
            "target_customer": "Women who want comfort-first performance underwear for low-impact routines.",
            "sustainability_indicators": ["made_in_canada"],
        },
    },
    {
        "name": "Recovery Shorts",
        "price": 38.0,
        "currency": "CAD",
        "category": "loungewear",
        "subcategory": "boyshort",
        "description": "Soft organic-cotton recovery shorts designed for sleep, lounge, and recovery days.",
        "source_url": "https://biaundies.com/products/recovery-shorts",
        "images": [make_svg_data_uri("Recovery Shorts", "#7C2D12", "#0F172A")],
        "attributes": {
            "material": "organic_cotton",
            "activities": ["sleep", "lounge", "recovery"],
            "gender": "women",
            "sizes": ["S", "M", "L", "XL"],
            "ships_to": ["CA", "US"],
            "free_shipping": True,
            "made_in": "Canada",
            "key_features": [
                "comfortable boyshort cut",
                "designed for rest and recovery",
                "soft organic cotton",
            ],
            "target_customer": "Women looking for elevated recovery essentials and premium comfort.",
            "sustainability_indicators": ["organic", "made_in_canada"],
        },
    },
    {
        "name": "The Recovery T",
        "price": 42.0,
        "currency": "CAD",
        "category": "loungewear",
        "subcategory": "t-shirt",
        "description": "A laid-back recovery tee with a soft, organic-cotton feel for lounge and sleep.",
        "source_url": "https://biaundies.com/products/the-recovery-t",
        "images": [make_svg_data_uri("The Recovery T", "#9A3412", "#1E293B")],
        "attributes": {
            "material": "organic_cotton",
            "activities": ["sleep", "lounge", "recovery"],
            "gender": "women",
            "sizes": ["S", "M", "L", "XL"],
            "ships_to": ["CA", "US"],
            "free_shipping": True,
            "made_in": "Canada",
            "key_features": [
                "laid-back feel",
                "recovery-focused silhouette",
                "simple and comfortable",
            ],
            "target_customer": "Women who want premium basics for slower days and recovery rituals.",
            "sustainability_indicators": ["organic", "made_in_canada"],
        },
    },
]


def get_demo_products(domain: str) -> list[dict[str, Any]]:
    if "biaundies.com" in domain:
        return DEMO_BIA_PRODUCTS
    return []


def sync_products_for_merchant(
    db: Session,
    merchant: Merchant,
    structured_products: list[dict[str, Any]],
) -> list[Product]:
    existing_products = {
        (product.source_url or product.name).lower(): product
        for product in merchant.products
    }
    seen_keys: set[str] = set()
    synced: list[Product] = []

    for payload in structured_products:
        lookup_key = (payload.get("source_url") or payload["name"]).lower()
        seen_keys.add(lookup_key)
        product = existing_products.get(lookup_key)
        if product is None:
            product = Product(merchant_id=merchant.id)
            db.add(product)

        product.source_url = payload.get("source_url")
        product.name = payload["name"]
        product.category = payload.get("category")
        product.subcategory = payload.get("subcategory")
        product.price = float(payload["price"])
        product.currency = payload.get("currency", "USD")
        product.description = payload.get("description")
        product.attributes = payload.get("attributes", {})
        product.images = payload.get("images", [])
        product.status = payload.get("status", "active")
        product.last_crawled = datetime.now(timezone.utc)
        synced.append(product)

    for lookup_key, product in existing_products.items():
        if lookup_key not in seen_keys:
            product.status = "inactive"

    db.flush()
    return synced


def seed_campaign_activity(db: Session, campaign: Campaign) -> None:
    existing_match = db.scalar(select(Match).where(Match.campaign_id == campaign.id).limit(1))
    if existing_match is not None:
        return

    merchant = db.scalar(
        select(Merchant)
        .where(Merchant.id == campaign.merchant_id)
        .options(joinedload(Merchant.products))
    )
    if merchant is None:
        return

    active_products = [product for product in merchant.products if product.status == "active"]
    if not active_products:
        return

    rng = random.Random(campaign.id)
    now = datetime.now(timezone.utc)
    target_spend = campaign.budget_monthly * (0.44 + rng.random() * 0.22)
    product_weights = {
        "High Movement Thong": 0.42,
        "Supersoft Thong": 0.31,
        "Recovery Shorts": 0.16,
        "The Recovery T": 0.11,
    }
    product_lookup = {product.name: product for product in active_products}
    weighted_products = [
        product_lookup[name]
        for name in product_weights
        if name in product_lookup
    ] or active_products
    weights = [product_weights.get(product.name, 0.2) for product in weighted_products]
    query_bank = [
        "athletic underwear for running under $40 in Canada",
        "women's breathable thong for cycling",
        "comfortable underwear for lifting workouts",
        "soft underwear for yoga and pilates",
        "recovery loungewear made in Canada",
        "organic cotton sleep shorts for women",
        "performance thong with sweat wicking",
        "premium lounge tee for recovery days",
        "best workout underwear that stays in place",
        "low-intensity underwear for walking and yoga",
    ]
    agents = ["Claude", "ChatGPT", "Gemini", "Perplexity"]

    curve = []
    for day in range(30):
        rhythm = 1 + 0.18 * math.sin(day / 30 * math.pi * 2)
        curve.append(rhythm + rng.uniform(-0.08, 0.18))
    curve_total = sum(curve)

    total_spend = 0.0
    for day_index, weight in enumerate(curve):
        day_spend = round(target_spend * weight / curve_total, 2)
        day_timestamp = now - timedelta(days=29 - day_index)
        match_count = rng.randint(6, 10)
        base_cost = max(day_spend / match_count, 0.7)

        for position_seed in range(match_count):
            product = rng.choices(weighted_products, weights=weights, k=1)[0]
            query_text = rng.choice(query_bank)
            query = Query(
                query_text=query_text,
                constraints={},
                results_count=1,
                agent_source=rng.choice(agents),
                channel="mcp",
                created_at=day_timestamp + timedelta(minutes=position_seed * 9),
            )
            db.add(query)
            db.flush()

            match = Match(
                query_id=query.id,
                product_id=product.id,
                campaign_id=campaign.id,
                score=round(74 + rng.random() * 24, 2),
                position=1,
                compute_cost=round(base_cost * rng.uniform(0.82, 1.18), 2),
                channel="mcp",
                created_at=query.created_at,
            )
            db.add(match)
            total_spend += match.compute_cost
            db.flush()

            if rng.random() < 0.76:
                click = Click(
                    match_id=match.id,
                    product_id=product.id,
                    campaign_id=campaign.id,
                    channel="mcp",
                    created_at=match.created_at + timedelta(minutes=rng.randint(1, 48)),
                )
                db.add(click)
                db.flush()

                conversion_lift = 0.72 if product.name == "High Movement Thong" else 0.56
                if rng.random() < conversion_lift:
                    order_multiplier = 1.0 if "Thong" in product.name else 1.25
                    conversion = Conversion(
                        click_id=click.id,
                        product_id=product.id,
                        campaign_id=campaign.id,
                        order_value=round(product.price * order_multiplier, 2),
                        channel="mcp",
                        created_at=click.created_at + timedelta(minutes=rng.randint(3, 180)),
                    )
                    db.add(conversion)

    campaign.budget_spent = round(total_spend, 2)
    db.commit()
