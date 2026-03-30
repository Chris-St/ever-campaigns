from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.openclaw_agent import (
    MIN_FUNDED_DISCOVERY_REFRESH_SECONDS,
    build_discovery_queries,
    discover_live_opportunities,
    discovery_refresh_seconds,
    funded_live_mode,
)
from app.services.model_competition import enabled_competition_lanes, normalize_competition_config


def sample_config() -> dict:
    return {
        "brand": {
            "name": "Bia",
            "disclosure": "I'm an AI agent for Bia (via Ever)",
        },
        "context": {
            "key_messages": ["Lead with fit and comfort during movement."],
            "proof_points": ["Made in Canada", "Organic cotton recovery pieces"],
        },
        "products": [
            {
                "id": "prod_1",
                "name": "High Movement Thong",
                "price": 32.0,
                "currency": "CAD",
                "description": "Performance thong for running and high-movement training.",
                "category": "athletic_underwear",
                "attributes": {"subcategory": "thong", "material": "mesh_woven"},
                "activities": ["running", "cycling", "lifting"],
                "referral_base": "http://localhost:8000/go/prod_1",
                "key_selling_points": ["breathable", "stays in place", "sweat-wicking"],
            },
            {
                "id": "prod_2",
                "name": "The Recovery T",
                "price": 42.0,
                "currency": "CAD",
                "description": "Organic-cotton tee for lounge and recovery days.",
                "category": "loungewear",
                "attributes": {"subcategory": "t-shirt", "material": "organic_cotton"},
                "activities": ["sleep", "lounge", "recovery"],
                "referral_base": "http://localhost:8000/go/prod_2",
                "key_selling_points": ["organic cotton", "soft hand feel", "recovery-first"],
            },
        ],
    }


def test_build_discovery_queries_biases_toward_bia_use_cases() -> None:
    queries = build_discovery_queries(sample_config())

    assert "running underwear chafing" in queries
    assert "workout underwear recommendation" in queries
    assert any("organic cotton" in query for query in queries)


def test_funded_live_mode_detects_paid_propose_only_campaigns() -> None:
    assert funded_live_mode({"campaign_status": "active", "operating_mode": "propose_only"}) is True
    assert funded_live_mode({"campaign_status": "pending_payment", "operating_mode": "propose_only"}) is False
    assert funded_live_mode({"campaign_status": "active", "operating_mode": "simulation"}) is False


def test_discovery_refresh_seconds_frontloads_then_slows_with_budget() -> None:
    fast = discovery_refresh_seconds(
        {
            "campaign_status": "active",
            "operating_mode": "propose_only",
            "budget": {"monthly": 50.0, "remaining": 50.0},
            "constraints": {"max_actions_per_day": 50},
        }
    )
    slower = discovery_refresh_seconds(
        {
            "campaign_status": "active",
            "operating_mode": "propose_only",
            "budget": {"monthly": 50.0, "remaining": 35.0},
            "constraints": {"max_actions_per_day": 50},
        }
    )

    assert fast >= MIN_FUNDED_DISCOVERY_REFRESH_SECONDS
    assert slower >= fast


def test_enabled_competition_prefers_openai_over_heuristic_when_available(monkeypatch) -> None:
    monkeypatch.setattr("app.services.model_competition.settings.openai_api_key", "sk-test-openai")
    monkeypatch.setattr("app.services.model_competition.settings.openai_model", "gpt-5.4")
    competition = normalize_competition_config(
        {
            "enabled": True,
            "mode": "best_of_n",
            "lanes": [
                {"id": "heuristic:objective-baseline", "provider": "heuristic", "model": "objective-baseline", "enabled": True},
                {"id": "openai:gpt-5.4", "provider": "openai", "model": "gpt-5.4", "enabled": True},
            ],
        }
    )
    lanes = enabled_competition_lanes(competition)
    assert any(lane["provider"] == "openai" for lane in lanes)
    assert all(lane["provider"] != "heuristic" for lane in lanes)


def test_discover_live_opportunities_prefers_real_reddit_threads() -> None:
    created_utc = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search.json":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "permalink": "/r/running/comments/abc123/testing_thread",
                                    "title": "What underwear doesn't chafe on long runs?",
                                    "selftext": "Looking for something breathable that stays put.",
                                    "author": "runner_jane",
                                    "subreddit": "running",
                                    "created_utc": created_utc,
                                    "num_comments": 7,
                                    "score": 12,
                                    "over_18": False,
                                    "stickied": False,
                                    "locked": False,
                                }
                            }
                        ]
                    }
                },
            )
        if request.url.path.endswith("/new.json"):
            return httpx.Response(200, json={"data": {"children": []}})
        if request.url.path == "/html/":
            return httpx.Response(
                200,
                text="""
                <html><body>
                  <div class="result">
                    <a class="result__a" href="https://example.com/running-newsletter">Women's running newsletter</a>
                    <a class="result__snippet">A weekly newsletter for women training for distance races.</a>
                  </div>
                </body></html>
                """,
            )
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    opportunities = discover_live_opportunities(client, sample_config(), seen_source_urls=set())

    assert opportunities
    assert any(item["surface"] == "reddit" for item in opportunities)
    assert any(item["action_type"] == "email" for item in opportunities)

    reddit_opportunity = next(item for item in opportunities if item["surface"] == "reddit")
    assert reddit_opportunity["source_url"] == "https://www.reddit.com/r/running/comments/abc123/testing_thread"
    assert reddit_opportunity["subreddit_or_channel"] == "r/running"
    assert reddit_opportunity["intent_score"]["composite"] >= 62
    assert "live Reddit post" in reddit_opportunity["description"]

    outreach_opportunity = next(item for item in opportunities if item["action_type"] == "email")
    assert outreach_opportunity["surface"] == "creator"
    assert outreach_opportunity["expected_return_score"] >= 58
    assert "outreach potential" in outreach_opportunity["description"]
