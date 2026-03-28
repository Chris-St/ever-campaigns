from __future__ import annotations

import os
import tempfile


temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{temp_db.name}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db.session import init_db  # noqa: E402


def test_full_flow() -> None:
    init_db()
    client = TestClient(app)

    signup = client.post(
        "/auth/signup",
        json={"email": "founder@ever.com", "password": "testpass123"},
    )
    assert signup.status_code == 200
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    scan = client.post("/stores/scan", json={"url": "https://biaundies.com"}, headers=headers)
    assert scan.status_code == 200
    merchant_id = scan.json()["merchant_id"]
    merchant_slug = scan.json()["merchant_slug"]
    assert len(scan.json()["products"]) >= 4

    create_campaign = client.post(
        "/campaigns/create",
        json={"merchant_id": merchant_id, "budget_monthly": 2400, "auto_optimize": True},
        headers=headers,
    )
    assert create_campaign.status_code == 200
    campaign_id = create_campaign.json()["id"]
    assert create_campaign.json()["status"] == "pending_payment"

    checkout = client.post(
        "/billing/create-checkout",
        json={"campaign_id": campaign_id},
        headers=headers,
    )
    assert checkout.status_code == 200
    assert checkout.json()["activated"] is True

    overview = client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["status"] == "active"
    assert overview.json()["merchant_slug"] == merchant_slug
    assert overview.json()["revenue"] > 0
    assert overview.json()["agent_endpoints"]["mcp"]["public_url"].endswith(f"/{merchant_slug}")

    endpoints = client.get(f"/campaigns/{campaign_id}/endpoints", headers=headers)
    assert endpoints.status_code == 200
    assert endpoints.json()["merchant_slug"] == merchant_slug

    products = client.get(f"/campaigns/{campaign_id}/products", headers=headers)
    assert products.status_code == 200
    assert len(products.json()) >= 4

    mcp_search = client.post(
        "/mcp/all/tools/search_products",
        json={"query": "breathable running thong under $40 in Canada"},
    )
    assert mcp_search.status_code == 200
    assert mcp_search.json()["scope"] == "all"
    assert len(mcp_search.json()["results"]) >= 1

    scoped_search = client.post(
        f"/mcp/{merchant_slug}/tools/search_products",
        json={"query": "breathable running thong under $40 in Canada"},
    )
    assert scoped_search.status_code == 200
    assert scoped_search.json()["scope"] == merchant_slug
    assert all(
        result["merchant_slug"] == merchant_slug for result in scoped_search.json()["results"]
    )

    scoped_catalog = client.get(f"/mcp/{merchant_slug}/tools/get_catalog?limit=10")
    assert scoped_catalog.status_code == 200
    assert scoped_catalog.json()["scope"] == merchant_slug
    assert len(scoped_catalog.json()["products"]) >= 4

    acp_feed = client.get(f"/feeds/{merchant_id}/acp.jsonl.gz")
    assert acp_feed.status_code == 200
    assert acp_feed.headers["content-type"] == "application/gzip"

    acp_preview = client.get(f"/feeds/{merchant_id}/acp-preview.json")
    assert acp_preview.status_code == 200
    assert len(acp_preview.json()["products"]) >= 4

    ucp_feed = client.get(f"/feeds/{merchant_id}/ucp.json")
    assert ucp_feed.status_code == 200
    assert len(ucp_feed.json()["products"]) >= 4
