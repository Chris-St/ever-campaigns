from __future__ import annotations

import json
import os
import tempfile


temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{temp_db.name}"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.openclaw_runtime import (  # noqa: E402
    campaign_manifest_path,
    campaign_runtime_config_path,
    campaign_runtime_skill_path,
)


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
    create_campaign_json = create_campaign.json()
    campaign_id = create_campaign_json["id"]
    agent_api_key = create_campaign_json["agent_endpoints"]["openclaw"]["api_key"]
    assert create_campaign_json["status"] == "pending_payment"
    assert agent_api_key.startswith("ek_live_")

    checkout = client.post(
        "/billing/create-checkout",
        json={"campaign_id": campaign_id},
        headers=headers,
    )
    assert checkout.status_code == 200
    assert checkout.json()["activated"] is True

    overview = client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert overview.status_code == 200
    overview_json = overview.json()
    assert overview_json["status"] == "active"
    assert overview_json["merchant_slug"] == merchant_slug
    assert overview_json["revenue"] > 0
    assert overview_json["agent_endpoints"]["mcp"]["public_url"].endswith(f"/{merchant_slug}")
    assert overview_json["agent_endpoints"]["openclaw"]["api_key"] is None
    assert overview_json["agent_endpoints"]["openclaw"]["api_key_preview"].startswith("ek_live_****")

    listener_status = client.get(f"/campaigns/{campaign_id}/listener/status", headers=headers)
    assert listener_status.status_code == 200
    assert listener_status.json()["status"] == "stopped"
    assert listener_status.json()["surfaces_active_count"] >= 2

    started_listener = client.post(f"/campaigns/{campaign_id}/listener/start", headers=headers)
    assert started_listener.status_code == 200
    started_listener_json = started_listener.json()
    assert started_listener_json["status"] == "running"
    assert started_listener_json["surfaces_active_count"] >= 2

    manifest_path = campaign_manifest_path(campaign_id)
    runtime_config_path = campaign_runtime_config_path(campaign_id)
    runtime_skill_path = campaign_runtime_skill_path(campaign_id)
    assert manifest_path.exists()
    assert runtime_config_path.exists()
    assert runtime_skill_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "test-mode"
    assert manifest["config_path"] == str(runtime_config_path)
    runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    assert runtime_config["api_key"] == agent_api_key

    agent_headers = {"Authorization": f"Bearer {agent_api_key}"}
    agent_config = client.get(
        f"/api/campaigns/{campaign_id}/agent-config",
        headers=agent_headers,
    )
    assert agent_config.status_code == 200
    agent_config_json = agent_config.json()
    assert agent_config_json["campaign_id"] == campaign_id
    assert agent_config_json["reporting"]["api_key"] == agent_api_key
    assert agent_config_json["surfaces"]["reddit"]["enabled"] is True
    product_id = agent_config_json["products"][0]["id"]

    intent_detected = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "intent_detected",
            "surface": "reddit",
            "source_url": "https://reddit.com/r/running/comments/test123",
            "source_content": "What underwear doesn't chafe on long runs?",
            "source_author": "u/runner_jane",
            "source_context": "Thread about marathon training gear",
            "intent_score": {
                "relevance": 85,
                "intent": 72,
                "fit": 90,
                "receptivity": 80,
                "composite": 82,
            },
            "action_taken": "skip",
            "response_text": None,
            "referral_url": None,
            "product_id": product_id,
            "tokens_used": 620,
            "compute_cost_usd": 0.0046,
            "timestamp": "2026-03-28T14:30:00Z",
        },
    )
    assert intent_detected.status_code == 200
    assert intent_detected.json()["status"] == "recorded"

    response_posted = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "response_posted",
            "surface": "reddit",
            "source_url": "https://reddit.com/r/running/comments/test123",
            "source_content": "What underwear doesn't chafe on long runs?",
            "source_author": "u/runner_jane",
            "source_context": "Thread about marathon training gear",
            "intent_score": {
                "relevance": 85,
                "intent": 72,
                "fit": 90,
                "receptivity": 80,
                "composite": 82,
            },
            "action_taken": "reply",
            "response_text": "If the goal is comfort during movement, breathable and stay-put matters most. Bia's High Movement Thong is built for running and dries fast. I'm an AI agent for Bia (via Ever).",
            "referral_url": f"http://localhost:8000/go/{product_id}?src=reddit&cid={campaign_id}&iid=reply_evt_1",
            "product_id": product_id,
            "tokens_used": 1150,
            "compute_cost_usd": 0.0082,
            "timestamp": "2026-03-28T14:34:00Z",
        },
    )
    assert response_posted.status_code == 200
    assert response_posted.json()["status"] == "recorded"
    assert response_posted.json()["budget_remaining"] < 2400

    response_skipped = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "response_skipped",
            "surface": "twitter",
            "source_url": "https://x.com/everagent/status/abc123?query=best%20athletic%20thong",
            "source_content": "best athletic thong for hot yoga and walking all day?",
            "source_author": "@studionotes",
            "source_context": "Looking for something breathable and soft",
            "intent_score": {
                "relevance": 74,
                "intent": 68,
                "fit": 61,
                "receptivity": 55,
                "composite": 66,
            },
            "action_taken": "skip",
            "response_text": None,
            "referral_url": None,
            "product_id": product_id,
            "tokens_used": 540,
            "compute_cost_usd": 0.0035,
            "timestamp": "2026-03-28T15:00:00Z",
        },
    )
    assert response_skipped.status_code == 200

    updated_listener_status = client.get(
        f"/campaigns/{campaign_id}/listener/status",
        headers=headers,
    )
    assert updated_listener_status.status_code == 200
    updated_listener_status_json = updated_listener_status.json()
    assert updated_listener_status_json["status"] == "running"
    assert updated_listener_status_json["signals_today"] >= 2
    assert updated_listener_status_json["responses_today"] >= 1
    assert updated_listener_status_json["last_active"] is not None

    redirect = client.get(
        f"/go/{product_id}?src=reddit&iid=reply_evt_1",
        follow_redirects=False,
    )
    assert redirect.status_code in {302, 307}

    conversion = client.post(
        "/webhooks/shopify/order",
        json={
            "campaign_id": campaign_id,
            "product_id": product_id,
            "order_value": 32.0,
        },
    )
    assert conversion.status_code == 200
    assert conversion.json()["status"] == "recorded"

    listener_analytics = client.get(
        f"/campaigns/{campaign_id}/listener/analytics?period=30d",
        headers=headers,
    )
    assert listener_analytics.status_code == 200
    listener_analytics_json = listener_analytics.json()
    assert listener_analytics_json["signals_detected"] >= 2
    assert listener_analytics_json["responses_sent"] >= 1
    assert listener_analytics_json["clicks"] >= 1
    assert listener_analytics_json["conversions"] >= 1
    assert listener_analytics_json["revenue"] >= 32.0
    assert listener_analytics_json["compute_cost"] > 0
    assert any(
        item["subreddit_or_channel"] == "running"
        for item in listener_analytics_json["top_surfaces"]
    )
    assert any(
        item["subreddit_or_channel"] == "best athletic thong"
        for item in listener_analytics_json["top_surfaces"]
    )
    assert len(listener_analytics_json["daily_series"]) >= 1

    response_activity = client.get(
        f"/campaigns/{campaign_id}/activity?limit=20&event_type=response",
        headers=headers,
    )
    assert response_activity.status_code == 200
    assert any(entry["event_type"] == "response" for entry in response_activity.json())

    match_activity = client.get(
        f"/campaigns/{campaign_id}/activity?limit=20&event_type=match",
        headers=headers,
    )
    assert match_activity.status_code == 200
    assert any(entry["channel"] == "intent_listener" for entry in match_activity.json())

    review_queue = client.get(f"/campaigns/{campaign_id}/review", headers=headers)
    assert review_queue.status_code == 200
    assert review_queue.json() == []

    regenerated_key = client.post(
        f"/campaigns/{campaign_id}/agent-key/regenerate",
        headers=headers,
    )
    assert regenerated_key.status_code == 200
    regenerated_key_json = regenerated_key.json()
    assert regenerated_key_json["api_key"] != agent_api_key
    assert regenerated_key_json["api_key_preview"].startswith("ek_live_****")

    old_key_config = client.get(
        f"/api/campaigns/{campaign_id}/agent-config",
        headers=agent_headers,
    )
    assert old_key_config.status_code == 401

    new_agent_headers = {"Authorization": f"Bearer {regenerated_key_json['api_key']}"}
    new_key_config = client.get(
        f"/api/campaigns/{campaign_id}/agent-config",
        headers=new_agent_headers,
    )
    assert new_key_config.status_code == 200

    endpoints = client.get(f"/campaigns/{campaign_id}/endpoints", headers=headers)
    assert endpoints.status_code == 200
    endpoints_json = endpoints.json()
    assert endpoints_json["merchant_slug"] == merchant_slug
    assert endpoints_json["openclaw"]["api_key"] is None
    assert endpoints_json["openclaw"]["api_key_preview"].endswith(
        regenerated_key_json["api_key"][-4:]
    )

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
