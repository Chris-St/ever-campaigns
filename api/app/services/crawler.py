from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.seeding import get_demo_products


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned.rstrip("/")


def domain_from_url(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    return parsed.netloc.lower().removeprefix("www.")


def merchant_name_from_domain(domain: str) -> str:
    if "biaundies.com" in domain:
        return "Bia"
    return domain.split(".")[0].replace("-", " ").title()


def scan_store(url: str) -> dict[str, Any]:
    normalized = normalize_url(url)
    domain = domain_from_url(normalized)
    with httpx.Client(
        timeout=12.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        raw_products = crawl_shopify_products(client, normalized)
        if not raw_products:
            raw_products = crawl_html_fallback(client, normalized)

    if not raw_products:
        demo_products = get_demo_products(domain)
        raw_products = [
            {
                "name": product["name"],
                "description": product["description"],
                "price": product["price"],
                "currency": product["currency"],
                "source_url": product["source_url"],
                "images": product["images"],
                "tags": product["attributes"].get("activities", []),
                "ships_to": product["attributes"].get("ships_to", ["US"]),
                "sizes": product["attributes"].get("sizes", []),
            }
            for product in demo_products
        ]

    return {
        "domain": domain,
        "name": merchant_name_from_domain(domain),
        "platform": "shopify",
        "ships_to": ["CA", "US"] if "biaundies.com" in domain else ["US"],
        "raw_products": raw_products,
    }


def crawl_shopify_products(client: httpx.Client, base_url: str) -> list[dict[str, Any]]:
    endpoint = f"{base_url}/products.json?limit=250"
    try:
        response = client.get(endpoint)
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    payload = response.json()
    products = payload.get("products", [])
    extracted = []
    for product in products:
        variants = product.get("variants") or []
        images = product.get("images") or []
        primary_variant = variants[0] if variants else {}
        extracted.append(
            {
                "name": product.get("title"),
                "description": product.get("body_html", ""),
                "price": primary_variant.get("price", 0),
                "currency": primary_variant.get("presentment_prices", [{}])[0]
                .get("price", {})
                .get("currency_code", "USD"),
                "source_url": urljoin(base_url, f"/products/{product.get('handle')}"),
                "images": [image.get("src") for image in images if image.get("src")],
                "tags": [tag.strip() for tag in (product.get("tags") or "").split(",") if tag.strip()],
                "ships_to": ["US"],
                "sizes": [variant.get("option1") for variant in variants if variant.get("option1")],
            }
        )
    return extracted


def crawl_html_fallback(client: httpx.Client, base_url: str) -> list[dict[str, Any]]:
    try:
        response = client.get(base_url)
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    products: list[dict[str, Any]] = []
    scripts = soup.select("script[type='application/ld+json']")
    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        products.extend(extract_ld_products(data, base_url))
    deduped = []
    seen = set()
    for product in products:
        key = (product.get("source_url") or product.get("name") or "").lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(product)
    return deduped


def extract_ld_products(payload: Any, base_url: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        products: list[dict[str, Any]] = []
        for entry in payload:
            products.extend(extract_ld_products(entry, base_url))
        return products

    if isinstance(payload, dict):
        if payload.get("@type") == "Product":
            offers = payload.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            image_value = payload.get("image") or []
            images = image_value if isinstance(image_value, list) else [image_value]
            return [
                {
                    "name": payload.get("name"),
                    "description": payload.get("description", ""),
                    "price": offers.get("price", 0),
                    "currency": offers.get("priceCurrency", "USD"),
                    "source_url": urljoin(base_url, payload.get("url", "")),
                    "images": images,
                    "tags": [],
                    "ships_to": ["US"],
                    "sizes": [],
                }
            ]
        nested_products: list[dict[str, Any]] = []
        for value in payload.values():
            nested_products.extend(extract_ld_products(value, base_url))
        return nested_products

    return []
