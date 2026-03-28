from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.entities import (
    AgentResponse,
    Campaign,
    Click,
    Conversion,
    IntentSignal,
    Merchant,
    Product,
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


def build_default_listener_config(campaign: Campaign) -> dict[str, Any]:
    aggressiveness = "balanced"
    return {
        "aggressiveness": aggressiveness,
        "review_mode": "manual",
        "auto_post_after_approvals": 50,
        "thresholds": threshold_config(aggressiveness),
        "safeguards": {
            "max_responses_per_surface_per_day": 10,
            "max_responses_per_day": 50,
            "max_thread_replies": 2,
            "minimum_minutes_between_surface_responses": 5,
            "minimum_post_age_minutes": 10,
            "one_response_per_author_per_day": True,
            "always_disclose_ai": True,
        },
        "surfaces": [
            {
                "type": "reddit",
                "enabled": True,
                "subreddits": [
                    "running",
                    "marathontraining",
                    "XXrunning",
                    "cycling",
                    "crossfit",
                    "femalefashionadvice",
                    "ABraThatFits",
                    "yoga",
                    "pilates",
                ],
                "keywords": ["underwear", "chafing", "thong", "workout underwear"],
                "search_queries": [],
                "poll_interval_seconds": 120,
            },
            {
                "type": "twitter",
                "enabled": True,
                "subreddits": [],
                "keywords": [
                    "workout underwear",
                    "running underwear chafing",
                    "athletic thong",
                    "gym underwear recommendation",
                ],
                "search_queries": [
                    "workout underwear recommendation",
                    "running underwear chafing",
                    "best athletic thong",
                    "organic cotton sleep set",
                ],
                "poll_interval_seconds": 180,
            },
        ],
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
    merged["thresholds"] = merge_dicts(threshold_config(aggressiveness), merged.get("thresholds", {}))
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
    return merged


def build_default_listener_config_for_values() -> dict[str, Any]:
    return {
        "aggressiveness": "balanced",
        "review_mode": "manual",
        "auto_post_after_approvals": 50,
        "thresholds": threshold_config("balanced"),
        "safeguards": {
            "max_responses_per_surface_per_day": 10,
            "max_responses_per_day": 50,
            "max_thread_replies": 2,
            "minimum_minutes_between_surface_responses": 5,
            "minimum_post_age_minutes": 10,
            "one_response_per_author_per_day": True,
            "always_disclose_ai": True,
        },
        "surfaces": [],
    }


def normalize_brand_voice(profile: dict[str, Any] | None, campaign: Campaign) -> dict[str, Any]:
    defaults = build_default_brand_voice(campaign)
    return merge_dicts(defaults, profile)


def ensure_listener_defaults(campaign: Campaign) -> None:
    campaign.brand_voice_profile = normalize_brand_voice(campaign.brand_voice_profile, campaign)
    if campaign.listener_config:
        campaign.listener_config = normalize_listener_config(campaign.listener_config)
    else:
        campaign.listener_config = normalize_listener_config(build_default_listener_config(campaign))
    if campaign.listener_status not in {"running", "stopped"}:
        campaign.listener_status = "stopped"
    if campaign.approved_response_count is None:
        campaign.approved_response_count = 0


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
    if refresh and campaign.listener_status == "running":
        if not db.scalar(select(IntentSignal.id).where(IntentSignal.campaign_id == campaign.id).limit(1)):
            seed_listener_history(db, campaign)
        maybe_generate_fresh_signals(db, campaign)
        db.commit()

    today_start = datetime.combine(utcnow().date(), datetime.min.time(), tzinfo=timezone.utc)
    signals_today = db.scalars(
        select(IntentSignal).where(IntentSignal.campaign_id == campaign.id, IntentSignal.created_at >= today_start)
    ).all()
    pending_responses = db.scalars(
        select(AgentResponse).where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.review_status == "pending",
        )
    ).all()
    responses_today = db.scalars(
        select(AgentResponse).where(
            AgentResponse.campaign_id == campaign.id,
            AgentResponse.created_at >= today_start,
        )
    ).all()
    compute_spent_today = round(
        sum(signal.scoring_cost for signal in signals_today)
        + sum(response.generation_cost for response in responses_today),
        2,
    )
    active_surfaces = [
        surface for surface in campaign.listener_config.get("surfaces", []) if surface.get("enabled", True)
    ]
    return {
        "campaign_id": campaign.id,
        "status": campaign.listener_status,
        "surfaces_active": len(active_surfaces),
        "signals_detected_today": len(signals_today),
        "responses_pending_review": len(pending_responses),
        "compute_spent_today": compute_spent_today,
        "approved_response_count": campaign.approved_response_count,
        "last_polled_at": campaign.listener_last_polled_at.isoformat() if campaign.listener_last_polled_at else None,
        "brand_voice_profile": campaign.brand_voice_profile,
        "config": campaign.listener_config,
    }


def start_listener(db: Session, campaign: Campaign) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    campaign.listener_status = "running"
    campaign.listener_started_at = campaign.listener_started_at or utcnow()
    if not db.scalar(select(IntentSignal.id).where(IntentSignal.campaign_id == campaign.id).limit(1)):
        seed_listener_history(db, campaign)
    maybe_generate_fresh_signals(db, campaign, force=True)
    db.commit()
    db.refresh(campaign)
    return build_listener_status(db, campaign, refresh=False)


def stop_listener(db: Session, campaign: Campaign) -> dict[str, Any]:
    ensure_listener_defaults(campaign)
    campaign.listener_status = "stopped"
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
    incoming_config = payload.get("config")
    if incoming_profile is not None:
        campaign.brand_voice_profile = normalize_brand_voice(incoming_profile, campaign)
    if incoming_config is not None:
        campaign.listener_config = normalize_listener_config(incoming_config)
    db.commit()
    db.refresh(campaign)
    return build_listener_status(db, campaign, refresh=False)


def review_queue(db: Session, campaign: Campaign) -> list[dict[str, Any]]:
    ensure_listener_defaults(campaign)
    if campaign.listener_status == "running":
        maybe_generate_fresh_signals(db, campaign)
        db.commit()
        db.refresh(campaign)
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
    if campaign.listener_status == "running":
        maybe_generate_fresh_signals(db, campaign)
        db.commit()
        db.refresh(campaign)

    period_map = {"7d": 7, "30d": 30, "90d": 90}
    days = period_map.get(period, 120)
    start_at = utcnow() - timedelta(days=days - 1)

    signals = db.scalars(
        select(IntentSignal)
        .where(IntentSignal.campaign_id == campaign.id, IntentSignal.created_at >= start_at)
        .options(joinedload(IntentSignal.product))
        .order_by(IntentSignal.created_at.asc())
    ).all()
    responses = db.scalars(
        select(AgentResponse)
        .where(AgentResponse.campaign_id == campaign.id, AgentResponse.created_at >= start_at)
        .options(joinedload(AgentResponse.product), joinedload(AgentResponse.signal))
        .order_by(AgentResponse.created_at.asc())
    ).all()
    clicks = db.scalars(
        select(Click)
        .where(
            Click.campaign_id == campaign.id,
            Click.source == "intent_listener",
            Click.created_at >= start_at,
        )
        .options(joinedload(Click.product), joinedload(Click.response))
    ).all()
    conversions = db.scalars(
        select(Conversion)
        .join(Click, Conversion.click_id == Click.id, isouter=True)
        .where(
            Conversion.campaign_id == campaign.id,
            Conversion.channel == "intent_listener",
            Conversion.created_at >= start_at,
        )
        .options(joinedload(Conversion.product))
    ).all()

    responses_sent = [response for response in responses if response.posted]
    reviewed = [response for response in responses if response.review_status != "pending"]
    approved = [response for response in responses if response.review_status in {"approved", "auto_approved"}]
    revenue = round(sum(conversion.order_value for conversion in conversions), 2)
    compute_cost = round(
        sum(signal.scoring_cost for signal in signals)
        + sum(response.generation_cost for response in responses),
        2,
    )
    roc = round(revenue / compute_cost, 2) if compute_cost else 0.0

    surface_stats: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {
            "surface": "",
            "signals_detected": 0,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "roc": 0.0,
        }
    )
    subreddit_counter: Counter[str] = Counter()
    product_stats: dict[str, dict[str, float | int | str | None]] = defaultdict(
        lambda: {
            "product_id": None,
            "product_name": None,
            "surface": None,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
            "roc": 0.0,
        }
    )

    response_lookup = {response.id: response for response in responses}

    for signal in signals:
        stats = surface_stats[signal.surface]
        stats["surface"] = signal.surface
        stats["signals_detected"] += 1
        stats["compute_cost"] += signal.scoring_cost
        if signal.subreddit_or_channel:
            subreddit_counter[signal.subreddit_or_channel] += 1

    for response in responses_sent:
        stats = surface_stats[response.surface]
        stats["surface"] = response.surface
        stats["responses_sent"] += 1
        stats["compute_cost"] += response.generation_cost
        if response.product_id:
            product_row = product_stats[response.product_id]
            product_row["product_id"] = response.product_id
            product_row["product_name"] = response.product.name if response.product else "Product"
            product_row["surface"] = response.surface
            product_row["responses_sent"] += 1
            product_row["compute_cost"] += response.generation_cost

    for click in clicks:
        surface = click.surface or "reddit"
        surface_stats[surface]["surface"] = surface
        surface_stats[surface]["clicks"] += 1
        if click.response_id and click.response_id in response_lookup and click.product_id:
            product_row = product_stats[click.product_id]
            product_row["product_id"] = click.product_id
            product_row["product_name"] = click.product.name if click.product else "Product"
            product_row["surface"] = surface
            product_row["clicks"] += 1

    for conversion in conversions:
        click = next((click for click in clicks if click.id == conversion.click_id), None)
        surface = click.surface if click and click.surface else "reddit"
        surface_stats[surface]["surface"] = surface
        surface_stats[surface]["conversions"] += 1
        surface_stats[surface]["revenue"] += conversion.order_value
        product_row = product_stats[conversion.product_id]
        product_row["product_id"] = conversion.product_id
        product_row["product_name"] = conversion.product.name if conversion.product else "Product"
        product_row["surface"] = surface
        product_row["conversions"] += 1
        product_row["revenue"] += conversion.order_value

    for stats in surface_stats.values():
        stats["revenue"] = round(float(stats["revenue"]), 2)
        stats["compute_cost"] = round(float(stats["compute_cost"]), 2)
        stats["roc"] = (
            round(float(stats["revenue"]) / float(stats["compute_cost"]), 2)
            if float(stats["compute_cost"])
            else 0.0
        )

    for row in product_stats.values():
        row["revenue"] = round(float(row["revenue"]), 2)
        row["compute_cost"] = round(float(row["compute_cost"]), 2)
        row["roc"] = round(float(row["revenue"]) / float(row["compute_cost"]), 2) if float(row["compute_cost"]) else 0.0

    score_buckets = {
        "0-24": 0,
        "25-49": 0,
        "50-69": 0,
        "70-84": 0,
        "85-100": 0,
    }
    for signal in signals:
        score = signal.composite_score
        if score < 25:
            score_buckets["0-24"] += 1
        elif score < 50:
            score_buckets["25-49"] += 1
        elif score < 70:
            score_buckets["50-69"] += 1
        elif score < 85:
            score_buckets["70-84"] += 1
        else:
            score_buckets["85-100"] += 1

    daily_map: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {
            "date": "",
            "signals_detected": 0,
            "responses_sent": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": 0.0,
            "compute_cost": 0.0,
        }
    )
    for signal in signals:
        key = ensure_utc(signal.created_at).date().isoformat()
        daily_map[key]["date"] = key
        daily_map[key]["signals_detected"] += 1
        daily_map[key]["compute_cost"] += signal.scoring_cost
    for response in responses:
        key = ensure_utc(response.created_at).date().isoformat()
        daily_map[key]["date"] = key
        if response.posted:
            daily_map[key]["responses_sent"] += 1
        daily_map[key]["compute_cost"] += response.generation_cost
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

    return {
        "period": period,
        "signals_detected": len(signals),
        "responses_sent": len(responses_sent),
        "responses_pending_review": sum(1 for response in responses if response.review_status == "pending"),
        "approval_rate": round(len(approved) / len(reviewed), 4) if reviewed else 0.0,
        "response_rate": round(len(responses_sent) / len(signals), 4) if signals else 0.0,
        "clicks": len(clicks),
        "click_through_rate": round(len(clicks) / len(responses_sent), 4) if responses_sent else 0.0,
        "conversions": len(conversions),
        "conversion_rate": round(len(conversions) / len(clicks), 4) if clicks else 0.0,
        "revenue": revenue,
        "compute_cost": compute_cost,
        "return_on_compute": roc,
        "top_surfaces": sorted(surface_stats.values(), key=lambda item: (item["revenue"], item["signals_detected"]), reverse=True)[:4],
        "top_products": sorted(product_stats.values(), key=lambda item: (item["revenue"], item["responses_sent"]), reverse=True)[:5],
        "top_subreddits": [
            {"label": label, "count": count}
            for label, count in subreddit_counter.most_common(5)
        ],
        "intent_score_distribution": [
            {"label": label, "count": count} for label, count in score_buckets.items()
        ],
        "daily": daily,
    }
