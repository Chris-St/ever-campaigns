from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.security import generate_campaign_api_key, hash_api_key
from app.models.entities import (
    AgentEvent,
    AgentResponse,
    Campaign,
    Click,
    Conversion,
    IntentSignal,
    Merchant,
    Proposal,
    Product,
)
from app.services.context_ingestion import build_context_seed_summary
from app.services.openclaw_runtime import launch_openclaw_agent, stop_openclaw_agent
from app.services.memory import build_memory_summary
from app.services.model_competition import normalize_competition_config
from app.services.proposals import (
    build_proposal_stats,
    create_proposal_from_event,
    update_campaign_budget_state,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def relative_time(value: datetime) -> str:
    delta = utcnow() - ensure_utc(value)
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m ago"


AGGRESSIVENESS_THRESHOLDS = {
    "conservative": {"composite_min": 78, "receptivity_min": 68},
    "balanced": {"composite_min": 70, "receptivity_min": 60},
    "aggressive": {"composite_min": 58, "receptivity_min": 48},
}

AGGRESSIVENESS_PROFILES = {
    "conservative": {"max_actions_per_day": 25, "quality_threshold": 78},
    "balanced": {"max_actions_per_day": 50, "quality_threshold": 64},
    "aggressive": {"max_actions_per_day": 100, "quality_threshold": 52},
}


DEMO_SIGNAL_LIBRARY: list[dict[str, Any]] = [
    {
        "surface": "reddit",
        "subreddit_or_channel": "running",
        "author_handle": "runnernorth",
        "content_text": "Any women runners have underwear recs that do not chafe on long runs? I am over bike shorts under everything.",
        "context_text": "Thread asking for gear recommendations before marathon training ramps up.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "XXrunning",
        "author_handle": "tempoalice",
        "content_text": "Looking for a thong or brief that actually stays put during speed workouts. Everything I own rides up.",
        "context_text": "Reply chain about race-day clothing systems.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "cycling",
        "author_handle": "cadencejules",
        "content_text": "Best underwear for indoor cycling? Need something breathable and low profile.",
        "context_text": "Comment thread comparing bibs and base layers for Peloton rides.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "crossfit",
        "author_handle": "barbellmara",
        "content_text": "Has anyone found underwear that works for box jumps and lifting without shifting around?",
        "context_text": "Post about small things that improve training comfort.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "femalefashionadvice",
        "author_handle": "closetnotes",
        "content_text": "Need a premium underwear brand that feels athletic but still nice enough for everyday wear. Any favorites?",
        "context_text": "Discussion about brands worth paying more for.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "ABraThatFits",
        "author_handle": "fitquestion",
        "content_text": "What underwear do you pair with leggings if you want no lines and zero rolling during workouts?",
        "context_text": "Side thread on comfortable gym layers.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "yoga",
        "author_handle": "floweast",
        "content_text": "Softest underwear for yoga and pilates? I care more about comfort than compression.",
        "context_text": "Beginner asking for gentler studio basics.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "pilates",
        "author_handle": "pilatesform",
        "content_text": "Recommendations for underwear that works for reformer classes and walking around after.",
        "context_text": "Pilates wardrobe roundup thread.",
    },
    {
        "surface": "reddit",
        "subreddit_or_channel": "BuyItForLife",
        "author_handle": "lastingthings",
        "content_text": "Curious if there are any made-in-Canada underwear brands that actually hold up to regular training.",
        "context_text": "People sharing durable clothing brands.",
    },
    {
        "surface": "twitter",
        "subreddit_or_channel": "workout underwear recommendation",
        "author_handle": "fitcasey",
        "content_text": "need a workout underwear recommendation that does not turn into a wedgie by minute 10",
        "context_text": "Short post asking followers for recs.",
    },
    {
        "surface": "twitter",
        "subreddit_or_channel": "running underwear chafing",
        "author_handle": "milelog",
        "content_text": "why is finding running underwear harder than finding shoes. please send help.",
        "context_text": "Frustrated but still clearly shopping.",
    },
    {
        "surface": "twitter",
        "subreddit_or_channel": "best athletic thong",
        "author_handle": "studiohazy",
        "content_text": "Best athletic thong for hot yoga and walking all day? Looking for something breathable.",
        "context_text": "Request for recommendations.",
    },
    {
        "surface": "twitter",
        "subreddit_or_channel": "recovery loungewear",
        "author_handle": "slowdaysclub",
        "content_text": "Need recovery-day shorts that feel elevated enough to wear all weekend.",
        "context_text": "Asking for premium basics recs.",
    },
    {
        "surface": "twitter",
        "subreddit_or_channel": "organic cotton sleep set",
        "author_handle": "restmode",
        "content_text": "Anyone have an organic cotton sleep tee they actually love?",
        "context_text": "Looking to replace fast-fashion sleepwear.",
    },
]

DEMO_AUTONOMOUS_LIBRARY: list[dict[str, Any]] = [
    {
        "category": "research",
        "surface": "reddit",
        "description": "Reviewed a fresh Reddit thread from runners looking for underwear that will not chafe on long efforts.",
        "source_content": "What underwear doesn't chafe on long runs?",
        "source_author": "u/runner_jane",
        "target_audience": "Women training for distance running",
        "expected_impact": "high",
    },
    {
        "category": "engagement",
        "surface": "reddit",
        "description": "Posted a helpful reply in a gear discussion after confirming the fit was strong for Bia's performance line.",
        "source_content": "Any recommendations for workout underwear that stays put during intervals?",
        "source_author": "u/tempo_casey",
        "target_audience": "High-intent runners comparing options",
        "expected_impact": "high",
    },
    {
        "category": "content_creation",
        "surface": "blog",
        "description": "Drafted a short educational post on how to choose underwear for high-movement training and recovery days.",
        "source_content": None,
        "source_author": None,
        "target_audience": "Prospects researching performance basics",
        "expected_impact": "medium",
    },
    {
        "category": "outreach",
        "surface": "email",
        "description": "Sent a personalized email to a fitness creator whose audience overlaps with Bia's highest-converting buyers.",
        "source_content": None,
        "source_author": "fitness.creator@example.com",
        "target_audience": "Fitness creator with engaged female audience",
        "expected_impact": "medium",
    },
    {
        "category": "engagement",
        "surface": "forum",
        "description": "Joined a boutique women's training forum thread and answered a product-fit question with a tracked recommendation.",
        "source_content": "Looking for premium workout underwear that still feels good all day.",
        "source_author": "forum:movementclub",
        "target_audience": "Women looking for premium active basics",
        "expected_impact": "medium",
    },
    {
        "category": "research",
        "surface": "twitter",
        "description": "Monitored a cluster of posts about breathable training underwear to see where conversion intent was strongest.",
        "source_content": "best athletic thong for hot yoga and walking all day?",
        "source_author": "@studio_notes",
        "target_audience": "People comparing workout underwear options",
        "expected_impact": "low",
    },
]


def threshold_config(aggressiveness: str) -> dict[str, int]:
    return AGGRESSIVENESS_THRESHOLDS.get(aggressiveness, AGGRESSIVENESS_THRESHOLDS["balanced"]).copy()


def build_default_brand_voice(campaign: Campaign) -> dict[str, Any]:
    merchant = campaign.merchant
    brand_name = merchant.name or merchant.domain.split(".")[0].title()
    products = merchant.products
    target_customer = (
        products[0].attributes.get("target_customer")
        if products and isinstance(products[0].attributes, dict)
        else "People looking for premium, thoughtfully-built essentials."
    )
    return {
        "brand_name": brand_name,
        "story": (
            f"{brand_name} builds premium essentials for people who want performance, comfort, "
            "and a product recommendation that actually fits the moment."
        ),
        "values": [
            "Helpful first",
            "Premium quality over hype",
            "Transparent AI disclosure",
        ],
        "tone": "Confident, understated, knowledgeable, and warm",
        "target_customer": target_customer,
        "dos": [
            "Lead with useful advice before mentioning the product",
            "Reference concrete product attributes only when they match the ask",
            "Mention disclosure clearly on every response",
            "Keep the recommendation concise and natural",
        ],
        "donts": [
            "Do not trash competitors",
            "Do not force a recommendation when fit is weak",
            "Do not make medical or unsupported performance claims",
            "Do not sound like a discount ad",
        ],
        "sample_responses": {
            "reddit": (
                f"If the problem is chafing, look for something that stays put and dries quickly instead of adding bulk. "
                f"{brand_name}'s High Movement Thong is built for running and cycling with breathable mesh and stretch, "
                f"so it tends to solve exactly that issue. Disclosure: I'm Ever, an AI agent for {brand_name}."
            ),
            "twitter": (
                f"If you want something low-profile and breathable, {brand_name}'s High Movement Thong is worth a look. "
                f"It was made for running and high-movement training. — Ever AI for {brand_name}"
            ),
            "product_query": (
                f"For recovery days, {brand_name}'s organic-cotton pieces are the best fit because they lean comfort-first "
                "without losing the premium feel."
            ),
        },
    }


def build_default_brand_context(campaign: Campaign) -> dict[str, Any]:
    merchant = campaign.merchant
    brand_name = merchant.name or merchant.domain.split(".")[0].title()
    products = get_products_for_campaign(campaign) or merchant.products
    ships_to = sorted(
        {
            destination
            for product in products
            for destination in (
                product.attributes.get("ships_to", []) if isinstance(product.attributes, dict) else []
            )
        }
    ) or merchant.ships_to
    made_in_values = sorted(
        {
            str(product.attributes.get("made_in")).strip()
            for product in products
            if isinstance(product.attributes, dict) and product.attributes.get("made_in")
        }
    )
    has_free_shipping = any(
        isinstance(product.attributes, dict) and bool(product.attributes.get("free_shipping"))
        for product in products
    )
    target_customer = (
        campaign.brand_voice_profile.get("target_customer")
        or build_default_brand_voice(campaign).get("target_customer")
        or "People looking for premium, thoughtfully-built essentials."
    )
    proof_points = []
    if made_in_values:
        proof_points.append(f"Made in {', '.join(made_in_values)}")
    if ships_to:
        proof_points.append(f"Ships to {', '.join(ships_to)}")
    if has_free_shipping:
        proof_points.append("Free shipping is available on the store")
    if products:
        proof_points.append(f"Catalog currently includes {len(products)} active products")

    return {
        "positioning": (
            f"{brand_name} is a premium direct-to-consumer brand focused on thoughtful product fit, "
            "clear utility, and understated quality."
        ),
        "ideal_customer": target_customer,
        "key_messages": [
            "Lead with product fit and customer relevance before promotion",
            "Reference concrete features already present in the catalog",
            "Frame the brand as premium, confident, and useful rather than discount-driven",
        ],
        "proof_points": proof_points,
        "objection_handling": [
            "If fit is weak, say so and avoid forcing the recommendation",
            "If pricing comes up, justify value through quality, material, and use-case fit",
            "If a shopper asks for proof, point to catalog attributes and product details already available",
        ],
        "prohibited_claims": [
            "Do not make medical claims",
            "Do not invent material, sizing, shipping, or performance claims",
            "Do not promise discounts, limited offers, or stock urgency unless explicitly configured",
        ],
        "additional_context": "",
    }


def build_default_listener_config(campaign: Campaign) -> dict[str, Any]:
    aggressiveness = "balanced"
    profile = AGGRESSIVENESS_PROFILES[aggressiveness]
    return {
        "listener_mode": "simulation",
        "aggressiveness": aggressiveness,
        "review_mode": "auto",
        "auto_post_after_approvals": 50,
        "max_actions_per_day": profile["max_actions_per_day"],
        "quality_threshold": profile["quality_threshold"],
        "thresholds": threshold_config(aggressiveness),
        "safeguards": {
            "max_actions_per_day": profile["max_actions_per_day"],
            "max_responses_per_surface_per_day": 10,
            "max_responses_per_day": 50,
            "max_thread_replies": 2,
            "minimum_minutes_between_surface_responses": 5,
            "minimum_post_age_minutes": 10,
            "never_respond_to_same_author_within_hours": 24,
            "one_response_per_author_per_day": True,
            "always_disclose_ai": True,
            "pause_if_downvote_rate_exceeds": 0.20,
            "auto_post_confidence_threshold": 70,
        },
        "surfaces": [],
        "competition": normalize_competition_config(None),
    }


def merge_dicts(defaults: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    incoming = incoming or {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            merged[key] = merge_dicts(value, incoming.get(key) if isinstance(incoming.get(key), dict) else {})
        elif isinstance(value, list):
            candidate = incoming.get(key)
            merged[key] = candidate if isinstance(candidate, list) and candidate else value
        else:
            merged[key] = incoming.get(key, value)
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = value
    return merged


def normalize_listener_config(config: dict[str, Any] | None) -> dict[str, Any]:
    defaults = build_default_listener_config_for_values()
    merged = merge_dicts(defaults, config)
    aggressiveness = merged.get("aggressiveness", "balanced")
    profile = AGGRESSIVENESS_PROFILES.get(aggressiveness, AGGRESSIVENESS_PROFILES["balanced"])
    merged["thresholds"] = merge_dicts(threshold_config(aggressiveness), merged.get("thresholds", {}))
    merged["max_actions_per_day"] = int(merged.get("max_actions_per_day") or profile["max_actions_per_day"])
    merged["quality_threshold"] = int(merged.get("quality_threshold") or profile["quality_threshold"])
    safeguards = merge_dicts(defaults.get("safeguards", {}), merged.get("safeguards", {}))
    safeguards["max_actions_per_day"] = int(
        safeguards.get("max_actions_per_day") or merged["max_actions_per_day"]
    )
    merged["safeguards"] = safeguards
    normalized_surfaces = []
    for surface in merged.get("surfaces", []):
        default_surface = {
            "type": surface.get("type", "reddit"),
            "enabled": True,
            "subreddits": [],
            "keywords": [],
            "search_queries": [],
            "poll_interval_seconds": 180,
        }
        normalized_surfaces.append(merge_dicts(default_surface, surface))
    merged["surfaces"] = normalized_surfaces
    merged["competition"] = normalize_competition_config(merged.get("competition"))
    return merged


def build_default_listener_config_for_values() -> dict[str, Any]:
    profile = AGGRESSIVENESS_PROFILES["balanced"]
    return {
        "listener_mode": "simulation",
        "aggressiveness": "balanced",
        "review_mode": "auto",
        "auto_post_after_approvals": 50,
        "max_actions_per_day": profile["max_actions_per_day"],
        "quality_threshold": profile["quality_threshold"],
        "thresholds": threshold_config("balanced"),
        "safeguards": {
            "max_actions_per_day": profile["max_actions_per_day"],
            "max_responses_per_surface_per_day": 10,
            "max_responses_per_day": 50,
            "max_thread_replies": 2,
            "minimum_minutes_between_surface_responses": 5,
            "minimum_post_age_minutes": 10,
            "never_respond_to_same_author_within_hours": 24,
            "one_response_per_author_per_day": True,
            "always_disclose_ai": True,
            "pause_if_downvote_rate_exceeds": 0.20,
            "auto_post_confidence_threshold": 70,
        },
        "surfaces": [],
        "competition": normalize_competition_config(None),
    }


def normalize_brand_voice(profile: dict[str, Any] | None, campaign: Campaign) -> dict[str, Any]:
    defaults = build_default_brand_voice(campaign)
    return merge_dicts(defaults, profile)


def normalize_brand_context(profile: dict[str, Any] | None, campaign: Campaign) -> dict[str, Any]:
    defaults = build_default_brand_context(campaign)
    normalized = merge_dicts(defaults, profile)
    for field in (
        "key_messages",
        "proof_points",
        "objection_handling",
        "prohibited_claims",
    ):
        normalized[field] = [
            str(item).strip()
            for item in normalized.get(field, [])
            if str(item).strip()
        ]
    for field in ("positioning", "ideal_customer", "additional_context"):
        normalized[field] = str(normalized.get(field, "") or "").strip()
    return normalized


def ensure_listener_defaults(campaign: Campaign) -> None:
    campaign.brand_voice_profile = normalize_brand_voice(campaign.brand_voice_profile, campaign)
    campaign.brand_context_profile = normalize_brand_context(campaign.brand_context_profile, campaign)
    if campaign.listener_config:
        campaign.listener_config = normalize_listener_config(campaign.listener_config)
    else:
        campaign.listener_config = normalize_listener_config(build_default_listener_config(campaign))
    if campaign.listener_status not in {"running", "stopped", "paused", "budget_exhausted"}:
        campaign.listener_status = "stopped"
    if campaign.approved_response_count is None:
        campaign.approved_response_count = 0


def ensure_campaign_api_key(campaign: Campaign, regenerate: bool = False) -> str:
    if campaign.listener_api_key and campaign.listener_api_key_hash and not regenerate:
        return campaign.listener_api_key

    api_key = generate_campaign_api_key()
    campaign.listener_api_key = api_key
    campaign.listener_api_key_hash = hash_api_key(api_key)
    campaign.listener_api_key_last_four = api_key[-4:]
    return api_key


def get_listener_campaign(db: Session, campaign_id: str) -> Campaign | None:
    return db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(
            joinedload(Campaign.merchant).selectinload(Merchant.products),
        )
    )


def get_products_for_campaign(campaign: Campaign) -> list[Product]:
    return [product for product in campaign.merchant.products if product.status == "active"]


def budget_remaining(campaign: Campaign) -> float:
    return round(max(campaign.budget_monthly - campaign.budget_spent, 0.0), 2)


def effective_listener_status(campaign: Campaign) -> str:
    if campaign.status in {"paused", "paused_manual", "canceled"}:
        return "paused"
    if campaign.status == "paused_budget" or budget_remaining(campaign) <= 0:
        return "budget_exhausted"
    return campaign.listener_status or "stopped"


def listener_mode(campaign: Campaign) -> str:
    ensure_listener_defaults(campaign)
    return campaign.listener_config.get("listener_mode", "simulation")


def map_aggressiveness_limits(aggressiveness: str) -> dict[str, int]:
    return AGGRESSIVENESS_PROFILES.get(aggressiveness, AGGRESSIVENESS_PROFILES["balanced"]).copy()


def choose_autonomous_product(campaign: Campaign, template: dict[str, Any], seed: str) -> Product | None:
    products = get_products_for_campaign(campaign)
    if not products:
        return None
    if template.get("source_content"):
        return choose_product(
            products,
            {
                "content_text": template.get("source_content", ""),
                "context_text": template.get("description", ""),
            },
        )
    return products[hash_value(seed) % len(products)]


def default_event_description(payload: dict[str, Any]) -> str:
    event_type = payload.get("event_type", "action")
    surface = payload.get("surface") or "the web"
    source_content = payload.get("source_content")
    if event_type == "metering":
        return payload.get("description") or "Recorded metered provider spend from the external agent runtime."
    if event_type == "strategy_update":
        return payload.get("description") or "Reported a strategy update."
    if event_type == "conversion_attempt":
        return payload.get("description") or "Attempted to convert a high-intent prospect."
    if event_type in {"intent_detected", "skip", "response_skipped"}:
        if source_content:
            return f"Researched a potential opportunity on {surface}: {source_content}"
        return f"Researched a potential opportunity on {surface}."
    if event_type in {"response_posted", "dm_sent", "email_sent", "response_pending_review"}:
        if source_content:
            return f"Took action on {surface} after finding a strong-fit conversation: {source_content}"
        return f"Took action on {surface} for a qualified prospect."
    return payload.get("description") or f"Reported an autonomous agent action on {surface}."


def default_event_category(payload: dict[str, Any]) -> str:
    event_type = payload.get("event_type", "action")
    if event_type == "metering":
        return "metering"
    if event_type == "strategy_update":
        return "strategy"
    if event_type == "conversion_attempt":
        return "engagement"
    if event_type in {"dm_sent", "email_sent"}:
        return "outreach"
    if event_type in {"response_posted", "response_pending_review"}:
        return "engagement"
    if event_type in {"intent_detected", "skip", "response_skipped"}:
        return "research"
    return "other"


def normalize_agent_event_payload(campaign: Campaign, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_event_type = payload.get("event_type") or "action"
    if normalized_event_type not in {"action", "strategy_update", "conversion_attempt", "metering"}:
        normalized_event_type = "action"
    surface = payload.get("surface") or "other"
    category = payload.get("category") or default_event_category(payload)
    description = payload.get("description") or default_event_description(payload)
    referral_url = payload.get("referral_url")
    interaction_id = parse_interaction_id(referral_url)
    event_id = payload.get("event_id") or payload.get("id") or interaction_id or str(uuid4())
    return {
        "id": event_id,
        "event_type": normalized_event_type,
        "category": category,
        "surface": surface,
        "description": description,
        "source_url": payload.get("source_url"),
        "source_content": payload.get("source_content"),
        "source_author": payload.get("source_author"),
        "target_audience": payload.get("target_audience")
        or payload.get("subreddit_or_channel")
        or payload.get("source_author"),
        "product_id": payload.get("product_id"),
        "referral_url": referral_url,
        "response_text": payload.get("response_text"),
        "model_provider": payload.get("model_provider"),
        "model_name": payload.get("model_name"),
        "tokens_used": int(payload.get("tokens_used", 0) or 0),
        "compute_cost_usd": float(payload.get("compute_cost_usd", 0.0) or 0.0),
        "expected_impact": payload.get("expected_impact")
        or (
            "high"
            if float(payload.get("intent_score", {}).get("composite", 0.0) or 0.0) >= 80
            else "medium"
            if float(payload.get("intent_score", {}).get("composite", 0.0) or 0.0) >= 60
            else "low"
        ),
        "details": {
            "raw_event_type": payload.get("event_type"),
            "subreddit_or_channel": payload.get("subreddit_or_channel"),
            "source_context": payload.get("source_context"),
            "intent_score": payload.get("intent_score", {}),
            "action_taken": payload.get("action_taken"),
            "channels_used": payload.get("channels_used", []),
            "total_actions": payload.get("total_actions"),
            "competition_score": payload.get("competition_score"),
            "campaign_status": campaign.status,
        },
    }


def persist_agent_event(
    db: Session,
    campaign: Campaign,
    payload: dict[str, Any],
    created_at: datetime,
) -> AgentEvent:
    normalized = normalize_agent_event_payload(campaign, payload)
    event = db.scalar(select(AgentEvent).where(AgentEvent.id == normalized["id"]))
    if event is None:
        event = AgentEvent(
            id=normalized["id"],
            campaign_id=campaign.id,
            event_type=normalized["event_type"],
            category=normalized["category"],
            surface=normalized["surface"],
            description=normalized["description"],
            source_url=normalized["source_url"],
            source_content=normalized["source_content"],
            source_author=normalized["source_author"],
            target_audience=normalized["target_audience"],
            product_id=normalized["product_id"],
            referral_url=normalized["referral_url"],
            response_text=normalized["response_text"],
            model_provider=normalized["model_provider"],
            model_name=normalized["model_name"],
            tokens_used=normalized["tokens_used"],
            compute_cost_usd=normalized["compute_cost_usd"],
            expected_impact=normalized["expected_impact"],
            details=normalized["details"],
            created_at=created_at,
        )
        db.add(event)
        db.flush()
        return event

    event.event_type = normalized["event_type"]
    event.category = normalized["category"]
    event.surface = normalized["surface"]
    event.description = normalized["description"]
    event.source_url = normalized["source_url"]
    event.source_content = normalized["source_content"]
    event.source_author = normalized["source_author"]
    event.target_audience = normalized["target_audience"]
    event.product_id = normalized["product_id"]
    event.referral_url = normalized["referral_url"]
    event.response_text = normalized["response_text"]
    event.model_provider = normalized["model_provider"]
    event.model_name = normalized["model_name"]
    event.tokens_used = normalized["tokens_used"]
    event.compute_cost_usd = normalized["compute_cost_usd"]
    event.expected_impact = normalized["expected_impact"]
    event.details = normalized["details"]
    event.created_at = created_at
    db.flush()
    return event


def simulate_click_and_conversion_for_event(db: Session, event: AgentEvent) -> None:
    if not event.product_id or not event.referral_url or event.event_type != "action":
        return
    existing_click = db.scalar(
        select(Click).where(
            Click.campaign_id == event.campaign_id,
            Click.product_id == event.product_id,
            Click.source == "autonomous_agent",
            Click.created_at >= event.created_at,
        )
    )
    if existing_click is not None:
        return

    likelihood = {
        "high": 62,
        "medium": 42,
        "low": 20,
    }.get(event.expected_impact or "medium", 35)
    seed = hash_value(event.id)
    if seed % 100 > likelihood:
        return

    click_time = ensure_utc(event.created_at) + timedelta(minutes=4 + seed % 35)
    click = Click(
        match_id=None,
        product_id=event.product_id,
        campaign_id=event.campaign_id,
        channel="autonomous_agent",
        source="autonomous_agent",
        surface=event.surface,
        created_at=click_time,
    )
    db.add(click)
    db.flush()

    product = db.scalar(select(Product).where(Product.id == event.product_id))
    if product is None:
        return
    if seed % 100 > max(likelihood - 18, 8):
        return

    conversion = Conversion(
        click_id=click.id,
        product_id=event.product_id,
        campaign_id=event.campaign_id,
        order_value=round(product.price * (1.0 + (seed % 8) / 20), 2),
        channel="autonomous_agent",
        created_at=click_time + timedelta(minutes=10 + seed % 75),
    )
    db.add(conversion)


def build_strategy_summary(events: list[AgentEvent], created_at: datetime) -> dict[str, Any]:
    surfaces = sorted({event.surface for event in events if event.surface})
    categories = Counter(event.category or "other" for event in events)
    top_category = categories.most_common(1)[0][0] if categories else "action"
    descriptions = ", ".join(surfaces[:3]) if surfaces else "the highest-fit channels"
    return {
        "event_type": "strategy_update",
        "category": "strategy",
        "surface": "agent_brain",
        "description": (
            f"Focused on {descriptions} today. Logged {len(events)} actions, leaned hardest into "
            f"{top_category}, and will reallocate toward the channels producing the strongest RoC signal."
        ),
        "source_url": None,
        "source_content": None,
        "source_author": None,
        "target_audience": None,
        "product_id": None,
        "referral_url": None,
        "response_text": None,
        "tokens_used": sum(event.tokens_used for event in events),
        "compute_cost_usd": round(sum(event.compute_cost_usd for event in events), 4),
        "expected_impact": "medium",
        "channels_used": surfaces,
        "total_actions": len(events),
        "timestamp": created_at.isoformat(),
    }


def seed_agent_history(db: Session, campaign: Campaign) -> None:
    existing_event = db.scalar(select(AgentEvent.id).where(AgentEvent.campaign_id == campaign.id).limit(1))
    if existing_event is not None:
        return

    now = utcnow()
    seeded_events: list[AgentEvent] = []
    for day_offset in range(12, -1, -1):
        day = now - timedelta(days=day_offset)
        actions_for_day = 2 + hash_value(f"{campaign.id}:{day.isoformat()}") % 3
        day_events: list[AgentEvent] = []
        for index in range(actions_for_day):
            template = DEMO_AUTONOMOUS_LIBRARY[
                (hash_value(f"{campaign.id}:{day.isoformat()}:{index}") + index) % len(DEMO_AUTONOMOUS_LIBRARY)
            ]
            created_at = day.replace(
                hour=9 + ((index * 3 + day_offset) % 8),
                minute=(index * 11 + day_offset * 7) % 60,
                second=0,
                microsecond=0,
            )
            product = choose_autonomous_product(campaign, template, f"{day.isoformat()}:{index}")
            referral_url = None
            if product is not None and template["category"] in {"engagement", "outreach"}:
                referral_url = (
                    f"{build_referral_base(product.id)}"
                    f"?src={template['surface']}&cid={campaign.id}&iid=sim_{hash_value(f'{campaign.id}:{created_at.isoformat()}:{index}')}"
                )
            payload = {
                **template,
                "event_type": "action",
                "product_id": product.id if product is not None else None,
                "referral_url": referral_url,
                "response_text": (
                    f"I'm an AI agent for {campaign.brand_voice_profile.get('brand_name') or campaign.merchant.name or 'the brand'} (via Ever)."
                    if template["category"] in {"engagement", "outreach"}
                    else None
                ),
                "tokens_used": 620 + (hash_value(f"{campaign.id}:{created_at.isoformat()}") % 920),
                "compute_cost_usd": round(0.003 + ((index + day_offset) % 9) * 0.0022, 4),
                "timestamp": created_at.isoformat(),
            }
            event = persist_agent_event(db, campaign, payload, created_at)
            day_events.append(event)
            seeded_events.append(event)
            simulate_click_and_conversion_for_event(db, event)

        strategy_created_at = day.replace(hour=20, minute=10, second=0, microsecond=0)
        strategy_payload = build_strategy_summary(day_events, strategy_created_at)
        strategy_event = persist_agent_event(db, campaign, strategy_payload, strategy_created_at)
        seeded_events.append(strategy_event)

    campaign.listener_started_at = campaign.listener_started_at or now - timedelta(days=13)
    campaign.listener_last_polled_at = now
    campaign.budget_spent = round(sum(event.compute_cost_usd for event in seeded_events), 2)


def maybe_generate_fresh_agent_events(db: Session, campaign: Campaign, force: bool = False) -> None:
    if campaign.listener_status != "running":
        return
    now = utcnow()
    if not force and campaign.listener_last_polled_at is not None:
        elapsed = (now - ensure_utc(campaign.listener_last_polled_at)).total_seconds()
        if elapsed < 180:
            return

    max_actions = int(campaign.listener_config.get("max_actions_per_day") or 50)
    day_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    actions_today = db.scalars(
        select(AgentEvent).where(
            AgentEvent.campaign_id == campaign.id,
            AgentEvent.event_type == "action",
            AgentEvent.created_at >= day_start,
        )
    ).all()
    remaining_slots = max(max_actions - len(actions_today), 0)
    if remaining_slots <= 0:
        campaign.listener_last_polled_at = now
        return

    to_create = min(remaining_slots, 1 + hash_value(f"{campaign.id}:{now.isoformat()}") % 2)
    new_events: list[AgentEvent] = []
    for index in range(to_create):
        template = DEMO_AUTONOMOUS_LIBRARY[
            (hash_value(f"{campaign.id}:{now.isoformat()}:{index}") + index) % len(DEMO_AUTONOMOUS_LIBRARY)
        ]
        created_at = now - timedelta(minutes=10 - index * 4)
        product = choose_autonomous_product(campaign, template, f"{campaign.id}:{created_at.isoformat()}:{index}")
        referral_url = None
        if product is not None and template["category"] in {"engagement", "outreach"}:
            referral_url = (
                f"{build_referral_base(product.id)}"
                f"?src={template['surface']}&cid={campaign.id}&iid=live_{uuid4().hex[:12]}"
            )
        payload = {
            **template,
            "event_type": "action",
            "product_id": product.id if product is not None else None,
            "referral_url": referral_url,
            "response_text": (
                f"I'm an AI agent for {campaign.brand_voice_profile.get('brand_name') or campaign.merchant.name or 'the brand'} (via Ever)."
                if template["category"] in {"engagement", "outreach"}
                else None
            ),
            "tokens_used": 540 + (hash_value(f"{campaign.id}:{created_at.isoformat()}") % 780),
            "compute_cost_usd": round(0.0025 + ((index + now.hour) % 7) * 0.0024, 4),
            "timestamp": created_at.isoformat(),
        }
        event = persist_agent_event(db, campaign, payload, created_at)
        new_events.append(event)
        simulate_click_and_conversion_for_event(db, event)

    strategy_today = db.scalar(
        select(AgentEvent.id).where(
            AgentEvent.campaign_id == campaign.id,
            AgentEvent.event_type == "strategy_update",
            AgentEvent.created_at >= day_start,
        )
    )
    if strategy_today is None and new_events:
        strategy_payload = build_strategy_summary(new_events, now)
        persist_agent_event(db, campaign, strategy_payload, now)

    campaign.listener_last_polled_at = now
    campaign.budget_spent = round(
        sum(
            db.scalars(select(AgentEvent.compute_cost_usd).where(AgentEvent.campaign_id == campaign.id)).all()
        ),
        2,
    )


def refresh_simulation_if_needed(db: Session, campaign: Campaign, force: bool = False) -> None:
    if listener_mode(campaign) != "simulation":
        return
    if effective_listener_status(campaign) != "running":
        return
    seed_agent_history(db, campaign)
    maybe_generate_fresh_agent_events(db, campaign, force=force)
    db.commit()
    db.refresh(campaign)


def build_brand_voice_text(campaign: Campaign) -> str:
    profile = campaign.brand_voice_profile
    story = profile.get("story", "")
    tone = profile.get("tone", "")
    values = ", ".join(profile.get("values", [])[:3])
    parts = [part.strip() for part in [tone, story, values] if part]
    return ". ".join(parts)


def build_brand_disclosure(campaign: Campaign) -> str:
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "the brand"
    return f"I'm an AI agent for {brand_name} (via Ever)"


def build_referral_base(product_id: str) -> str:
    return f"{settings.public_api_url}/go/{product_id}"


def parse_interaction_id(referral_url: str | None) -> str | None:
    if not referral_url:
        return None
    try:
        parsed = urlparse(referral_url)
        values = parse_qs(parsed.query)
    except ValueError:
        return None
    interaction = values.get("iid", [])
    return interaction[0] if interaction else None


def parse_source_channel(payload: dict[str, Any]) -> str:
    explicit_channel = payload.get("subreddit_or_channel")
    if explicit_channel and str(explicit_channel).strip():
        return str(explicit_channel).strip()
    source_url = payload.get("source_url")
    if not source_url:
        return payload["surface"]
    try:
        parsed = urlparse(source_url)
        query_values = parse_qs(parsed.query)
    except ValueError:
        return payload["surface"]
    if payload["surface"] == "reddit" and "/r/" in parsed.path:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "r":
            return parts[1]
    if payload["surface"] == "twitter":
        query = query_values.get("query", [])
        if query and query[0].strip():
            return query[0].strip()
    channel = query_values.get("channel", [])
    if channel and channel[0].strip():
        return channel[0].strip()
    return payload["surface"]


def build_agent_config(db: Session, campaign: Campaign) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    api_key = ensure_campaign_api_key(campaign)
    profile = campaign.brand_voice_profile
    context = campaign.brand_context_profile
    safeguards = campaign.listener_config.get("safeguards", {})
    live_status = effective_listener_status(campaign)
    memory = build_memory_summary(db, campaign)
    seeded_context_summary, seeded_context_items = build_context_seed_summary(db, campaign.id)
    competition = normalize_competition_config(campaign.listener_config.get("competition"))
    products = []
    for product in get_products_for_campaign(campaign):
        attributes = product.attributes if isinstance(product.attributes, dict) else {}
        key_selling_points = attributes.get("key_features", [])[:3]
        if attributes.get("made_in"):
            key_selling_points.append(f"Made in {attributes['made_in']}")
        products.append(
            {
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "currency": product.currency,
                "description": product.description,
                "category": product.category,
                "attributes": attributes,
                "material": attributes.get("material"),
                "activities": attributes.get("activities", []),
                "url": product.source_url,
                "referral_base": build_referral_base(product.id),
                "key_selling_points": key_selling_points,
            }
        )

    return {
        "campaign_id": campaign.id,
        "status": live_status,
        "campaign_status": campaign.status,
        "operating_mode": "propose_only",
        "manual_execution_required": True,
        "approval_required": True,
        "brand": {
            "name": profile.get("brand_name") or campaign.merchant.name or "Brand",
            "domain": campaign.merchant.domain,
            "voice": build_brand_voice_text(campaign),
            "story": profile.get("story"),
            "dos": profile.get("dos", []),
            "donts": profile.get("donts", []),
            "disclosure": build_brand_disclosure(campaign),
        },
        "products": products,
        "budget": {
            "monthly": campaign.budget_monthly,
            "spent": round(campaign.budget_spent, 2),
            "remaining": budget_remaining(campaign),
            "currency": "USD",
        },
        "objective": {
            "primary_goal": "Get real sales for the active catalog while keeping attributed sales above compute cost.",
            "optimization_equation": "sales > compute_cost",
            "budget_limit": campaign.budget_monthly,
            "operating_principle": (
                "Objective-first. The agent owns the result and chooses tactics, surfaces, sequencing, "
                "and experiments based on expected return on compute."
            ),
            "tactical_freedom": [
                "Search the internet for opportunities",
                "Invent tactics instead of following a channel plan",
                "Use whatever public-web path looks most likely to create profitable sales",
                "Experiment, learn, and adapt continuously",
            ],
        },
        "memory": memory,
        "reporting": {
            "events_endpoint": f"{settings.public_api_url}/api/campaigns/{campaign.id}/events",
            "api_key": api_key,
        },
        "constraints": {
            "always_disclose_ai": bool(safeguards.get("always_disclose_ai", True)),
            "always_use_referral_links": True,
            "never_spam": False,
            "never_disparage_competitors": False,
            "max_actions_per_day": int(
                campaign.listener_config.get("max_actions_per_day")
                or safeguards.get("max_actions_per_day", 50)
            ),
        },
        "context": {
            "positioning": context.get("positioning", ""),
            "ideal_customer": context.get("ideal_customer", ""),
            "key_messages": context.get("key_messages", []),
            "proof_points": context.get("proof_points", []),
            "objection_handling": context.get("objection_handling", []),
            "prohibited_claims": context.get("prohibited_claims", []),
            "additional_context": context.get("additional_context", ""),
            "seeded_context_summary": seeded_context_summary,
            "seeded_context_items": seeded_context_items,
        },
        "competition": {
            "enabled": competition.get("enabled", False),
            "mode": competition.get("mode", "single_lane"),
            "lanes": competition.get("lanes", []),
        },
    }


def find_signal_by_source(
    db: Session,
    campaign_id: str,
    source_url: str | None,
    source_content: str,
    created_at: datetime,
) -> IntentSignal | None:
    signals = db.scalars(
        select(IntentSignal)
        .where(IntentSignal.campaign_id == campaign_id)
        .order_by(IntentSignal.created_at.desc())
    ).all()
    for signal in signals[:50]:
        same_url = source_url and signal.content_url == source_url
        same_text = signal.content_text.strip() == source_content.strip()
        recent = abs((ensure_utc(signal.created_at) - ensure_utc(created_at)).total_seconds()) < 7200
        if recent and (same_url or same_text):
            return signal
    return None


def hash_value(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def select_templates(config: dict[str, Any]) -> list[dict[str, Any]]:
    enabled_surfaces = {surface["type"] for surface in config.get("surfaces", []) if surface.get("enabled", True)}
    templates = [template for template in DEMO_SIGNAL_LIBRARY if template["surface"] in enabled_surfaces]
    return templates or DEMO_SIGNAL_LIBRARY


def choose_product(products: list[Product], template: dict[str, Any]) -> Product | None:
    if not products:
        return None
    content_blob = " ".join([template.get("content_text", ""), template.get("context_text", "")]).lower()
    best_product = None
    best_score = -1
    for product in products:
        score = 0
        if product.category and product.category.replace("_", " ") in content_blob:
            score += 20
        if product.subcategory and product.subcategory.replace("_", " ") in content_blob:
            score += 18
        attributes = product.attributes if isinstance(product.attributes, dict) else {}
        for keyword in attributes.get("activities", []):
            if keyword in content_blob:
                score += 10
        for feature in attributes.get("key_features", []):
            if feature.lower().split()[0] in content_blob:
                score += 6
        if "chaf" in content_blob and "High Movement" in product.name:
            score += 16
        if "yoga" in content_blob and "Supersoft" in product.name:
            score += 16
        if "recovery" in content_blob and "Recovery" in product.name:
            score += 16
        if score > best_score:
            best_score = score
            best_product = product
    return best_product or products[0]


def score_template(
    template: dict[str, Any],
    product: Product | None,
    aggressiveness: str,
) -> dict[str, Any]:
    text = f"{template.get('content_text', '')} {template.get('context_text', '')}".lower()
    recommendation_terms = ["recommend", "rec", "looking for", "best", "any", "help", "need"]
    active_terms = ["running", "cycling", "lifting", "workout", "yoga", "pilates", "recovery", "sleep"]
    relevance = 50 + sum(9 for term in active_terms if term in text)
    intent = 44 + sum(10 for term in recommendation_terms if term in text)
    receptivity = 48 + (18 if "?" in template.get("content_text", "") else 0)
    fit = 48
    if product is not None:
        if product.category and any(token in text for token in product.category.replace("_", " ").split()):
            fit += 16
        if product.subcategory and product.subcategory in text:
            fit += 12
        attributes = product.attributes if isinstance(product.attributes, dict) else {}
        fit += min(24, sum(7 for activity in attributes.get("activities", []) if activity in text))

    relevance = min(relevance, 100)
    intent = min(intent, 100)
    receptivity = min(receptivity, 100)
    fit = min(fit, 100)
    composite = round(relevance * 0.3 + intent * 0.3 + fit * 0.2 + receptivity * 0.2, 1)

    thresholds = threshold_config(aggressiveness)
    should_respond = composite >= thresholds["composite_min"] or (
        composite >= thresholds["composite_min"] - 15 and receptivity >= thresholds["receptivity_min"]
    )
    response_type = "skip"
    if should_respond:
        response_type = "recommendation" if intent >= 60 and fit >= 58 else "helpful_info"
    reasoning = (
        "The person is explicitly asking for a product recommendation and the product attributes line up well."
        if should_respond
        else "The signal is either too low-intent or the product fit is not strong enough to justify a reply."
    )
    return {
        "relevance": int(relevance),
        "intent": int(intent),
        "fit": int(fit),
        "receptivity": int(receptivity),
        "composite": composite,
        "reasoning": reasoning,
        "should_respond": should_respond,
        "response_type": response_type,
    }


def build_referral_url(product: Product | None, surface: str, campaign_id: str, response_id: str | None) -> str | None:
    if product is None or response_id is None:
        return None
    return f"https://ever.com/go/{product.id}?src={surface}&cid={campaign_id}&iid={response_id}"


def surface_disclosure(surface: str, brand_name: str) -> str:
    if surface == "twitter":
        return f"— Ever AI for {brand_name}"
    return f"Disclosure: I'm Ever, an AI agent for {brand_name}."


def build_response_text(
    campaign: Campaign,
    template: dict[str, Any],
    product: Product | None,
    score: dict[str, Any],
) -> str:
    profile = campaign.brand_voice_profile
    brand_name = profile.get("brand_name") or campaign.merchant.name or "the brand"
    if product is None:
        return f"Happy to help, but this one looks like a weak fit for {brand_name} right now. {surface_disclosure(template['surface'], brand_name)}"

    attributes = product.attributes if isinstance(product.attributes, dict) else {}
    key_features = attributes.get("key_features", [])
    first_feature = key_features[0] if key_features else "a premium fit"
    second_feature = key_features[1] if len(key_features) > 1 else "comfort that holds up through movement"
    helpful_openers = {
        "reddit": (
            "If the goal is to stay comfortable through the workout, the biggest thing is finding something that stays put and breathes well."
        ),
        "twitter": "The big thing is finding something low-profile that still stays put when you start moving.",
    }
    opener = helpful_openers.get(template["surface"], helpful_openers["reddit"])
    recommendation = (
        f"{brand_name}'s {product.name} is a good fit here because it leans on {first_feature.lower()} and {second_feature.lower()}."
    )
    disclosure = surface_disclosure(template["surface"], brand_name)
    if template["surface"] == "twitter":
        return f"{opener} {recommendation} {disclosure}"
    return f"{opener} {recommendation} {disclosure}"


def confidence_for_score(score: dict[str, Any]) -> float:
    return round(min(98.0, score["composite"] + (score["fit"] - 50) * 0.18), 1)


def needs_human_review(campaign: Campaign, config: dict[str, Any], confidence: float) -> bool:
    auto_threshold = int(config.get("auto_post_after_approvals", 50) or 50)
    review_mode = config.get("review_mode", "manual")
    if review_mode == "manual":
        return True
    if campaign.approved_response_count < auto_threshold:
        return True
    return confidence < 70


def post_url(signal: IntentSignal, response: AgentResponse) -> str:
    if signal.content_url:
        return f"{signal.content_url}#ever-response-{response.id[:8]}"
    if response.surface == "twitter":
        return f"https://x.com/everagent/status/{response.id[:12]}"
    channel = signal.subreddit_or_channel or "intent"
    return f"https://reddit.com/r/{channel}/comments/{signal.platform_content_id or response.id[:8]}"


def simulate_click_and_conversion(db: Session, response: AgentResponse) -> None:
    if response.product_id is None or not response.posted:
        return
    existing_click = db.scalar(select(Click).where(Click.response_id == response.id))
    if existing_click is not None:
        return

    seed = hash_value(response.id)
    click_threshold = seed % 100
    if click_threshold >= 74:
        return

    click_time = ensure_utc(response.posted_at or response.created_at) + timedelta(minutes=8 + seed % 120)
    click = Click(
        match_id=None,
        product_id=response.product_id,
        campaign_id=response.campaign_id,
        channel="intent_listener",
        source="intent_listener",
        surface=response.surface,
        response_id=response.id,
        created_at=click_time,
    )
    db.add(click)
    db.flush()

    if click_threshold < 26 and response.product is not None:
        multiplier = 1.0 if "Thong" in response.product.name else 1.18
        conversion = Conversion(
            click_id=click.id,
            product_id=response.product_id,
            campaign_id=response.campaign_id,
            order_value=round(response.product.price * multiplier, 2),
            channel="intent_listener",
            created_at=click_time + timedelta(minutes=12 + seed % 180),
        )
        db.add(conversion)


def within_response_limits(db: Session, campaign: Campaign, surface: str, author_handle: str | None) -> bool:
    config = campaign.listener_config
    safeguards = config.get("safeguards", {})
    now = utcnow()
    start_of_day = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    responses_today = db.scalars(
        select(AgentResponse)
        .where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.posted.is_(True),
            AgentResponse.posted_at >= start_of_day,
        )
    ).all()
    if len(responses_today) >= int(safeguards.get("max_responses_per_day", 50)):
        return False
    if sum(1 for response in responses_today if response.surface == surface) >= int(
        safeguards.get("max_responses_per_surface_per_day", 10)
    ):
        return False
    surface_recent = [
        response
        for response in responses_today
        if response.surface == surface
        and response.posted_at is not None
        and ensure_utc(response.posted_at) >= now - timedelta(
            minutes=int(safeguards.get("minimum_minutes_between_surface_responses", 5))
        )
    ]
    if surface_recent:
        return False
    if author_handle and safeguards.get("one_response_per_author_per_day", True):
        recent_authors = db.scalars(
            select(IntentSignal)
            .join(AgentResponse, AgentResponse.signal_id == IntentSignal.id)
            .where(
                IntentSignal.campaign_id == campaign.id,
                IntentSignal.author_handle == author_handle,
                AgentResponse.posted.is_(True),
                AgentResponse.posted_at >= now - timedelta(days=1),
            )
        ).all()
        if recent_authors:
            return False
    return True


def create_signal(
    db: Session,
    campaign: Campaign,
    template: dict[str, Any],
    created_at: datetime,
) -> tuple[IntentSignal, AgentResponse | None]:
    products = get_products_for_campaign(campaign)
    product = choose_product(products, template)
    aggressiveness = campaign.listener_config.get("aggressiveness", "balanced")
    score = score_template(template, product, aggressiveness)
    platform_content_id = f"{template['surface'][:1]}_{hash_value(template['content_text'] + created_at.isoformat())}"
    signal = IntentSignal(
        campaign_id=campaign.id,
        product_id=product.id if product else None,
        surface=template["surface"],
        platform_content_id=platform_content_id,
        content_text=template["content_text"],
        content_url=build_content_url(template["surface"], template.get("subreddit_or_channel"), platform_content_id),
        context_text=template.get("context_text"),
        author_handle=template.get("author_handle"),
        subreddit_or_channel=template.get("subreddit_or_channel"),
        intent_score=score,
        composite_score=score["composite"],
        should_respond=bool(score["should_respond"]),
        response_type=score["response_type"],
        scoring_tokens_used=610 + hash_value(platform_content_id) % 280,
        scoring_cost=round(0.0028 + (hash_value(platform_content_id) % 18) / 10_000, 4),
        created_at=created_at,
    )
    db.add(signal)
    db.flush()

    if not score["should_respond"] or not within_response_limits(
        db,
        campaign,
        template["surface"],
        template.get("author_handle"),
    ):
        return signal, None

    confidence = confidence_for_score(score)
    response = AgentResponse(
        signal_id=signal.id,
        campaign_id=campaign.id,
        product_id=product.id if product else None,
        surface=template["surface"],
        response_text=build_response_text(campaign, template, product, score),
        referral_url=None,
        url_placement="inline" if template["surface"] == "reddit" else "separate_line",
        confidence=confidence,
        platform_appropriate=True,
        needs_review=needs_human_review(campaign, campaign.listener_config, confidence),
        review_status="pending",
        generation_tokens_used=1040 + hash_value(signal.id) % 420,
        generation_cost=round(0.0064 + (hash_value(signal.id) % 24) / 10_000, 4),
        created_at=created_at + timedelta(minutes=2),
    )
    db.add(response)
    db.flush()
    response.referral_url = build_referral_url(product, template["surface"], campaign.id, response.id)
    return signal, response


def build_content_url(surface: str, subreddit_or_channel: str | None, platform_content_id: str) -> str:
    if surface == "twitter":
        return f"https://x.com/i/status/{platform_content_id[-10:]}"
    channel = subreddit_or_channel or "running"
    return f"https://reddit.com/r/{channel}/comments/{platform_content_id[-10:]}"


def parse_event_timestamp(raw_timestamp: str) -> datetime:
    normalized = raw_timestamp.replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(normalized))


def should_create_response_record(event_type: str, action_taken: str) -> bool:
    return event_type != "intent_detected" and action_taken != "skip"


def upsert_signal_from_event(
    db: Session,
    campaign: Campaign,
    payload: dict[str, Any],
    created_at: datetime,
) -> tuple[IntentSignal, float]:
    existing = find_signal_by_source(
        db,
        campaign.id,
        payload.get("source_url"),
        payload["source_content"],
        created_at,
    )
    incremental_cost = 0.0
    intent_score = payload.get("intent_score", {})
    source_channel = parse_source_channel(payload)
    if existing is None:
        existing = IntentSignal(
            campaign_id=campaign.id,
            product_id=payload.get("product_id"),
            surface=payload["surface"],
            platform_content_id=f"{payload['surface'][:1]}_{uuid4().hex[:10]}",
            content_text=payload["source_content"],
            content_url=payload.get("source_url"),
            context_text=payload.get("source_context"),
            author_handle=payload.get("source_author"),
            subreddit_or_channel=source_channel,
            intent_score=intent_score,
            composite_score=float(intent_score.get("composite", 0.0) or 0.0),
            should_respond=payload.get("action_taken") != "skip",
            response_type="skip" if payload.get("action_taken") == "skip" else "recommendation",
            scoring_tokens_used=0,
            scoring_cost=0.0,
            created_at=created_at,
        )
        db.add(existing)
        db.flush()

    existing.product_id = payload.get("product_id") or existing.product_id
    existing.intent_score = intent_score or existing.intent_score
    existing.composite_score = float(intent_score.get("composite", existing.composite_score) or existing.composite_score)
    existing.content_url = payload.get("source_url") or existing.content_url
    existing.context_text = payload.get("source_context") or existing.context_text
    existing.author_handle = payload.get("source_author") or existing.author_handle
    existing.subreddit_or_channel = source_channel or existing.subreddit_or_channel or payload["surface"]
    existing.surface = payload["surface"]
    existing.should_respond = payload.get("action_taken") != "skip"

    if payload["event_type"] == "intent_detected" and existing.scoring_cost == 0:
        existing.scoring_tokens_used = int(payload.get("tokens_used", 0))
        existing.scoring_cost = float(payload.get("compute_cost_usd", 0.0) or 0.0)
        incremental_cost += existing.scoring_cost
    return existing, incremental_cost


def create_response_from_event(
    db: Session,
    campaign: Campaign,
    signal: IntentSignal,
    payload: dict[str, Any],
    created_at: datetime,
) -> tuple[AgentResponse | None, float, bool]:
    if not should_create_response_record(payload["event_type"], payload["action_taken"]):
        return None, 0.0, False

    interaction_id = parse_interaction_id(payload.get("referral_url")) or signal.id
    referral_url = payload.get("referral_url")
    if not referral_url and payload.get("product_id"):
        referral_url = (
            f"{build_referral_base(payload['product_id'])}"
            f"?src={payload['surface']}&cid={campaign.id}&iid={interaction_id}"
        )
    response = db.scalar(
        select(AgentResponse).where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.id == interaction_id,
        )
    )
    incremental_cost = 0.0
    posted = payload["event_type"] in {"response_posted", "dm_sent", "email_sent"}
    review_status = (
        "pending"
        if payload["event_type"] == "response_pending_review"
        else "rejected"
        if payload["event_type"] == "response_skipped"
        else "auto_approved"
    )
    if response is None:
        total_cost = float(payload.get("compute_cost_usd", 0.0) or 0.0)
        generation_cost = total_cost
        if signal.scoring_cost == 0 and total_cost > 0 and payload.get("intent_score", {}).get("composite"):
            signal.scoring_cost = round(total_cost * 0.35, 4)
            signal.scoring_tokens_used = int(payload.get("tokens_used", 0) * 0.35)
            generation_cost = round(total_cost - signal.scoring_cost, 4)
            incremental_cost += signal.scoring_cost
        response = AgentResponse(
            id=interaction_id,
            signal_id=signal.id,
            campaign_id=campaign.id,
            product_id=payload.get("product_id"),
            surface=payload["surface"],
            response_text=payload.get("response_text") or "",
            referral_url=referral_url,
            url_placement="inline" if payload.get("action_taken") == "reply" else "separate_line",
            confidence=float(payload.get("intent_score", {}).get("composite", 0.0) or 0.0),
            platform_appropriate=True,
            needs_review=payload["event_type"] == "response_pending_review",
            review_status=review_status,
            reviewed_at=created_at if review_status != "pending" else None,
            posted=posted,
            posted_url=payload.get("source_url") if posted else None,
            posted_at=created_at if posted else None,
            generation_tokens_used=max(int(payload.get("tokens_used", 0)) - signal.scoring_tokens_used, 0),
            generation_cost=generation_cost,
            created_at=created_at,
        )
        db.add(response)
        db.flush()
        incremental_cost += response.generation_cost
        became_posted_approved = posted and review_status in {"approved", "auto_approved"}
    else:
        already_posted_approved = response.posted and response.review_status in {"approved", "auto_approved"}
        response.response_text = payload.get("response_text") or response.response_text
        response.referral_url = referral_url or response.referral_url
        response.product_id = payload.get("product_id") or response.product_id
        response.surface = payload["surface"]
        response.posted = posted or response.posted
        response.posted_url = payload.get("source_url") if posted else response.posted_url
        response.posted_at = created_at if posted else response.posted_at
        response.review_status = review_status
        response.needs_review = payload["event_type"] == "response_pending_review"
        became_posted_approved = (
            not already_posted_approved
            and response.posted
            and response.review_status in {"approved", "auto_approved"}
        )

    return response, incremental_cost, became_posted_approved


def record_agent_event(
    db: Session,
    campaign: Campaign,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    if campaign.listener_config.get("listener_mode") != "live":
        campaign.listener_config = {
            **campaign.listener_config,
            "listener_mode": "live",
        }
    created_at = parse_event_timestamp(payload["timestamp"])
    if payload.get("event_type") == "proposal":
        try:
            proposal = create_proposal_from_event(db, campaign, payload, created_at)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        campaign.listener_last_polled_at = utcnow()
        if campaign.status == "active" and campaign.listener_status != "budget_exhausted":
            campaign.listener_status = "running"
        db.commit()
        db.refresh(campaign)
        budget_left = budget_remaining(campaign)
        return {
            "event_id": proposal.id,
            "proposal_id": proposal.id,
            "status": proposal.status,
            "budget_remaining": budget_left,
            "budget_exhausted": budget_left <= 0,
        }

    event = persist_agent_event(db, campaign, payload, created_at)
    update_campaign_budget_state(db, campaign)
    campaign.listener_last_polled_at = utcnow()
    next_status = effective_listener_status(campaign)
    campaign.listener_status = "running" if next_status == "running" else next_status

    db.commit()
    db.refresh(campaign)
    budget_left = budget_remaining(campaign)
    return {
        "event_id": event.id,
        "status": "recorded",
        "budget_remaining": budget_left,
        "budget_exhausted": budget_left <= 0,
    }


def seed_listener_history(db: Session, campaign: Campaign) -> None:
    existing_signal = db.scalar(select(IntentSignal.id).where(IntentSignal.campaign_id == campaign.id).limit(1))
    if existing_signal is not None:
        return

    templates = select_templates(campaign.listener_config)
    rng = random.Random(f"{campaign.id}:listener-history")
    now = utcnow()
    responses: list[AgentResponse] = []

    for day_offset in range(17, -1, -1):
        day = now - timedelta(days=day_offset)
        signals_for_day = 2 + rng.randint(0, 2)
        for signal_index in range(signals_for_day):
            template = templates[(day_offset * 3 + signal_index) % len(templates)]
            created_at = day.replace(
                hour=9 + ((signal_index * 3 + rng.randint(0, 4)) % 10),
                minute=(signal_index * 11 + rng.randint(0, 30)) % 60,
                second=0,
                microsecond=0,
            )
            _, response = create_signal(db, campaign, template, created_at)
            if response is not None:
                responses.append(response)

    responses.sort(key=lambda item: item.created_at)
    pending_count = min(5, len(responses))
    pending_ids = {response.id for response in responses[-pending_count:]}

    for index, response in enumerate(responses):
        if response.id in pending_ids:
            response.needs_review = True
            response.review_status = "pending"
            continue

        if index % 6 == 5:
            response.needs_review = False
            response.review_status = "rejected"
            response.reviewed_at = response.created_at + timedelta(minutes=18)
            continue

        response.needs_review = False
        response.review_status = "approved"
        response.reviewed_at = response.created_at + timedelta(minutes=14)
        response.posted = True
        response.posted_at = response.reviewed_at + timedelta(minutes=4)
        response.posted_url = post_url(response.signal, response)
        campaign.approved_response_count += 1
        simulate_click_and_conversion(db, response)

    campaign.listener_started_at = campaign.listener_started_at or now - timedelta(days=18)
    campaign.listener_last_polled_at = now


def maybe_generate_fresh_signals(db: Session, campaign: Campaign, force: bool = False) -> None:
    if campaign.listener_status != "running":
        return

    poll_interval_seconds = min(
        (
            int(surface.get("poll_interval_seconds", 180))
            for surface in campaign.listener_config.get("surfaces", [])
            if surface.get("enabled", True)
        ),
        default=180,
    )
    now = utcnow()
    if not force and campaign.listener_last_polled_at is not None:
        elapsed = (now - ensure_utc(campaign.listener_last_polled_at)).total_seconds()
        if elapsed < poll_interval_seconds:
            return

    templates = select_templates(campaign.listener_config)
    fresh_count = 1 + hash_value(f"{campaign.id}:{now.date().isoformat()}:{now.hour}") % 2
    for index in range(fresh_count):
        template = templates[(hash_value(f"{campaign.id}:{now.isoformat()}:{index}") + index) % len(templates)]
        created_at = now - timedelta(minutes=18 - index * 6)
        signal, response = create_signal(db, campaign, template, created_at)
        if response is None:
            continue
        if needs_human_review(campaign, campaign.listener_config, response.confidence):
            response.needs_review = True
            response.review_status = "pending"
            continue
        response.needs_review = False
        response.review_status = "auto_approved"
        response.reviewed_at = created_at + timedelta(minutes=2)
        response.posted = True
        response.posted_at = response.reviewed_at + timedelta(minutes=2)
        response.posted_url = post_url(signal, response)
        campaign.approved_response_count += 1
        simulate_click_and_conversion(db, response)

    campaign.listener_last_polled_at = now


def build_listener_status(db: Session, campaign: Campaign, refresh: bool = True) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    if refresh:
        refresh_simulation_if_needed(db, campaign)
    today_start = datetime.combine(utcnow().date(), datetime.min.time(), tzinfo=timezone.utc)
    events_today = db.scalars(
        select(AgentEvent).where(
            AgentEvent.campaign_id == campaign.id,
            AgentEvent.created_at >= today_start,
        )
    ).all()
    proposals_today = db.scalars(
        select(Proposal).where(
            Proposal.campaign_id == campaign.id,
            Proposal.created_at >= today_start,
        )
    ).all()
    pending_proposals = db.scalars(
        select(Proposal).where(
            Proposal.campaign_id == campaign.id,
            Proposal.status == "proposed",
        )
    ).all()
    pending_responses = db.scalars(
        select(AgentResponse).where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.review_status == "pending",
        )
    ).all()
    actions_today = [event for event in events_today if event.event_type == "action"]
    strategy_updates_today = [event for event in events_today if event.event_type == "strategy_update"]
    response_like_actions = [
        event
        for event in actions_today
        if event.category in {"engagement", "outreach"} and (event.response_text or event.referral_url)
    ]
    compute_spent_today = round(
        sum(event.compute_cost_usd for event in events_today)
        + sum(proposal.compute_cost_usd for proposal in proposals_today),
        2,
    )
    active_surfaces = sorted(
        {
            *(event.surface for event in events_today if event.surface and event.event_type != "metering"),
            *(proposal.surface for proposal in proposals_today if proposal.surface),
        }
    )
    latest_event = db.scalar(
        select(AgentEvent.created_at)
        .where(AgentEvent.campaign_id == campaign.id)
        .order_by(AgentEvent.created_at.desc())
        .limit(1)
    )
    latest_proposal = db.scalar(
        select(Proposal.created_at)
        .where(Proposal.campaign_id == campaign.id)
        .order_by(Proposal.created_at.desc())
        .limit(1)
    )
    last_active = max(
        [value for value in [campaign.listener_last_polled_at, latest_event, latest_proposal] if value is not None],
        default=None,
    )
    current_status = effective_listener_status(campaign)
    uptime_hours = (
        round((utcnow() - ensure_utc(campaign.listener_started_at)).total_seconds() / 3600, 1)
        if campaign.listener_started_at
        else 0.0
    )
    return {
        "campaign_id": campaign.id,
        "status": current_status,
        "last_active": last_active.isoformat() if last_active else None,
        "last_polled_at": campaign.listener_last_polled_at.isoformat() if campaign.listener_last_polled_at else None,
        "actions_today": len(actions_today),
        "strategy_updates_today": len(strategy_updates_today),
        "active_surfaces": active_surfaces,
        "active_surface_count": len(active_surfaces),
        "surfaces_active": active_surfaces,
        "surfaces_active_count": len(active_surfaces),
        "signals_today": len(actions_today) + len(proposals_today),
        "responses_today": len(response_like_actions),
        "budget_remaining": budget_remaining(campaign),
        "uptime_hours": uptime_hours,
        "signals_detected_today": len(actions_today) + len(proposals_today),
        "responses_pending_review": len(pending_responses),
        "proposals_pending": len(pending_proposals),
        "compute_spent_today": compute_spent_today,
        "approved_response_count": campaign.approved_response_count,
        "operating_mode": "propose_only",
        "manual_execution_required": True,
        "approval_required": True,
        "brand_voice_profile": campaign.brand_voice_profile,
        "brand_context_profile": campaign.brand_context_profile,
        "config": campaign.listener_config,
    }


def start_listener(db: Session, campaign: Campaign) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    if campaign.status in {"paused_budget"} or budget_remaining(campaign) <= 0:
        campaign.listener_status = "budget_exhausted"
        db.commit()
        db.refresh(campaign)
        return build_listener_status(db, campaign, refresh=False)
    if campaign.status not in {"active"} and listener_mode(campaign) == "live":
        raise ValueError("Campaign must be paid and active before launching the live agent.")
    campaign.listener_status = "running"
    campaign.listener_started_at = campaign.listener_started_at or utcnow()
    if listener_mode(campaign) == "live":
        api_key = ensure_campaign_api_key(campaign)
        launch_openclaw_agent(campaign, api_key)
    else:
        stop_openclaw_agent(campaign.id)
        seed_agent_history(db, campaign)
        maybe_generate_fresh_agent_events(db, campaign, force=True)
    db.commit()
    db.refresh(campaign)
    return build_listener_status(db, campaign, refresh=False)


def stop_listener(db: Session, campaign: Campaign) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    campaign.listener_status = "stopped"
    stop_openclaw_agent(campaign.id)
    db.commit()
    db.refresh(campaign)
    return build_listener_status(db, campaign, refresh=False)


def update_listener_config(
    db: Session,
    campaign: Campaign,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    incoming_profile = payload.get("brand_voice_profile")
    incoming_context = payload.get("brand_context_profile")
    incoming_config = payload.get("config")
    previous_mode = listener_mode(campaign)
    if incoming_profile is not None:
        campaign.brand_voice_profile = normalize_brand_voice(incoming_profile, campaign)
    if incoming_context is not None:
        campaign.brand_context_profile = normalize_brand_context(incoming_context, campaign)
    if incoming_config is not None:
        campaign.listener_config = normalize_listener_config(incoming_config)
    if previous_mode == "live" and listener_mode(campaign) == "simulation":
        stop_openclaw_agent(campaign.id)
    db.commit()
    db.refresh(campaign)
    return build_listener_status(db, campaign, refresh=False)


def review_queue(db: Session, campaign: Campaign) -> list[dict[str, Any]]:
    ensure_listener_defaults(campaign)
    refresh_simulation_if_needed(db, campaign)
    responses = db.scalars(
        select(AgentResponse)
        .where(AgentResponse.campaign_id == campaign.id, AgentResponse.review_status == "pending")
        .options(
            joinedload(AgentResponse.signal),
            joinedload(AgentResponse.product),
        )
        .order_by(AgentResponse.created_at.desc())
    ).all()
    return [build_review_item(response) for response in responses]


def build_review_item(response: AgentResponse) -> dict[str, Any]:
    product_name = response.product.name if response.product else None
    signal = response.signal
    return {
        "response_id": response.id,
        "signal_id": signal.id,
        "surface": response.surface,
        "subreddit_or_channel": signal.subreddit_or_channel,
        "content_text": signal.content_text,
        "context_text": signal.context_text,
        "content_url": signal.content_url,
        "product_id": response.product_id,
        "product_name": product_name,
        "intent_score": signal.intent_score,
        "response_text": response.response_text,
        "referral_url": response.referral_url,
        "confidence": response.confidence,
        "needs_review": response.needs_review,
        "review_status": response.review_status,
        "created_at": response.created_at.isoformat(),
        "relative_time": relative_time(response.created_at),
    }


def find_review_response(db: Session, campaign: Campaign, response_id: str) -> AgentResponse:
    response = db.scalar(
        select(AgentResponse)
        .where(AgentResponse.campaign_id == campaign.id, AgentResponse.id == response_id)
        .options(joinedload(AgentResponse.signal), joinedload(AgentResponse.product))
    )
    if response is None:
        raise ValueError("Review response not found")
    return response


def approve_response(db: Session, campaign: Campaign, response_id: str) -> dict[str, Any]:
    response = find_review_response(db, campaign, response_id)
    if response.review_status == "pending":
        response.review_status = "approved"
        response.needs_review = False
        response.reviewed_at = utcnow()
        response.posted = True
        response.posted_at = response.reviewed_at + timedelta(minutes=1)
        response.posted_url = post_url(response.signal, response)
        campaign.approved_response_count += 1
        simulate_click_and_conversion(db, response)
        db.commit()
        db.refresh(response)
    return build_review_item(response)


def reject_response(db: Session, campaign: Campaign, response_id: str) -> dict[str, Any]:
    response = find_review_response(db, campaign, response_id)
    if response.review_status == "pending":
        response.review_status = "rejected"
        response.needs_review = False
        response.reviewed_at = utcnow()
        db.commit()
        db.refresh(response)
    return build_review_item(response)


def edit_response(db: Session, campaign: Campaign, response_id: str, response_text: str) -> dict[str, Any]:
    response = find_review_response(db, campaign, response_id)
    response.response_text = response_text.strip()
    db.commit()
    db.refresh(response)
    return build_review_item(response)


def build_listener_analytics(db: Session, campaign: Campaign, period: str = "7d") -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    refresh_simulation_if_needed(db, campaign)
    period_map = {"7d": 7, "30d": 30, "90d": 90}
    days = period_map.get(period, 120)
    start_at = utcnow() - timedelta(days=days - 1)
    events = db.scalars(
        select(AgentEvent)
        .where(AgentEvent.campaign_id == campaign.id, AgentEvent.created_at >= start_at)
        .options(joinedload(AgentEvent.product))
        .order_by(AgentEvent.created_at.asc())
    ).all()
    proposals = db.scalars(
        select(Proposal)
        .where(Proposal.campaign_id == campaign.id, Proposal.created_at >= start_at)
        .options(joinedload(Proposal.product))
        .order_by(Proposal.created_at.asc())
    ).all()
    clicks = db.scalars(
        select(Click)
        .where(
            Click.campaign_id == campaign.id,
            Click.created_at >= start_at,
            Click.source.in_(["proposal", "autonomous_agent", "intent_listener"]),
        )
        .options(joinedload(Click.product))
    ).all()
    conversions = db.scalars(
        select(Conversion)
        .where(
            Conversion.campaign_id == campaign.id,
            Conversion.created_at >= start_at,
            Conversion.channel.in_(["proposal", "autonomous_agent", "intent_listener"]),
        )
        .options(joinedload(Conversion.product), joinedload(Conversion.click))
    ).all()
    pending_responses = db.scalars(
        select(AgentResponse).where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.review_status == "pending",
        )
    ).all()

    action_events = [event for event in events if event.event_type == "action"]
    strategy_events = [event for event in events if event.event_type == "strategy_update"]
    metering_events = [event for event in events if event.event_type == "metering"]
    response_actions = [
        event for event in action_events if event.category in {"engagement", "outreach"}
    ]
    approved_proposals = [proposal for proposal in proposals if proposal.approved_at is not None]
    executed_proposals = [proposal for proposal in proposals if proposal.executed_at is not None]
    revenue = round(sum(conversion.order_value for conversion in conversions), 2)
    compute_cost = round(
        sum(event.compute_cost_usd for event in events)
        + sum(proposal.compute_cost_usd for proposal in proposals),
        2,
    )
    roc = round(revenue / compute_cost, 2) if compute_cost else 0.0

    surface_stats: dict[str, dict[str, float | int | str | None]] = defaultdict(
        lambda: {
            "surface": "other",
            "subreddit": None,
            "query": None,
            "subreddit_or_channel": None,
            "responses": 0,
            "signals_detected": 0,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "roc": 0.0,
        }
    )
    channel_breakdown: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {
            "surface": "other",
            "actions": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "return_on_compute": 0.0,
        }
    )
    product_stats: dict[str, dict[str, float | int | str | None]] = defaultdict(
        lambda: {
            "product_id": None,
            "name": None,
            "product_name": None,
            "surface": None,
            "responses": 0,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "roc": 0.0,
        }
    )
    model_breakdown: dict[tuple[str, str], dict[str, float | int | str]] = defaultdict(
        lambda: {
            "provider": "heuristic",
            "model": "objective-baseline",
            "label": "Heuristic baseline",
            "proposals": 0,
            "approved": 0,
            "executed": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "return_on_compute": 0.0,
        }
    )
    proposal_lookup = {proposal.id: proposal for proposal in proposals}

    for event in action_events:
        surface = event.surface or "other"
        surface_row = surface_stats[surface]
        surface_row["surface"] = surface
        surface_row["subreddit_or_channel"] = surface
        surface_row["signals_detected"] += 1
        surface_row["compute_cost"] += event.compute_cost_usd
        if event.category in {"engagement", "outreach"}:
            surface_row["responses"] += 1
            surface_row["responses_sent"] += 1

        channel_row = channel_breakdown[surface]
        channel_row["surface"] = surface
        channel_row["actions"] += 1
        channel_row["compute_cost"] += event.compute_cost_usd

        if event.product_id:
            product_row = product_stats[event.product_id]
            product_row["product_id"] = event.product_id
            product_row["name"] = event.product.name if event.product else "Product"
            product_row["product_name"] = event.product.name if event.product else "Product"
            product_row["surface"] = surface
            product_row["responses"] += 1
            if event.category in {"engagement", "outreach"}:
                product_row["responses_sent"] += 1
            product_row["compute_cost"] += event.compute_cost_usd

        provider = event.model_provider or "heuristic"
        model_name = event.model_name or "objective-baseline"
        model_row = model_breakdown[(provider, model_name)]
        model_row["provider"] = provider
        model_row["model"] = model_name
        model_row["label"] = f"{provider}:{model_name}"
        model_row["compute_cost"] += event.compute_cost_usd

    for event in metering_events:
        provider = event.model_provider or "external"
        model_name = event.model_name or "session-log"
        model_row = model_breakdown[(provider, model_name)]
        model_row["provider"] = provider
        model_row["model"] = model_name
        model_row["label"] = f"{provider}:{model_name}"
        model_row["compute_cost"] += event.compute_cost_usd

    for proposal in proposals:
        surface = proposal.surface or "other"
        surface_row = surface_stats[surface]
        surface_row["surface"] = surface
        surface_row["subreddit_or_channel"] = surface
        surface_row["signals_detected"] += 1
        surface_row["responses"] += 1
        if proposal.approved_at is not None:
            surface_row["responses_sent"] += 1
        surface_row["compute_cost"] += proposal.compute_cost_usd

        channel_row = channel_breakdown[surface]
        channel_row["surface"] = surface
        channel_row["actions"] += 1
        channel_row["compute_cost"] += proposal.compute_cost_usd

        if proposal.product_id:
            product_row = product_stats[proposal.product_id]
            product_row["product_id"] = proposal.product_id
            product_row["name"] = proposal.product.name if proposal.product else "Product"
            product_row["product_name"] = proposal.product.name if proposal.product else "Product"
            product_row["surface"] = surface
            product_row["responses"] += 1
            if proposal.approved_at is not None:
                product_row["responses_sent"] += 1
            product_row["compute_cost"] += proposal.compute_cost_usd

        provider = proposal.model_provider or "heuristic"
        model_name = proposal.model_name or "objective-baseline"
        model_row = model_breakdown[(provider, model_name)]
        model_row["provider"] = provider
        model_row["model"] = model_name
        model_row["label"] = f"{provider}:{model_name}"
        model_row["proposals"] += 1
        if proposal.approved_at is not None:
            model_row["approved"] += 1
        if proposal.executed_at is not None:
            model_row["executed"] += 1
        model_row["compute_cost"] += proposal.compute_cost_usd

    for click in clicks:
        surface = click.surface or "other"
        surface_stats[surface]["surface"] = surface
        surface_stats[surface]["subreddit_or_channel"] = surface
        surface_stats[surface]["clicks"] += 1
        channel_breakdown[surface]["surface"] = surface
        channel_breakdown[surface]["clicks"] += 1
        if click.product_id:
            product_row = product_stats[click.product_id]
            product_row["product_id"] = click.product_id
            product_row["name"] = click.product.name if click.product else "Product"
            product_row["product_name"] = click.product.name if click.product else "Product"
            product_row["surface"] = surface
            product_row["clicks"] += 1

    for conversion in conversions:
        surface = conversion.click.surface if conversion.click and conversion.click.surface else "other"
        surface_stats[surface]["surface"] = surface
        surface_stats[surface]["subreddit_or_channel"] = surface
        surface_stats[surface]["conversions"] += 1
        surface_stats[surface]["revenue"] += conversion.order_value
        channel_breakdown[surface]["surface"] = surface
        channel_breakdown[surface]["conversions"] += 1
        channel_breakdown[surface]["revenue"] += conversion.order_value
        product_row = product_stats[conversion.product_id]
        product_row["product_id"] = conversion.product_id
        product_row["name"] = conversion.product.name if conversion.product else "Product"
        product_row["product_name"] = conversion.product.name if conversion.product else "Product"
        product_row["surface"] = surface
        product_row["conversions"] += 1
        product_row["revenue"] += conversion.order_value
        if conversion.click and conversion.click.proposal_id:
            proposal = proposal_lookup.get(conversion.click.proposal_id)
            if proposal is not None:
                provider = proposal.model_provider or "heuristic"
                model_name = proposal.model_name or "objective-baseline"
                model_row = model_breakdown[(provider, model_name)]
                model_row["provider"] = provider
                model_row["model"] = model_name
                model_row["label"] = f"{provider}:{model_name}"
                model_row["conversions"] += 1
                model_row["revenue"] += conversion.order_value

    for stats in surface_stats.values():
        stats["revenue"] = round(float(stats["revenue"]), 2)
        stats["compute_cost"] = round(float(stats["compute_cost"]), 2)
        stats["roc"] = (
            round(float(stats["revenue"]) / float(stats["compute_cost"]), 2)
            if float(stats["compute_cost"])
            else 0.0
        )

    for stats in channel_breakdown.values():
        stats["revenue"] = round(float(stats["revenue"]), 2)
        stats["compute_cost"] = round(float(stats["compute_cost"]), 2)
        stats["return_on_compute"] = (
            round(float(stats["revenue"]) / float(stats["compute_cost"]), 2)
            if float(stats["compute_cost"])
            else 0.0
        )

    for row in product_stats.values():
        row["revenue"] = round(float(row["revenue"]), 2)
        row["compute_cost"] = round(float(row["compute_cost"]), 2)
        row["roc"] = (
            round(float(row["revenue"]) / float(row["compute_cost"]), 2)
            if float(row["compute_cost"])
            else 0.0
        )

    for row in model_breakdown.values():
        row["revenue"] = round(float(row["revenue"]), 2)
        row["compute_cost"] = round(float(row["compute_cost"]), 2)
        row["return_on_compute"] = (
            round(float(row["revenue"]) / float(row["compute_cost"]), 2)
            if float(row["compute_cost"])
            else 0.0
        )

    daily_map: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {
            "date": "",
            "actions_reported": 0,
            "strategy_updates": 0,
            "signals_detected": 0,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
        }
    )
    for event in action_events:
        key = ensure_utc(event.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["actions_reported"] += 1
        daily_map[key]["signals_detected"] += 1
        if event.category in {"engagement", "outreach"}:
            daily_map[key]["responses_sent"] += 1
        daily_map[key]["compute_cost"] += event.compute_cost_usd
    for proposal in proposals:
        key = ensure_utc(proposal.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["actions_reported"] += 1
        daily_map[key]["signals_detected"] += 1
        if proposal.approved_at is not None:
            daily_map[key]["responses_sent"] += 1
        daily_map[key]["compute_cost"] += proposal.compute_cost_usd
    for event in strategy_events:
        key = ensure_utc(event.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["strategy_updates"] += 1
    for event in metering_events:
        key = ensure_utc(event.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["compute_cost"] += event.compute_cost_usd
    for click in clicks:
        key = ensure_utc(click.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["clicks"] += 1
    for conversion in conversions:
        key = ensure_utc(conversion.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["conversions"] += 1
        daily_map[key]["revenue"] += conversion.order_value

    daily = []
    for offset in range(days):
        day = (start_at.date() + timedelta(days=offset)).isoformat()
        point = daily_map[day]
        point["date"] = day
        point["revenue"] = round(float(point["revenue"]), 2)
        point["compute_cost"] = round(float(point["compute_cost"]), 2)
        daily.append(point.copy())

    proposal_stats = {
        "total": len(proposals),
        "approved": len(approved_proposals),
        "executed": len(executed_proposals),
    }
    return {
        "period": period,
        "actions_reported": len(action_events) + len(proposals),
        "strategy_updates": len(strategy_events),
        "signals_detected": len(action_events) + len(proposals),
        "responses_sent": len(response_actions) + len(approved_proposals),
        "responses_pending_review": len(pending_responses),
        "proposals_generated": proposal_stats["total"],
        "proposals_approved": proposal_stats["approved"],
        "proposals_executed": proposal_stats["executed"],
        "execution_rate": round(proposal_stats["executed"] / proposal_stats["approved"], 4)
        if proposal_stats["approved"]
        else 0.0,
        "approval_rate": round(proposal_stats["approved"] / proposal_stats["total"], 4)
        if proposal_stats["total"]
        else 0.0,
        "response_rate": round(len(approved_proposals) / len(proposals), 4) if proposals else 0.0,
        "clicks": len(clicks),
        "click_through_rate": round(len(clicks) / len(executed_proposals), 4) if executed_proposals else 0.0,
        "conversions": len(conversions),
        "conversion_rate": round(len(conversions) / len(clicks), 4) if clicks else 0.0,
        "revenue": revenue,
        "compute_cost": compute_cost,
        "return_on_compute": roc,
        "top_surfaces": sorted(
            surface_stats.values(),
            key=lambda item: (float(item["roc"]), float(item["revenue"]), int(item["signals_detected"])),
            reverse=True,
        )[:6],
        "top_products": sorted(
            product_stats.values(),
            key=lambda item: (float(item["roc"]), float(item["revenue"]), int(item["responses_sent"])),
            reverse=True,
        )[:6],
        "top_subreddits": [
            {"label": row["surface"], "count": int(row["actions"])}
            for row in sorted(
                channel_breakdown.values(),
                key=lambda item: (float(item["return_on_compute"]), int(item["actions"])),
                reverse=True,
            )[:5]
        ],
        "intent_score_distribution": [],
        "channel_breakdown": sorted(
            channel_breakdown.values(),
            key=lambda item: (float(item["return_on_compute"]), float(item["revenue"]), int(item["actions"])),
            reverse=True,
        ),
        "model_breakdown": sorted(
            model_breakdown.values(),
            key=lambda item: (
                float(item["return_on_compute"]),
                float(item["revenue"]),
                int(item["proposals"]),
            ),
            reverse=True,
        ),
        "strategy_feed": [
            {
                "id": event.id,
                "description": event.description,
                "channels_used": list(event.details.get("channels_used", [])),
                "total_actions": int(event.details.get("total_actions") or 0),
                "compute_cost": round(event.compute_cost_usd, 4),
                "timestamp": event.created_at.isoformat(),
                "relative_time": relative_time(event.created_at),
            }
            for event in sorted(strategy_events, key=lambda item: item.created_at, reverse=True)[:8]
        ],
        "daily": daily,
        "daily_series": daily,
    }
