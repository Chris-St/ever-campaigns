from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Merchant


def slugify_merchant(name: str | None, domain: str) -> str:
    source = (name or domain.split(".")[0] or "merchant").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", source)
    slug = slug.strip("-")
    return slug or "merchant"


def assign_merchant_slug(db: Session, merchant: Merchant) -> str:
    if merchant.merchant_slug:
        return merchant.merchant_slug

    base_slug = slugify_merchant(merchant.name, merchant.domain)
    slug = base_slug
    counter = 2

    while db.scalar(
        select(Merchant).where(
            Merchant.merchant_slug == slug,
            Merchant.id != merchant.id,
        )
    ):
        slug = f"{base_slug}-{counter}"
        counter += 1

    merchant.merchant_slug = slug
    db.flush()
    return slug


def build_agent_endpoints(campaign) -> dict:
    merchant = campaign.merchant
    merchant_slug = merchant.merchant_slug or slugify_merchant(merchant.name, merchant.domain)
    public_mcp_url = f"https://mcp.ever.com/{merchant_slug}"
    local_mcp_url = f"{settings.public_api_url}/mcp/{merchant_slug}"
    global_public_mcp_url = "https://mcp.ever.com/all"
    local_global_mcp_url = f"{settings.public_api_url}/mcp/all"
    mcp_live = campaign.status == "active"
    live_label = "Live" if mcp_live else "Paused"
    connected_surfaces = (
        f"MCP ({live_label}) | ACP (Coming Soon) | UCP (Coming Soon)"
    )

    return {
        "merchant_slug": merchant_slug,
        "connected_surfaces": connected_surfaces,
        "summary": (
            "Right now, your products are live on MCP. ACP and UCP feeds are generated and "
            "ready, but submission remains pending until those integrations ship."
        ),
        "mcp": {
            "status": "live" if mcp_live else "paused",
            "label": live_label,
            "badge": "Live" if mcp_live else "Paused",
            "public_url": public_mcp_url,
            "preview_url": local_mcp_url,
            "global_public_url": global_public_mcp_url,
            "global_preview_url": local_global_mcp_url,
            "description": (
                "Any AI agent can connect to this MCP server to discover and query your products."
            ),
            "quick_test_prompt": (
                "Try asking Claude to search this MCP server for your top product category."
            ),
        },
        "acp": {
            "status": "pending",
            "label": "Pending",
            "badge": "Coming Soon",
            "description": (
                "Your ACP feed is generated and ready, pending Agentic Commerce Protocol submission."
            ),
            "feed_url": f"{settings.public_api_url}/feeds/{merchant.id}/acp.jsonl.gz",
            "preview_url": f"{settings.public_api_url}/feeds/{merchant.id}/acp-preview.json",
        },
        "ucp": {
            "status": "pending",
            "label": "Pending",
            "badge": "Coming Soon",
            "description": (
                "Your UCP feed is generated and ready, pending Universal Commerce Protocol submission."
            ),
            "feed_url": f"{settings.public_api_url}/feeds/{merchant.id}/ucp.json",
            "preview_url": f"{settings.public_api_url}/feeds/{merchant.id}/ucp-preview.json",
        },
    }
