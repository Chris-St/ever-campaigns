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

    listener_status = client.get(f"/campaigns/{campaign_id}/listener/status", headers=headers)
    assert listener_status.status_code == 200
    assert listener_status.json()["status"] == "stopped"
    assert listener_status.json()["surfaces_active"] >= 2

    listener_payload = listener_status.json()
    listener_payload["brand_voice_profile"]["tone"] = "Helpful, premium, and direct"
    listener_payload["config"]["review_mode"] = "auto"
    updated_listener = client.put(
        f"/campaigns/{campaign_id}/listener/config",
        json={
            "brand_voice_profile": listener_payload["brand_voice_profile"],
            "config": listener_payload["config"],
        },
        headers=headers,
    )
    assert updated_listener.status_code == 200
    assert updated_listener.json()["config"]["review_mode"] == "auto"

    started_listener = client.post(f"/campaigns/{campaign_id}/listener/start", headers=headers)
    assert started_listener.status_code == 200
    assert started_listener.json()["status"] == "running"
    assert started_listener.json()["approved_response_count"] > 0

    review_queue = client.get(f"/campaigns/{campaign_id}/review", headers=headers)
    assert review_queue.status_code == 200
    assert len(review_queue.json()) >= 1
    review_item = review_queue.json()[0]

    edited_review = client.post(
        f"/campaigns/{campaign_id}/review/{review_item['response_id']}/edit",
        json={"response_text": f"{review_item['response_text']} Edited."},
        headers=headers,
    )
    assert edited_review.status_code == 200
    assert edited_review.json()["response_text"].endswith("Edited.")

    approved_review = client.post(
        f"/campaigns/{campaign_id}/review/{review_item['response_id']}/approve",
        headers=headers,
    )
    assert approved_review.status_code == 200
    assert approved_review.json()["review_status"] == "approved"

    listener_analytics = client.get(
        f"/campaigns/{campaign_id}/listener/analytics?period=30d",
        headers=headers,
    )
    assert listener_analytics.status_code == 200
    assert listener_analytics.json()["signals_detected"] > 0
    assert listener_analytics.json()["responses_sent"] > 0
    assert len(listener_analytics.json()["top_surfaces"]) >= 1

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

    stopped_listener = client.post(f"/campaigns/{campaign_id}/listener/stop", headers=headers)
    assert stopped_listener.status_code == 200
    assert stopped_listener.json()["status"] == "stopped"
