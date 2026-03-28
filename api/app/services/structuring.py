from __future__ import annotations

import re
from typing import Any

from app.services.seeding import get_demo_products


def structure_products(raw_products: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    demo_lookup = {product["name"].lower(): product for product in get_demo_products(domain)}
    structured: list[dict[str, Any]] = []
    for raw_product in raw_products:
        name = raw_product.get("name", "").strip()
        if name.lower() in demo_lookup:
            structured.append(demo_lookup[name.lower()].copy())
            continue
        structured.append(structure_single_product(raw_product))
    return structured


def structure_single_product(raw_product: dict[str, Any]) -> dict[str, Any]:
    title = raw_product.get("name", "")
    description = raw_product.get("description") or ""
    tags = raw_product.get("tags") or []
    lower_blob = " ".join([title, description, " ".join(tags)]).lower()
    category = infer_category(lower_blob)
    subcategory = infer_subcategory(lower_blob)
    activities = infer_activities(lower_blob)
    material = infer_material(lower_blob)
    made_in = infer_country(description)
    sustainability = infer_sustainability(lower_blob)
    key_features = infer_key_features(description, tags)

    return {
        "name": title,
        "source_url": raw_product.get("source_url"),
        "category": category,
        "subcategory": subcategory,
        "price": float(raw_product.get("price", 0) or 0),
        "currency": raw_product.get("currency", "USD"),
        "description": description,
        "images": raw_product.get("images", []),
        "attributes": {
            "material": material,
            "activities": activities,
            "gender": infer_gender(lower_blob),
            "sizes": raw_product.get("sizes", []),
            "ships_to": raw_product.get("ships_to", ["US"]),
            "free_shipping": "free shipping" in lower_blob,
            "made_in": made_in,
            "key_features": key_features,
            "target_customer": infer_target_customer(category, activities),
            "sustainability_indicators": sustainability,
        },
    }


def infer_category(blob: str) -> str:
    if any(keyword in blob for keyword in ["underwear", "thong", "brief"]):
        return "athletic_underwear"
    if any(keyword in blob for keyword in ["lounge", "sleep", "recovery", "tee", "shirt", "short"]):
        return "loungewear"
    return "apparel"


def infer_subcategory(blob: str) -> str:
    mapping = {
        "thong": "thong",
        "brief": "brief",
        "short": "shorts",
        "boyshort": "boyshort",
        "tee": "t-shirt",
        "t-shirt": "t-shirt",
        "shirt": "t-shirt",
    }
    for keyword, label in mapping.items():
        if keyword in blob:
            return label
    return "general"


def infer_material(blob: str) -> str:
    mapping = {
        "organic cotton": "organic_cotton",
        "cotton": "cotton",
        "modal": "modal_blend",
        "mesh": "mesh_woven",
        "nylon": "nylon_spandex",
        "spandex": "nylon_spandex",
    }
    for keyword, label in mapping.items():
        if keyword in blob:
            return label
    return "unspecified"


def infer_activities(blob: str) -> list[str]:
    keywords = [
        "running",
        "yoga",
        "pilates",
        "lifting",
        "cycling",
        "walking",
        "sleep",
        "lounge",
        "recovery",
        "jumping",
    ]
    activities = [keyword for keyword in keywords if keyword in blob]
    return activities or ["everyday"]


def infer_gender(blob: str) -> str:
    if "men" in blob and "women" not in blob:
        return "men"
    if "unisex" in blob:
        return "unisex"
    return "women"


def infer_sustainability(blob: str) -> list[str]:
    signals = []
    for keyword in ["organic", "recycled", "sustainable", "eco", "made in canada"]:
        if keyword in blob:
            signals.append(keyword.replace(" ", "_"))
    return signals


def infer_country(text: str) -> str | None:
    match = re.search(r"made in ([A-Za-z ]+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def infer_key_features(description: str, tags: list[str]) -> list[str]:
    features = []
    description_blob = description.lower()
    candidates = {
        "breathable": "breathable",
        "sweat": "sweat-wicking",
        "stretch": "4-way stretch",
        "soft": "ultra-soft feel",
        "recovery": "recovery-focused",
        "stays in place": "stays in place",
        "organic": "organic fibers",
    }
    for keyword, label in candidates.items():
        if keyword in description_blob and label not in features:
            features.append(label)
    for tag in tags[:3]:
        clean_tag = tag.replace("_", " ").strip()
        if clean_tag and clean_tag not in features:
            features.append(clean_tag)
    return features[:5] or ["premium essentials", "agent-ready catalog data", "clear product positioning"]


def infer_target_customer(category: str, activities: list[str]) -> str:
    activity_text = ", ".join(activities[:3])
    return f"Shoppers looking for {category.replace('_', ' ')} tuned for {activity_text}."
