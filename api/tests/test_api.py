from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone


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
    now = datetime.now(timezone.utc)
    research_timestamp = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    action_timestamp = (now - timedelta(minutes=22)).isoformat().replace("+00:00", "Z")
    strategy_timestamp = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    brand_context_profile = {
        "positioning": "Bia makes premium movement essentials for women who care about fit, comfort, and quality.",
        "ideal_customer": "Women who want premium underwear for running, training, and recovery.",
        "key_messages": [
            "Lead with fit and comfort during movement.",
            "Stay premium and useful, never discount-driven.",
        ],
        "proof_points": [
            "Made in Canada",
            "Designed for high-movement training and recovery days",
        ],
        "objection_handling": [
            "If pricing comes up, justify it through quality and fit instead of discounts.",
        ],
        "prohibited_claims": [
            "Do not make medical claims.",
            "Do not promise discounts unless explicitly configured.",
        ],
        "additional_context": "The founder built Bia after struggling to find underwear that stayed put during training.",
    }

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
    assert listener_status.json()["surfaces_active_count"] == 0
    assert listener_status.json()["config"]["listener_mode"] == "simulation"

    updated_listener = client.put(
        f"/campaigns/{campaign_id}/listener/config",
        headers=headers,
        json={
            "brand_voice_profile": listener_status.json()["brand_voice_profile"],
            "brand_context_profile": brand_context_profile,
            "config": {
                **listener_status.json()["config"],
                "listener_mode": "live",
            },
        },
    )
    assert updated_listener.status_code == 200
    assert updated_listener.json()["config"]["listener_mode"] == "live"
    assert updated_listener.json()["brand_context_profile"]["positioning"].startswith("Bia makes premium")

    started_listener = client.post(f"/campaigns/{campaign_id}/listener/start", headers=headers)
    assert started_listener.status_code == 200
    started_listener_json = started_listener.json()
    assert started_listener_json["status"] == "running"
    assert started_listener_json["surfaces_active_count"] == 0

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

    openclaw_skill = client.get(f"/api/campaigns/{campaign_id}/openclaw-skill", headers=headers)
    assert openclaw_skill.status_code == 200
    assert openclaw_skill.headers["content-type"].startswith("text/markdown")
    openclaw_skill_text = openclaw_skill.text
    assert "Ever Autonomous Sales Agent" in openclaw_skill_text
    assert "/agent-config" in openclaw_skill_text
    assert "Which channels and platforms to use" in openclaw_skill_text
    assert "Made in Canada" in openclaw_skill_text
    assert "Reddit-Specific Rules" not in openclaw_skill_text

    openclaw_skill_bundle = client.get(
        f"/api/campaigns/{campaign_id}/openclaw-skill?format=bundle",
        headers=headers,
    )
    assert openclaw_skill_bundle.status_code == 200
    openclaw_skill_json = openclaw_skill_bundle.json()
    assert openclaw_skill_json["campaign_id"] == campaign_id
    assert openclaw_skill_json["config_json"]["api_key"] == agent_api_key
    assert openclaw_skill_json["config_json"]["ever_api"]["api_key"] == agent_api_key
    assert "reddit" not in openclaw_skill_json["config_json"]

    openclaw_config = client.get(
        f"/api/campaigns/{campaign_id}/openclaw-skill?format=config",
        headers=headers,
    )
    assert openclaw_config.status_code == 200
    openclaw_config_json = openclaw_config.json()
    assert openclaw_config_json["ever_api"]["config_endpoint"].endswith("/agent-config")
    assert openclaw_config_json["ever_api"]["events_endpoint"].endswith("/events")

    agent_headers = {"Authorization": f"Bearer {agent_api_key}"}
    agent_config = client.get(
        f"/api/campaigns/{campaign_id}/agent-config",
        headers=agent_headers,
    )
    assert agent_config.status_code == 200
    agent_config_json = agent_config.json()
    assert agent_config_json["campaign_id"] == campaign_id
    assert agent_config_json["status"] == "running"
    assert agent_config_json["reporting"]["api_key"] == agent_api_key
    assert agent_config_json["brand"]["story"]
    assert "surfaces" not in agent_config_json
    assert "rules" not in agent_config_json
    assert agent_config_json["constraints"]["always_disclose_ai"] is True
    assert agent_config_json["constraints"]["max_actions_per_day"] >= 1
    assert agent_config_json["budget"]["remaining"] > 0
    assert agent_config_json["context"]["positioning"].startswith("Bia makes premium")
    assert "Made in Canada" in agent_config_json["context"]["proof_points"]
    assert "attributes" in agent_config_json["products"][0]
    assert len(agent_config_json["products"][0]["key_selling_points"]) >= 1
    product_id = agent_config_json["products"][0]["id"]

    research_event = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "action",
            "category": "research",
            "surface": "forum",
            "description": "Reviewed a premium-basics forum thread to gauge fit before engaging.",
            "source_url": "https://forum.ever.local/thread/test123",
            "source_content": "Looking for premium workout underwear that still feels good all day.",
            "source_author": "forum:movementclub",
            "target_audience": "Women buying premium active basics",
            "product_id": product_id,
            "tokens_used": 620,
            "compute_cost_usd": 0.0046,
            "expected_impact": "medium",
            "timestamp": research_timestamp,
        },
    )
    assert research_event.status_code == 200
    assert research_event.json()["status"] == "recorded"

    response_action = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "action",
            "category": "engagement",
            "surface": "reddit",
            "description": "Posted a helpful reply in a running thread after confirming product fit.",
            "source_url": "https://reddit.com/r/running/comments/test123",
            "source_content": "What underwear doesn't chafe on long runs?",
            "source_author": "u/runner_jane",
            "target_audience": "Women training for distance running",
            "response_text": "If the goal is comfort during movement, breathable and stay-put matters most. Bia's High Movement Thong is built for running and dries fast. I'm an AI agent for Bia (via Ever).",
            "referral_url": f"http://localhost:8000/go/{product_id}?src=reddit&cid={campaign_id}&iid=reply_evt_1",
            "product_id": product_id,
            "tokens_used": 1150,
            "compute_cost_usd": 0.0082,
            "expected_impact": "high",
            "timestamp": action_timestamp,
        },
    )
    assert response_action.status_code == 200
    assert response_action.json()["status"] == "recorded"
    assert response_action.json()["budget_remaining"] < 2400
    assert response_action.json()["event_id"] == "reply_evt_1"

    strategy_update = client.post(
        f"/api/campaigns/{campaign_id}/events",
        headers=agent_headers,
        json={
            "event_type": "strategy_update",
            "category": "strategy",
            "surface": "agent_brain",
            "description": "Focused on Reddit and forum research first, then shifted toward helpful engagement once fit looked strong.",
            "channels_used": ["reddit", "forum"],
            "total_actions": 2,
            "tokens_used": 1770,
            "compute_cost_usd": 0.0128,
            "timestamp": strategy_timestamp,
        },
    )
    assert strategy_update.status_code == 200
    assert strategy_update.json()["status"] == "recorded"

    updated_listener_status = client.get(
        f"/campaigns/{campaign_id}/listener/status",
        headers=headers,
    )
    assert updated_listener_status.status_code == 200
    updated_listener_status_json = updated_listener_status.json()
    assert updated_listener_status_json["status"] == "running"
    assert updated_listener_status_json["signals_today"] >= 2
    assert updated_listener_status_json["responses_today"] >= 1
    assert updated_listener_status_json["strategy_updates_today"] >= 1
    assert updated_listener_status_json["active_surface_count"] >= 2
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
    assert listener_analytics_json["strategy_updates"] >= 1
    assert listener_analytics_json["clicks"] >= 1
    assert listener_analytics_json["conversions"] >= 1
    assert listener_analytics_json["revenue"] >= 32.0
    assert listener_analytics_json["compute_cost"] > 0
    assert any(item["surface"] == "reddit" for item in listener_analytics_json["top_surfaces"])
    assert any(item["surface"] == "forum" for item in listener_analytics_json["top_surfaces"])
    assert any(
        item["surface"] == "reddit" for item in listener_analytics_json["channel_breakdown"]
    )
    assert any(
        "reddit" in entry["channels_used"] for entry in listener_analytics_json["strategy_feed"]
    )
    assert len(listener_analytics_json["daily_series"]) >= 1

    action_activity = client.get(
        f"/campaigns/{campaign_id}/activity?limit=20&event_type=action",
        headers=headers,
    )
    assert action_activity.status_code == 200
    assert any(entry["event_type"] == "action" for entry in action_activity.json())
    assert any(entry["surface"] == "reddit" for entry in action_activity.json())

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

    match_activity = client.get(
        f"/campaigns/{campaign_id}/activity?limit=20&event_type=match",
        headers=headers,
    )
    assert match_activity.status_code == 200
    assert any(entry["channel"] == "mcp" for entry in match_activity.json())

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
