from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.model_competition import enabled_competition_lanes, lane_label


RUNNING = True
DISCOVERY_REFRESH_SECONDS = 180
LIVE_PROPOSAL_INTERVAL_SECONDS = 20
FALLBACK_PROPOSAL_INTERVAL_SECONDS = 10
SEARCH_RESULT_LIMIT = 6


DEMO_TEMPLATES: list[dict[str, str]] = [
    {
        "category": "research",
        "surface": "reddit",
        "description": "Reviewed a fresh Reddit conversation about chafing during long runs.",
        "content": "What underwear doesn't chafe on long runs?",
        "author": "u/runner_jane",
        "audience": "distance runners",
    },
    {
        "category": "engagement",
        "surface": "forum",
        "description": "Answered a premium-basics question in a women's training forum.",
        "content": "Looking for premium workout underwear that still feels good all day.",
        "author": "forum:movementclub",
        "audience": "women buying premium active basics",
    },
    {
        "category": "outreach",
        "surface": "email",
        "description": "Sent a personalized note to a creator with strong audience fit.",
        "content": "Personalized creator outreach",
        "author": "coach@example.com",
        "audience": "fitness creator audiences",
    },
    {
        "category": "content_creation",
        "surface": "blog",
        "description": "Drafted a content angle around staying comfortable through movement.",
        "content": "How to choose underwear for high-movement training",
        "author": "ever-bot",
        "audience": "search-driven prospects",
    },
    {
        "category": "engagement",
        "surface": "twitter",
        "description": "Joined an active thread about breathable workout underwear.",
        "content": "best athletic thong for hot yoga and walking all day?",
        "author": "@studio_notes",
        "audience": "people comparing workout underwear",
    },
]

INTENT_PHRASES = [
    "looking for",
    "recommend",
    "recommendation",
    "anyone have",
    "any recs",
    "need help",
    "need a",
    "best",
    "what should i buy",
    "worth it",
    "does anyone know",
    "struggling to find",
]

DEFAULT_REDDIT_SUBREDDITS = [
    "running",
    "XXrunning",
    "cycling",
    "crossfit",
    "femalefashionadvice",
    "ABraThatFits",
    "yoga",
    "pilates",
    "BuyItForLife",
]

CREATOR_HINTS = [
    "newsletter",
    "creator",
    "coach",
    "influencer",
    "podcast",
    "studio",
    "founder",
    "editor",
]

COMMUNITY_HINTS = [
    "forum",
    "community",
    "discussion",
    "thread",
    "subreddit",
    "discord",
]

CONTENT_HINTS = [
    "guide",
    "best",
    "how to",
    "review",
    "tips",
    "blog",
]


def stop_agent(*_: object) -> None:
    global RUNNING
    RUNNING = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clamp_score(value: float, lower: int = 0, upper: int = 99) -> int:
    return max(lower, min(int(round(value)), upper))


def compact_text(value: str, limit: int = 360) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def runtime_state_path(args: argparse.Namespace) -> Path | None:
    if args.config_path:
        return Path(args.config_path).with_name("agent-state.json")
    return None


def load_runtime_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"seen_source_urls": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen_source_urls": []}
    return {"seen_source_urls": payload.get("seen_source_urls", [])}


def persist_runtime_state(path: Path | None, state: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "seen_source_urls": state.get("seen_source_urls", [])[:400],
                "saved_at": now_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def remember_source_url(path: Path | None, state: dict[str, Any], source_url: str | None) -> None:
    if not source_url:
        return
    existing = [item for item in state.get("seen_source_urls", []) if item != source_url]
    state["seen_source_urls"] = [source_url, *existing][:400]
    persist_runtime_state(path, state)


def clean_domain(url: str | None) -> str:
    if not url:
        return ""
    domain = urlparse(url).netloc.lower()
    return domain.removeprefix("www.")


def normalize_result_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    if url.startswith("//"):
        return f"https:{url}"
    return url


def search_headers() -> dict[str, str]:
    return {
        "User-Agent": settings.reddit_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def source_url(surface: str, seed: str) -> str | None:
    if surface == "reddit":
        return f"https://reddit.com/r/running/comments/{seed[:10]}"
    if surface == "twitter":
        return f"https://x.com/everagent/status/{seed[:12]}"
    if surface == "forum":
        return f"https://forum.ever.local/thread/{seed[:10]}"
    if surface == "blog":
        return f"https://ever.local/drafts/{seed[:10]}"
    return None


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens / 1000 * 0.003) + (output_tokens / 1000 * 0.015), 4)


def product_fit_score(product: dict[str, Any], text: str) -> int:
    fit_score = 0
    text_lower = text.lower()
    category = (product.get("category") or "").replace("_", " ").lower()
    if category and category in text_lower:
        fit_score += 8
    attributes = product.get("attributes", {}) or {}
    subcategory = str(attributes.get("subcategory") or "").replace("_", " ").lower()
    if subcategory and subcategory in text_lower:
        fit_score += 10
    for point in product.get("key_selling_points", []):
        for token in point.lower().replace("-", " ").split():
            if len(token) >= 5 and token in text_lower:
                fit_score += 4
                break
    for activity in product.get("activities", []):
        if activity.lower() in text_lower:
            fit_score += 8
    for token in product.get("name", "").lower().replace("-", " ").split():
        if len(token) >= 4 and token in text_lower:
            fit_score += 4
    if "chaf" in text_lower and "high movement" in product.get("name", "").lower():
        fit_score += 16
    if "organic cotton" in text_lower and "organic" in json.dumps(attributes).lower():
        fit_score += 10
    if "recovery" in text_lower and "recovery" in product.get("name", "").lower():
        fit_score += 10
    return fit_score


def choose_product(products: list[dict[str, Any]], template: dict[str, str]) -> dict[str, Any]:
    explicit_product_id = template.get("product_id")
    if explicit_product_id:
        match = next((product for product in products if product.get("id") == explicit_product_id), None)
        if match is not None:
            return match
    text = f"{template['content']} {template['description']}".lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for product in products:
        scored.append((product_fit_score(product, text), product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else products[0]


def build_response_text(
    config: dict[str, Any],
    product: dict[str, Any],
    template: dict[str, Any] | None = None,
) -> str:
    disclosure = config["brand"]["disclosure"]
    context = config.get("context", {})
    selling_points = product.get("key_selling_points", [])[:2]
    selling_line = ", ".join(selling_points) if selling_points else product["name"]
    key_message = next((item for item in context.get("key_messages", []) if item), "")
    proof_point = next((item for item in context.get("proof_points", []) if item), "")
    opportunity_text = (
        f"{template.get('content', '')} {template.get('description', '')}".lower() if template else ""
    )
    if "chaf" in opportunity_text or "long run" in opportunity_text:
        opener = (
            "For long runs, the biggest thing is something that stays put and dries quickly "
            "instead of adding bulk."
        )
    elif "yoga" in opportunity_text or "pilates" in opportunity_text:
        opener = "For yoga and pilates, softer low-profile fabric usually wins over compression."
    elif "sleep" in opportunity_text or "recovery" in opportunity_text or "lounge" in opportunity_text:
        opener = "For recovery days, comfort-first natural fabric is usually the right place to start."
    else:
        opener = key_message or "Lead with the product fit and usefulness before pushing the sale."
    proof_line = f" One useful proof point: {proof_point}." if proof_point else ""
    return (
        f"{opener} {product['name']} stands out because of {selling_line}.{proof_line} {disclosure}"
    )


def build_referral_url(product: dict[str, Any], campaign_id: str, surface: str) -> str:
    return f"{product['referral_base']}?src={quote(surface)}&cid={quote(campaign_id)}"


def map_action_type(template: dict[str, str]) -> str:
    explicit_action = template.get("action_type")
    if explicit_action:
        return explicit_action
    if template["surface"] == "email":
        return "email"
    if template["category"] == "outreach":
        return "outreach"
    if template["category"] == "content_creation":
        return "content"
    return "reply"


def build_subject_line(product: dict[str, Any], template: dict[str, Any]) -> str:
    if map_action_type(template) == "email":
        return f"Bia fit for your audience: {product['name']}"
    if map_action_type(template) == "content":
        return f"Content angle: {product['name']} for high-fit shoppers"
    return product["name"]


def build_content_brief(config: dict[str, Any], product: dict[str, Any], template: dict[str, Any]) -> str:
    disclosure = config["brand"]["disclosure"]
    fallback_headline = f"Why {product['name']} fits this moment"
    content_title = f"Working title: {template.get('headline') or fallback_headline}"
    audience = template.get("audience", "people already searching for a better-fit product")
    hook = (
        f"Opening hook: People in {audience} are already asking for a better solution. Start with the problem, "
        f"then explain why {product['name']} fits."
    )
    proof_points = ", ".join(product.get("key_selling_points", [])[:2]) or product["name"]
    body = (
        f"Draft: Lead with the pain point from the source, explain the fit with {proof_points}, "
        f"and close with a tracked product recommendation."
    )
    cta = f"CTA: Recommend {product['name']} with the tracked link and keep the disclosure visible. {disclosure}"
    return "\n".join([content_title, "", hook, body, cta])


def build_outreach_message(config: dict[str, Any], product: dict[str, Any], template: dict[str, Any]) -> str:
    disclosure = config["brand"]["disclosure"]
    target = template.get("author") or template.get("audience") or "there"
    proof_point = next((item for item in config.get("context", {}).get("proof_points", []) if item), "")
    opener = f"Subject: {build_subject_line(product, template)}"
    body = (
        f"Hi {target},\n\n"
        f"I'm reaching out because your audience is already discussing the exact problem {product['name']} solves. "
        f"Bia has a strong-fit product here, especially for shoppers who care about {', '.join(product.get('activities', [])[:2]) or 'fit and comfort'}."
    )
    if proof_point:
        body += f" One useful proof point is {proof_point}."
    body += (
        f"\n\nIf helpful, I can share a tracked link and a short product summary you can pass along."
        f"\n\n{disclosure}"
    )
    return opener + "\n\n" + body


def build_proposed_response(config: dict[str, Any], product: dict[str, Any], template: dict[str, Any]) -> str:
    action_type = map_action_type(template)
    if action_type in {"email", "outreach"}:
        return build_outreach_message(config, product, template)
    if action_type == "content":
        return build_content_brief(config, product, template)
    return build_response_text(config, product, template)


def build_rationale(template: dict[str, str], product: dict[str, Any]) -> str:
    source_hint = f" on {template['surface']}" if template.get("surface") else ""
    expected_efficiency = template.get("expected_return_score")
    efficiency_line = (
        f" It ranks highly on expected return on compute ({expected_efficiency}/100)."
        if expected_efficiency is not None
        else ""
    )
    return (
        f"This looks like a strong fit because the person is explicitly asking for help and "
        f"{product['name']} matches the use case{source_hint}.{efficiency_line}"
    )


def build_execution_instructions(template: dict[str, str], source_link: str | None, response_text: str) -> str:
    action_type = map_action_type(template)
    target = source_link or "the source conversation"
    if action_type in {"email", "outreach"}:
        return (
            f"Step 1: Open {target}. "
            f"Step 2: Find the best contact path for the creator, editor, or operator. "
            f"Step 3: Copy the drafted outreach message and personalize the first line if needed. "
            f"Step 4: Include the tracked link once the context makes sense. "
            f"Step 5: Send it manually and record whether you got a response."
        )
    if action_type == "content":
        return (
            f"Step 1: Open {target} and review the content gap or ranking page. "
            f"Step 2: Use the draft below as the opening structure for a post, note, or landing-page update. "
            f"Step 3: Add the tracked product link where the recommendation naturally fits. "
            f"Step 4: Publish manually in your CMS or social tool. "
            f"Step 5: Record the publication URL and any early engagement notes."
        )
    return (
        f"Step 1: Open {target}. "
        f"Step 2: Start a {map_action_type(template)}. "
        f"Step 3: Paste the proposed response below exactly. "
        f"Step 4: Include the tracked referral link if the surface allows it. "
        f"Step 5: Send or publish manually."
    )


def post_event(
    client: httpx.Client,
    events_endpoint: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        events_endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_config(client: httpx.Client, config_endpoint: str, api_key: str) -> dict[str, Any]:
    response = client.get(
        config_endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def load_runtime_credentials(args: argparse.Namespace) -> tuple[str, str]:
    if args.config_path:
        payload = json.loads(Path(args.config_path).read_text(encoding="utf-8"))
        if "ever_api" in payload:
            return payload["ever_api"]["config_endpoint"], payload["ever_api"]["api_key"]
        return payload["config_endpoint"], payload["api_key"]
    if args.campaign_id and args.api_base and args.api_key:
        return f"{args.api_base}/api/campaigns/{args.campaign_id}/agent-config", args.api_key
    raise ValueError("Missing OpenClaw runtime credentials")


def model_available() -> bool:
    return bool(settings.anthropic_api_key)


def clean_json_text(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def call_anthropic_json(
    client: httpx.Client,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1800,
) -> tuple[Any, dict[str, int]] | None:
    if not model_available():
        return None
    response = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    text_blocks = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ]
    raw_text = clean_json_text("\n".join(text_blocks))
    parsed = json.loads(raw_text)
    usage = payload.get("usage", {}) or {}
    return parsed, {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
    }


def openai_available() -> bool:
    return bool(settings.openai_api_key)


def extract_openai_output_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    text_chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                text_chunks.append(str(content["text"]))
    return "\n".join(text_chunks)


def call_openai_json(
    client: httpx.Client,
    *,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int = 1800,
) -> tuple[Any, dict[str, int]] | None:
    if not openai_available():
        return None
    response = client.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key or ''}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_model,
            "reasoning": {"effort": "low"},
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            "max_output_tokens": max_output_tokens,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw_text = clean_json_text(extract_openai_output_text(payload))
    parsed = json.loads(raw_text)
    usage = payload.get("usage", {}) or {}
    return parsed, {
        "input_tokens": int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0),
    }


def build_model_context(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": config.get("objective", {}),
        "brand": config.get("brand", {}),
        "budget": config.get("budget", {}),
        "memory": config.get("memory", {}),
        "products": [
            {
                "id": product.get("id"),
                "name": product.get("name"),
                "category": product.get("category"),
                "description": product.get("description"),
                "activities": product.get("activities", []),
                "key_selling_points": product.get("key_selling_points", []),
            }
            for product in config.get("products", [])
        ],
    }


def generate_query_plan_with_model(client: httpx.Client, config: dict[str, Any]) -> tuple[list[dict[str, str]], float]:
    fallback = build_objective_query_plan(config)
    if not model_available():
        return fallback, 0.0

    system_prompt = (
        "You are planning internet discovery for an objective-first commerce agent. "
        "Do not choose tactics yet. Your job is to decide what the agent should search for on the live internet "
        "to maximize attributed sales relative to compute cost."
    )
    user_prompt = (
        "Given the objective, products, and memory below, return JSON only as an array of 8-10 search tasks.\n"
        "Each item must contain: query, family, reason.\n"
        "family should be one of buyer_intent, creator_outreach, content_gap, partnership, or community.\n"
        "Diversify the search plan. Avoid fixed-channel bias. Focus on opportunities likely to produce sales more efficiently than compute cost.\n\n"
        f"{json.dumps(build_model_context(config), indent=2)}"
    )
    try:
        result = call_anthropic_json(
            client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1400,
        )
    except Exception:
        return fallback, 0.0
    if result is None:
        return fallback, 0.0
    parsed, usage = result
    plan: list[dict[str, str]] = []
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            query = str(item.get("query", "")).strip()
            family = str(item.get("family", "buyer_intent")).strip() or "buyer_intent"
            reason = str(item.get("reason", "")).strip()
            if not query:
                continue
            plan.append({"query": query, "family": family, "reason": reason})
    if not plan:
        return fallback, 0.0
    return plan[:10], compute_cost(usage["input_tokens"], usage["output_tokens"])


def generate_query_plan_with_openai(
    client: httpx.Client,
    config: dict[str, Any],
) -> tuple[list[dict[str, str]], float]:
    fallback = build_objective_query_plan(config)
    if not openai_available():
        return fallback, 0.0

    system_prompt = (
        "You are planning internet discovery for an objective-first commerce agent. "
        "Do not choose tactics yet. Decide what the agent should search for on the live internet "
        "to maximize attributed sales relative to compute cost. Return JSON only."
    )
    user_prompt = (
        "Return an array of 8-10 search tasks. "
        "Each item must contain query, family, and reason. "
        "family must be one of buyer_intent, creator_outreach, content_gap, partnership, or community. "
        "Diversify the search plan and avoid fixed-channel bias.\n\n"
        f"{json.dumps(build_model_context(config), indent=2)}"
    )
    try:
        result = call_openai_json(
            client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=1400,
        )
    except Exception:
        return fallback, 0.0
    if result is None:
        return fallback, 0.0
    parsed, usage = result
    plan: list[dict[str, str]] = []
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            query = str(item.get("query", "")).strip()
            family = str(item.get("family", "buyer_intent")).strip() or "buyer_intent"
            reason = str(item.get("reason", "")).strip()
            if query:
                plan.append({"query": query, "family": family, "reason": reason})
    if not plan:
        return fallback, 0.0
    return plan[:10], compute_cost(usage["input_tokens"], usage["output_tokens"])


def search_reddit_posts(
    client: httpx.Client,
    query: str,
    *,
    keywords: list[str],
    products: list[dict[str, Any]],
    now_ts: float,
    batch_seen: set[str],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    response = client.get(
        "https://www.reddit.com/search.json",
        params={
            "q": query,
            "sort": "new",
            "limit": 5,
            "raw_json": 1,
            "t": "month",
        },
        headers=reddit_headers(),
        timeout=20.0,
    )
    response.raise_for_status()

    for child in response.json().get("data", {}).get("children", []):
        data = child.get("data", {})
        permalink = data.get("permalink")
        if not permalink:
            continue
        source_link = f"https://www.reddit.com{permalink}"
        if source_link in batch_seen:
            continue
        if data.get("over_18") or data.get("stickied") or data.get("locked"):
            continue
        title = str(data.get("title") or "").strip()
        selftext = str(data.get("selftext") or "").strip()
        combined = compact_text(f"{title} {selftext}".strip(), 420)
        if not combined:
            continue
        keyword_hits = sum(1 for keyword in keywords if keyword and keyword in combined.lower())
        product = choose_product(products, {"content": combined, "description": title or combined})
        fit_score = product_fit_score(product, combined)
        age_minutes = max(int((now_ts - float(data.get("created_utc") or now_ts)) // 60), 0)
        intent_score = compute_intent_scores(
            combined,
            fit_score=fit_score,
            keyword_hits=keyword_hits,
            age_minutes=age_minutes,
            num_comments=int(data.get("num_comments") or 0),
        )
        observations.append(
            {
                "source_url": source_link,
                "surface": "reddit",
                "domain": "reddit.com",
                "title": title or combined,
                "snippet": selftext[:220] if selftext else title,
                "query": query,
                "family": "buyer_intent",
                "source_author": f"u/{data.get('author')}" if data.get("author") else None,
                "source_context": f"Thread in r/{data.get('subreddit')}" if data.get("subreddit") else None,
                "candidate_product_id": product.get("id"),
                "fit_score": fit_score,
                "keyword_hits": keyword_hits,
                "intent_score": intent_score,
            }
        )
        batch_seen.add(source_link)
    return observations


def collect_live_observations(
    client: httpx.Client,
    config: dict[str, Any],
    query_plan: list[dict[str, str]],
    seen_source_urls: set[str],
) -> list[dict[str, Any]]:
    products = config.get("products", [])
    if not products:
        return []
    keywords = build_keyword_watchlist(config)
    now_ts = datetime.now(timezone.utc).timestamp()
    observations: list[dict[str, Any]] = []
    batch_seen = set(seen_source_urls)

    for plan_item in query_plan[:10]:
        query = plan_item["query"]
        family = plan_item.get("family", "buyer_intent")
        try:
            html = search_html(client, query)
        except Exception:
            html = ""
        if html:
            for result in parse_search_results(html):
                source_link = result["url"]
                if source_link in batch_seen:
                    continue
                surface = classify_surface(source_link, family, result["title"], result["snippet"])
                combined = f"{result['title']} {result['snippet']} {query}"
                keyword_hits = sum(1 for keyword in keywords if keyword and keyword in combined.lower())
                product = choose_product(products, {"content": combined, "description": result["title"]})
                fit_score = product_fit_score(product, combined)
                if fit_score < 5 and keyword_hits == 0:
                    continue
                observations.append(
                    {
                        "source_url": source_link,
                        "surface": surface,
                        "domain": clean_domain(source_link),
                        "title": result["title"],
                        "snippet": result["snippet"],
                        "query": query,
                        "family": family,
                        "source_author": clean_domain(source_link),
                        "source_context": f"Search result for '{query}'",
                        "candidate_product_id": product.get("id"),
                        "fit_score": fit_score,
                        "keyword_hits": keyword_hits,
                    }
                )
                batch_seen.add(source_link)
        if family in {"buyer_intent", "community"}:
            try:
                observations.extend(
                    search_reddit_posts(
                        client,
                        query,
                        keywords=keywords,
                        products=products,
                        now_ts=now_ts,
                        batch_seen=batch_seen,
                    )
                )
            except Exception:
                continue

    observations.sort(
        key=lambda item: (
            item.get("fit_score", 0),
            item.get("keyword_hits", 0),
        ),
        reverse=True,
    )
    return observations[:28]


def plan_opportunities_with_model(
    client: httpx.Client,
    config: dict[str, Any],
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    if not model_available() or not observations:
        return [], 0.0

    compact_observations = [
        {
            "source_url": observation.get("source_url"),
            "surface": observation.get("surface"),
            "title": observation.get("title"),
            "snippet": observation.get("snippet"),
            "query": observation.get("query"),
            "family": observation.get("family"),
            "candidate_product_id": observation.get("candidate_product_id"),
            "fit_score": observation.get("fit_score"),
            "source_author": observation.get("source_author"),
            "source_context": observation.get("source_context"),
        }
        for observation in observations[:24]
    ]
    system_prompt = (
        "You are the planner for an objective-first commerce agent. "
        "You optimize for attributed sales being greater than compute cost. "
        "You are not channel-first. Choose the best tactics from the internet observations you see. "
        "All actions are propose-only and manually executed by a human."
    )
    user_prompt = (
        "Use the objective, memory, and live internet observations below.\n"
        "Return JSON only as an array of up to 6 proposals.\n"
        "Each proposal must contain: source_url, surface, action_type, product_id, description, source_content, "
        "source_context, source_author, target_audience, rationale, proposed_response, execution_instructions, "
        "expected_return_score, and intent_score with relevance, intent, fit, receptivity, composite.\n"
        "Choose the actions most likely to keep sales above compute cost. "
        "Allowed action types: reply, email, outreach, content, other.\n"
        "Only use product IDs that appear in the context.\n\n"
        f"{json.dumps({'context': build_model_context(config), 'observations': compact_observations}, indent=2)}"
    )
    try:
        result = call_anthropic_json(
            client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2200,
        )
    except Exception:
        return [], 0.0
    if result is None:
        return [], 0.0
    parsed, usage = result
    proposals: list[dict[str, Any]] = []
    valid_product_ids = {str(product.get("id")) for product in config.get("products", [])}
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("product_id", "")).strip()
            source_url = str(item.get("source_url", "")).strip()
            if not source_url or product_id not in valid_product_ids:
                continue
            intent_score = item.get("intent_score", {}) if isinstance(item.get("intent_score"), dict) else {}
            proposals.append(
                {
                    "category": category_for_action(str(item.get("action_type", "other"))),
                    "surface": str(item.get("surface", "internet")).strip() or "internet",
                    "action_type": str(item.get("action_type", "other")).strip() or "other",
                    "description": str(item.get("description", "Model-selected opportunity")).strip()
                    or "Model-selected opportunity",
                    "content": compact_text(str(item.get("source_content", "")).strip(), 420),
                    "author": str(item.get("source_author", "")).strip() or clean_domain(source_url) or "internet",
                    "audience": str(item.get("target_audience", "")).strip()
                    or "People with high-fit purchase intent",
                    "source_url": source_url,
                    "source_context": str(item.get("source_context", "")).strip() or None,
                    "intent_score": {
                        "relevance": clamp_score(float(intent_score.get("relevance", 0) or 0)),
                        "intent": clamp_score(float(intent_score.get("intent", 0) or 0)),
                        "fit": clamp_score(float(intent_score.get("fit", 0) or 0)),
                        "receptivity": clamp_score(float(intent_score.get("receptivity", 0) or 0)),
                        "composite": clamp_score(float(intent_score.get("composite", 0) or 0)),
                    },
                    "product_id": product_id,
                    "proposed_response": str(item.get("proposed_response", "")).strip(),
                    "rationale": str(item.get("rationale", "")).strip(),
                    "execution_instructions": str(item.get("execution_instructions", "")).strip(),
                    "expected_return_score": clamp_score(float(item.get("expected_return_score", 0) or 0), 0, 100),
                }
            )
    proposals = [
        proposal
        for proposal in proposals
        if proposal["proposed_response"] and proposal["execution_instructions"]
    ]
    return proposals[:6], compute_cost(usage["input_tokens"], usage["output_tokens"])


def plan_opportunities_with_openai(
    client: httpx.Client,
    config: dict[str, Any],
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    if not openai_available() or not observations:
        return [], 0.0

    compact_observations = [
        {
            "source_url": observation.get("source_url"),
            "surface": observation.get("surface"),
            "title": observation.get("title"),
            "snippet": observation.get("snippet"),
            "query": observation.get("query"),
            "family": observation.get("family"),
            "candidate_product_id": observation.get("candidate_product_id"),
            "fit_score": observation.get("fit_score"),
            "source_author": observation.get("source_author"),
            "source_context": observation.get("source_context"),
        }
        for observation in observations[:24]
    ]
    system_prompt = (
        "You are the planner for an objective-first commerce agent. "
        "Optimize for attributed sales being greater than compute cost. "
        "Choose the highest-efficiency tactics from the internet observations you see. "
        "All actions are propose-only and manually executed by a human. Return JSON only."
    )
    user_prompt = (
        "Return an array of up to 6 proposals. "
        "Each proposal must contain: source_url, surface, action_type, product_id, description, source_content, "
        "source_context, source_author, target_audience, rationale, proposed_response, execution_instructions, "
        "expected_return_score, and intent_score with relevance, intent, fit, receptivity, composite. "
        "Allowed action types: reply, email, outreach, content, other.\n\n"
        f"{json.dumps({'context': build_model_context(config), 'observations': compact_observations}, indent=2)}"
    )
    try:
        result = call_openai_json(
            client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=2200,
        )
    except Exception:
        return [], 0.0
    if result is None:
        return [], 0.0
    parsed, usage = result
    proposals: list[dict[str, Any]] = []
    valid_product_ids = {str(product.get("id")) for product in config.get("products", [])}
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("product_id", "")).strip()
            source_url = str(item.get("source_url", "")).strip()
            if not source_url or product_id not in valid_product_ids:
                continue
            intent_score = item.get("intent_score", {}) if isinstance(item.get("intent_score"), dict) else {}
            proposals.append(
                {
                    "category": category_for_action(str(item.get("action_type", "other"))),
                    "surface": str(item.get("surface", "internet")).strip() or "internet",
                    "action_type": str(item.get("action_type", "other")).strip() or "other",
                    "description": str(item.get("description", "Model-selected opportunity")).strip()
                    or "Model-selected opportunity",
                    "content": compact_text(str(item.get("source_content", "")).strip(), 420),
                    "author": str(item.get("source_author", "")).strip() or clean_domain(source_url) or "internet",
                    "audience": str(item.get("target_audience", "")).strip()
                    or "People with high-fit purchase intent",
                    "source_url": source_url,
                    "source_context": str(item.get("source_context", "")).strip() or None,
                    "intent_score": {
                        "relevance": clamp_score(float(intent_score.get("relevance", 0) or 0)),
                        "intent": clamp_score(float(intent_score.get("intent", 0) or 0)),
                        "fit": clamp_score(float(intent_score.get("fit", 0) or 0)),
                        "receptivity": clamp_score(float(intent_score.get("receptivity", 0) or 0)),
                        "composite": clamp_score(float(intent_score.get("composite", 0) or 0)),
                    },
                    "product_id": product_id,
                    "proposed_response": str(item.get("proposed_response", "")).strip(),
                    "rationale": str(item.get("rationale", "")).strip(),
                    "execution_instructions": str(item.get("execution_instructions", "")).strip(),
                    "expected_return_score": clamp_score(float(item.get("expected_return_score", 0) or 0), 0, 100),
                }
            )
    proposals = [
        proposal
        for proposal in proposals
        if proposal["proposed_response"] and proposal["execution_instructions"]
    ]
    return proposals[:6], compute_cost(usage["input_tokens"], usage["output_tokens"])


def build_discovery_queries(config: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    products = config.get("products", [])
    for product in products:
        category = (product.get("category") or "").replace("_", " ").lower()
        attributes = product.get("attributes", {}) or {}
        subcategory = str(attributes.get("subcategory") or "").replace("_", " ").lower()
        activities = [str(activity).lower() for activity in product.get("activities", [])[:4]]
        product_name = product.get("name", "").lower()
        recovery_focused = any(
            activity in {"sleep", "lounge", "recovery"} for activity in activities
        ) or "recovery" in product_name
        underwear_focused = (
            "underwear" in category
            or subcategory in {"thong", "brief", "boyshort"}
            or "thong" in product_name
        )

        if underwear_focused:
            queries.extend(
                [
                    "running underwear chafing",
                    "workout underwear recommendation",
                    "best athletic thong",
                    "underwear that stays put running",
                    "breathable workout underwear women",
                ]
            )
        if recovery_focused:
            queries.extend(
                [
                    "organic cotton sleep shirt recommendation",
                    "recovery loungewear women",
                    "best recovery shorts women",
                    "comfortable sleep tee women organic cotton",
                ]
            )
        noun = subcategory or category or "underwear"
        for activity in activities:
            activity_label = activity.replace("_", " ")
            queries.append(f"{activity_label} {noun} recommendation")
            queries.append(f"best {activity_label} {noun}")

    proof_points = [point.lower() for point in config.get("context", {}).get("proof_points", [])]
    if any("canada" in point for point in proof_points):
        queries.append("made in Canada workout underwear")
    if any("organic" in point for point in proof_points):
        queries.append("organic cotton sleepwear women")

    if not queries:
        queries.extend(
            [
                "workout underwear recommendation",
                "running underwear chafing",
                "recovery loungewear women",
            ]
        )

    return unique_strings(queries)[:14]


def build_keyword_watchlist(config: dict[str, Any]) -> list[str]:
    keywords = [
        "underwear",
        "workout underwear",
        "athletic thong",
        "chafing",
        "running",
        "yoga",
        "pilates",
        "cycling",
        "crossfit",
        "recovery",
        "loungewear",
        "sleep tee",
        "organic cotton",
    ]
    for product in config.get("products", []):
        keywords.append(product.get("name", ""))
        keywords.append((product.get("category") or "").replace("_", " "))
        keywords.extend(product.get("activities", []))
        keywords.extend(product.get("key_selling_points", []))
        attributes = product.get("attributes", {}) or {}
        keywords.append(str(attributes.get("subcategory") or ""))
        keywords.append(str(attributes.get("material") or ""))
    return [keyword.lower().strip() for keyword in unique_strings(keywords) if keyword.strip()]


def build_subreddit_watchlist(config: dict[str, Any]) -> list[str]:
    activities = {
        str(activity).lower()
        for product in config.get("products", [])
        for activity in product.get("activities", [])
    }
    subreddits: list[str] = ["femalefashionadvice", "ABraThatFits"]
    if activities.intersection({"running", "lifting", "jumping"}):
        subreddits.extend(["running", "XXrunning", "crossfit"])
    if "cycling" in activities:
        subreddits.append("cycling")
    if activities.intersection({"yoga", "pilates", "walking", "low-intensity"}):
        subreddits.extend(["yoga", "pilates"])
    if activities.intersection({"sleep", "lounge", "recovery"}):
        subreddits.extend(["BuyItForLife"])
    subreddits.extend(DEFAULT_REDDIT_SUBREDDITS)
    return unique_strings(subreddits)[:8]


def reddit_headers() -> dict[str, str]:
    return {
        "User-Agent": settings.reddit_user_agent,
        "Accept": "application/json",
    }


def build_objective_query_plan(config: dict[str, Any]) -> list[dict[str, str]]:
    activities = unique_strings(
        [
            str(activity).replace("_", " ")
            for product in config.get("products", [])
            for activity in product.get("activities", [])
        ]
    )
    buyer_queries = build_discovery_queries(config)[:7]
    outreach_queries: list[str] = []
    content_queries: list[str] = []

    for activity in activities[:4]:
        outreach_queries.extend(
            [
                f"best {activity} newsletter women",
                f"{activity} coach newsletter women",
                f"{activity} creator contact women",
            ]
        )
        content_queries.extend(
            [
                f"best {activity} underwear women",
                f"what to wear for {activity} women",
            ]
        )

    products = config.get("products", [])
    if any("recovery" in product.get("name", "").lower() for product in products):
        outreach_queries.append("recovery lifestyle newsletter women")
        content_queries.extend(
            [
                "best recovery loungewear women",
                "organic cotton sleep tee women",
            ]
        )

    if any("thong" in product.get("name", "").lower() for product in products):
        content_queries.extend(
            [
                "best thong for running women",
                "underwear that stays put under leggings",
            ]
        )

    plan: list[dict[str, str]] = []
    plan.extend({"family": "buyer_intent", "query": query} for query in buyer_queries)
    plan.extend({"family": "creator_outreach", "query": query} for query in unique_strings(outreach_queries)[:5])
    plan.extend({"family": "content_gap", "query": query} for query in unique_strings(content_queries)[:5])
    return plan


def classify_surface(url: str, family: str, title: str, snippet: str) -> str:
    domain = clean_domain(url)
    text_blob = f"{domain} {title} {snippet}".lower()
    if "reddit.com" in domain:
        return "reddit"
    if domain in {"x.com", "twitter.com"}:
        return "twitter"
    if any(hint in text_blob for hint in CREATOR_HINTS) or family == "creator_outreach":
        return "creator"
    if any(hint in text_blob for hint in COMMUNITY_HINTS):
        return "forum"
    if "youtube.com" in domain:
        return "youtube"
    if "substack.com" in domain or "beehiiv.com" in domain:
        return "newsletter"
    return "search"


def classify_action_type(surface: str, family: str, title: str, snippet: str) -> str:
    text_blob = f"{surface} {title} {snippet}".lower()
    if surface in {"reddit", "twitter", "forum"}:
        return "reply"
    if surface in {"creator", "newsletter"} or family == "creator_outreach":
        return "email"
    if "partnership" in text_blob:
        return "outreach"
    return "content"


def category_for_action(action_type: str) -> str:
    if action_type in {"email", "outreach"}:
        return "outreach"
    if action_type == "content":
        return "content_creation"
    return "engagement"


def audience_for_surface(surface: str, title: str, snippet: str) -> str:
    text_blob = f"{title} {snippet}".strip()
    if surface == "creator":
        return "Creator or editor with audience overlap"
    if surface == "newsletter":
        return "Newsletter audience aligned with the brand"
    if surface == "youtube":
        return "Viewers researching a product category fit"
    if surface in {"reddit", "forum", "twitter"}:
        return "People actively asking for product help"
    return text_blob[:120] if text_blob else "Search-driven shoppers"


def estimate_expected_return_score(
    *,
    action_type: str,
    family: str,
    intent_score: dict[str, int],
    fit_score: int,
    keyword_hits: int,
) -> int:
    directness = {
        "reply": 24,
        "email": 16,
        "outreach": 18,
        "content": 12,
    }.get(action_type, 10)
    leverage = {
        "reply": 10,
        "email": 17,
        "outreach": 18,
        "content": 16,
    }.get(action_type, 8)
    family_bonus = {
        "buyer_intent": 12,
        "creator_outreach": 6,
        "content_gap": 4,
    }.get(family, 0)
    return clamp_score(
        intent_score["composite"] * 0.58
        + fit_score * 1.2
        + keyword_hits * 2.5
        + directness
        + leverage
        + family_bonus,
        0,
        100,
    )


def search_html(client: httpx.Client, query: str) -> str:
    response = client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers=search_headers(),
        timeout=20.0,
    )
    response.raise_for_status()
    return response.text


def parse_search_results(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    parsed: list[dict[str, str]] = []
    for result in soup.select(".result"):
        anchor = result.select_one(".result__a")
        if anchor is None:
            continue
        url = normalize_result_url(anchor.get("href") or "")
        title = compact_text(anchor.get_text(" ", strip=True), 180)
        snippet = compact_text(
            (result.select_one(".result__snippet") or result.select_one(".result__body")).get_text(" ", strip=True)
            if result.select_one(".result__snippet") or result.select_one(".result__body")
            else "",
            260,
        )
        if not url or not title:
            continue
        parsed.append({"url": url, "title": title, "snippet": snippet})
    return parsed[:SEARCH_RESULT_LIMIT]


def compute_intent_scores(
    text: str,
    fit_score: int,
    keyword_hits: int,
    age_minutes: int,
    num_comments: int,
) -> dict[str, int]:
    text_lower = text.lower()
    relevance = 38 + keyword_hits * 8 + min(fit_score, 20) * 2.1
    if "reddit" in text_lower:
        relevance += 0
    intent = 28
    if "?" in text_lower:
        intent += 12
    for phrase in INTENT_PHRASES:
        if phrase in text_lower:
            intent += 10
    if "recommend" in text_lower or "best" in text_lower:
        intent += 10
    fit = 32 + fit_score * 3
    receptivity = 34
    if 10 <= age_minutes <= 1440:
        receptivity += 18
    elif age_minutes <= 10080:
        receptivity += 10
    if num_comments <= 20:
        receptivity += 12
    elif num_comments >= 80:
        receptivity -= 8
    if age_minutes > 60 * 24 * 14:
        receptivity -= 12
    relevance_score = clamp_score(relevance)
    intent_score = clamp_score(intent)
    fit_value = clamp_score(fit)
    receptivity_score = clamp_score(receptivity)
    composite = clamp_score(
        relevance_score * 0.35
        + intent_score * 0.25
        + fit_value * 0.25
        + receptivity_score * 0.15
    )
    return {
        "relevance": relevance_score,
        "intent": intent_score,
        "fit": fit_value,
        "receptivity": receptivity_score,
        "composite": composite,
    }


def compute_search_result_scores(
    *,
    title: str,
    snippet: str,
    query: str,
    family: str,
    fit_score: int,
    keyword_hits: int,
) -> dict[str, int]:
    combined = f"{title} {snippet} {query}"
    age_minutes = 180 if family == "buyer_intent" else 720
    num_comments = 10 if family == "buyer_intent" else 0
    intent_score = compute_intent_scores(
        combined,
        fit_score=fit_score,
        keyword_hits=keyword_hits,
        age_minutes=age_minutes,
        num_comments=num_comments,
    )
    if family == "creator_outreach":
        intent_score["relevance"] = clamp_score(intent_score["relevance"] + 6)
        intent_score["fit"] = clamp_score(intent_score["fit"] + 4)
        intent_score["composite"] = clamp_score(intent_score["composite"] + 4)
    elif family == "content_gap":
        intent_score["relevance"] = clamp_score(intent_score["relevance"] + 4)
        intent_score["receptivity"] = clamp_score(intent_score["receptivity"] + 6)
        intent_score["composite"] = clamp_score(intent_score["composite"] + 2)
    return intent_score


def discover_live_opportunities(
    client: httpx.Client,
    config: dict[str, Any],
    seen_source_urls: set[str],
) -> list[dict[str, Any]]:
    products = config.get("products", [])
    if not products:
        return []

    now_ts = datetime.now(timezone.utc).timestamp()
    keywords = build_keyword_watchlist(config)
    subreddits = build_subreddit_watchlist(config)
    query_plan = build_objective_query_plan(config)
    discovered: list[dict[str, Any]] = []
    batch_seen = set(seen_source_urls)

    def maybe_add_post(post: dict[str, Any], *, query: str | None = None) -> None:
        data = post.get("data", {})
        permalink = data.get("permalink")
        if not permalink:
            return
        source_link = f"https://www.reddit.com{permalink}"
        if source_link in batch_seen:
            return
        if data.get("over_18") or data.get("stickied") or data.get("locked"):
            return
        title = str(data.get("title") or "").strip()
        selftext = str(data.get("selftext") or "").strip()
        if not title:
            return
        combined = compact_text(f"{title} {selftext}".strip(), 420)
        if not combined:
            return
        text_lower = combined.lower()
        keyword_hits = sum(1 for keyword in keywords if keyword and keyword in text_lower)
        if query is None and keyword_hits == 0:
            return
        age_minutes = max(int((now_ts - float(data.get("created_utc") or now_ts)) // 60), 0)
        if age_minutes < 10:
            return
        product = choose_product(products, {"content": combined, "description": title})
        fit_score = product_fit_score(product, combined)
        if fit_score < 8 and keyword_hits == 0:
            return
        intent_score = compute_intent_scores(
            combined,
            fit_score=fit_score,
            keyword_hits=keyword_hits,
            age_minutes=age_minutes,
            num_comments=int(data.get("num_comments") or 0),
        )
        if intent_score["composite"] < 62:
            return
        subreddit = data.get("subreddit")
        discovered.append(
            {
                "category": "engagement",
                "surface": "reddit",
                "description": (
                    f"Found a live Reddit post in r/{subreddit} asking for a product recommendation."
                    if subreddit
                    else "Found a live Reddit post with clear purchase intent."
                ),
                "content": combined,
                "author": f"u/{data.get('author')}" if data.get("author") else "u/reddit_user",
                "audience": f"People active in r/{subreddit}" if subreddit else "Reddit shoppers",
                "source_url": source_link,
                "subreddit_or_channel": f"r/{subreddit}" if subreddit else None,
                "search_query": query,
                "intent_score": intent_score,
                "action_type": "reply",
                "expected_return_score": estimate_expected_return_score(
                    action_type="reply",
                    family="buyer_intent",
                    intent_score=intent_score,
                    fit_score=fit_score,
                    keyword_hits=keyword_hits,
                ),
            }
        )
        batch_seen.add(source_link)

    for plan_item in query_plan:
        if plan_item["family"] != "buyer_intent":
            continue
        query = plan_item["query"]
        try:
            response = client.get(
                "https://www.reddit.com/search.json",
                params={
                    "q": query,
                    "sort": "new",
                    "limit": 4,
                    "raw_json": 1,
                    "t": "month",
                },
                headers=reddit_headers(),
                timeout=20.0,
            )
            response.raise_for_status()
            for child in response.json().get("data", {}).get("children", []):
                maybe_add_post(child, query=query)
        except Exception:
            continue

    for plan_item in query_plan:
        query = plan_item["query"]
        family = plan_item["family"]
        try:
            html = search_html(client, query)
            for result in parse_search_results(html):
                source_link = result["url"]
                if source_link in batch_seen:
                    continue
                surface = classify_surface(source_link, family, result["title"], result["snippet"])
                action_type = classify_action_type(surface, family, result["title"], result["snippet"])
                if surface == "reddit" and family == "buyer_intent":
                    continue
                combined = f"{result['title']} {result['snippet']} {query}"
                keyword_hits = sum(1 for keyword in keywords if keyword and keyword in combined.lower())
                product = choose_product(
                    products,
                    {
                        "content": combined,
                        "description": result["title"],
                    },
                )
                fit_score = product_fit_score(product, combined)
                if fit_score < 6 and keyword_hits == 0:
                    continue
                intent_score = compute_search_result_scores(
                    title=result["title"],
                    snippet=result["snippet"],
                    query=query,
                    family=family,
                    fit_score=fit_score,
                    keyword_hits=keyword_hits,
                )
                if intent_score["composite"] < 54:
                    continue
                expected_return_score = estimate_expected_return_score(
                    action_type=action_type,
                    family=family,
                    intent_score=intent_score,
                    fit_score=fit_score,
                    keyword_hits=keyword_hits,
                )
                if expected_return_score < 58:
                    continue
                description = {
                    "reply": "Found a live discussion where a direct recommendation could convert quickly.",
                    "email": "Found a creator or editorial outlet with clear audience overlap and outreach potential.",
                    "outreach": "Found a possible partnership or amplification target worth a manual pitch.",
                    "content": "Found a search-driven content gap where Bia can capture demand with a targeted asset.",
                }.get(action_type, "Found a promising public-web opportunity.")
                discovered.append(
                    {
                        "category": category_for_action(action_type),
                        "surface": surface,
                        "description": description,
                        "content": compact_text(f"{result['title']} — {result['snippet']}", 380),
                        "author": clean_domain(source_link) or "public-web",
                        "audience": audience_for_surface(surface, result["title"], result["snippet"]),
                        "source_url": source_link,
                        "subreddit_or_channel": None,
                        "search_query": query,
                        "intent_score": intent_score,
                        "action_type": action_type,
                        "headline": result["title"],
                        "expected_return_score": expected_return_score,
                        "query_family": family,
                    }
                )
                batch_seen.add(source_link)
        except Exception:
            continue

    for subreddit in subreddits[:6]:
        try:
            response = client.get(
                f"https://www.reddit.com/r/{subreddit}/new.json",
                params={"limit": 8, "raw_json": 1},
                headers=reddit_headers(),
                timeout=20.0,
            )
            response.raise_for_status()
            for child in response.json().get("data", {}).get("children", []):
                maybe_add_post(child, query=None)
        except Exception:
            continue

    discovered.sort(
        key=lambda item: (
            item.get("expected_return_score", 0),
            item["intent_score"]["composite"],
            item["intent_score"]["intent"],
            item["intent_score"]["fit"],
        ),
        reverse=True,
    )
    return discovered[:10]


def lane_query_plan(
    client: httpx.Client,
    config: dict[str, Any],
    lane: dict[str, Any],
) -> tuple[list[dict[str, str]], float]:
    provider = lane.get("provider")
    if provider == "anthropic":
        return generate_query_plan_with_model(client, config)
    if provider == "openai":
        return generate_query_plan_with_openai(client, config)
    return build_objective_query_plan(config), 0.0


def lane_planned_opportunities(
    client: httpx.Client,
    config: dict[str, Any],
    lane: dict[str, Any],
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    provider = lane.get("provider")
    if provider == "anthropic":
        return plan_opportunities_with_model(client, config, observations)
    if provider == "openai":
        return plan_opportunities_with_openai(client, config, observations)
    return [], 0.0


def competition_rank(item: dict[str, Any]) -> tuple[float, int, int]:
    intent_score = item.get("intent_score") or {}
    return (
        float(item.get("competition_score", item.get("expected_return_score", 0) or 0.0)),
        int(intent_score.get("composite", 0) or 0),
        int(intent_score.get("fit", 0) or 0),
    )


def build_competing_live_queue(
    client: httpx.Client,
    config: dict[str, Any],
    seen_source_urls: set[str],
) -> tuple[list[dict[str, Any]], float]:
    lanes = enabled_competition_lanes(config.get("competition"))
    if not lanes:
        lanes = [{"provider": "heuristic", "model": "objective-baseline", "label": "Heuristic baseline"}]
    ranked: list[dict[str, Any]] = []
    total_cost = 0.0
    seed_seen = set(seen_source_urls)

    for lane in lanes:
        query_plan, query_cost = lane_query_plan(client, config, lane)
        total_cost += query_cost
        observations = collect_live_observations(client, config, query_plan, seed_seen)
        planned, planning_cost = lane_planned_opportunities(client, config, lane, observations)
        total_cost += planning_cost
        if planned:
            opportunities = planned
        else:
            opportunities = discover_live_opportunities(client, config, seed_seen)
        for item in opportunities:
            item["model_provider"] = str(lane.get("provider", "heuristic"))
            item["model_name"] = str(lane.get("model", "objective-baseline"))
            item["model_label"] = str(lane.get("label") or lane_label(item["model_provider"], item["model_name"]))
            item["competition_score"] = float(
                item.get("competition_score", item.get("expected_return_score", 0) or 0.0)
            )
            ranked.append(item)

    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for item in sorted(ranked, key=competition_rank, reverse=True):
        dedupe_key = (
            str(item.get("source_url") or ""),
            str(item.get("action_type") or ""),
            str(item.get("product_id") or ""),
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped.append(item)
    return deduped[:10], round(total_cost, 4)


def maybe_emit_strategy_update(
    client: httpx.Client,
    config: dict[str, Any],
    api_key: str,
    counters: dict[str, Any],
    current_day: str,
) -> None:
    if counters["strategy_sent"][current_day]:
        return
    if counters["actions_by_day"][current_day] < 3:
        return
    channels = sorted(counters["surfaces_by_day"][current_day])
    payload = {
        "event_type": "strategy_update",
        "category": "strategy",
        "surface": "agent_brain",
        "description": (
            f"Focused on {', '.join(channels) if channels else 'the highest-efficiency opportunities'} today. "
            f"Logged {counters['actions_by_day'][current_day]} proposals and will double down on the tactics most likely to keep sales above compute cost."
        ),
        "channels_used": channels,
        "total_actions": counters["actions_by_day"][current_day],
        "tokens_used": counters["tokens_by_day"][current_day],
        "compute_cost_usd": round(counters["cost_by_day"][current_day], 4),
        "timestamp": now_iso(),
    }
    post_event(client, config["reporting"]["events_endpoint"], api_key, payload)
    counters["strategy_sent"][current_day] = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path")
    parser.add_argument("--campaign-id")
    parser.add_argument("--api-base")
    parser.add_argument("--api-key")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, stop_agent)
    signal.signal(signal.SIGINT, stop_agent)

    try:
        config_endpoint, api_key = load_runtime_credentials(args)
    except ValueError:
        return 1

    client = httpx.Client(follow_redirects=True)
    state_path = runtime_state_path(args)
    runtime_state = load_runtime_state(state_path)
    last_config_refresh = 0.0
    config: dict[str, Any] | None = None
    template_index = random.randint(0, len(DEMO_TEMPLATES) - 1)
    last_live_refresh = 0.0
    live_queue: list[dict[str, Any]] = []
    planning_cost_pending = 0.0
    planning_tokens_pending = 0
    counters = {
        "actions_by_day": defaultdict(int),
        "surfaces_by_day": defaultdict(set),
        "tokens_by_day": defaultdict(int),
        "cost_by_day": defaultdict(float),
        "strategy_sent": defaultdict(bool),
    }

    while RUNNING:
        try:
            if config is None or time.time() - last_config_refresh > 1800:
                config = fetch_config(client, config_endpoint, api_key)
                last_config_refresh = time.time()

            if (
                not config["budget"]["remaining"]
                or config.get("status") in {"paused", "stopped", "budget_exhausted"}
                or config.get("campaign_status") in {"pending_payment", "paused_manual", "paused_budget", "canceled"}
                or not config.get("products")
            ):
                time.sleep(30)
                continue

            current_day = datetime.now(timezone.utc).date().isoformat()
            if counters["actions_by_day"][current_day] >= config["constraints"]["max_actions_per_day"]:
                maybe_emit_strategy_update(client, config, api_key, counters, current_day)
                time.sleep(30)
                continue

            if not live_queue and time.time() - last_live_refresh > DISCOVERY_REFRESH_SECONDS:
                live_queue, planning_cost_pending = build_competing_live_queue(
                    client,
                    config,
                    seen_source_urls=set(runtime_state.get("seen_source_urls", [])),
                )
                estimated_planning_tokens = (
                    int(round((planning_cost_pending / 0.018) * 1000)) if planning_cost_pending else 0
                )
                planning_tokens_pending = max(estimated_planning_tokens, 0)
                if live_queue and planning_cost_pending > 0:
                    share_cost = round(planning_cost_pending / len(live_queue), 4)
                    share_tokens = max(planning_tokens_pending // len(live_queue), 0)
                    for index, item in enumerate(live_queue):
                        item["planning_cost_share"] = share_cost
                        item["planning_tokens_share"] = share_tokens
                        if index == 0:
                            item["planning_tokens_share"] += planning_tokens_pending - (share_tokens * len(live_queue))
                    planning_cost_pending = 0.0
                    planning_tokens_pending = 0
                last_live_refresh = time.time()
                if not live_queue and planning_cost_pending > 0:
                    post_event(
                        client,
                        config["reporting"]["events_endpoint"],
                        api_key,
                        {
                            "event_type": "strategy_update",
                            "category": "strategy",
                            "surface": "agent_brain",
                            "description": (
                                "Searched the live internet and held back because nothing cleared the "
                                "expected return-on-compute threshold."
                            ),
                            "channels_used": [],
                            "model_provider": None,
                            "model_name": None,
                            "total_actions": 0,
                            "tokens_used": planning_tokens_pending,
                            "compute_cost_usd": planning_cost_pending,
                            "timestamp": now_iso(),
                        },
                    )
                    counters["tokens_by_day"][current_day] += planning_tokens_pending
                    counters["cost_by_day"][current_day] += planning_cost_pending
                    planning_cost_pending = 0.0
                    planning_tokens_pending = 0

            using_live_discovery = bool(live_queue)
            if using_live_discovery:
                template = live_queue.pop(0)
            else:
                template = DEMO_TEMPLATES[template_index % len(DEMO_TEMPLATES)]
                template_index += 1

            product = choose_product(config["products"], template)

            tracked_url = build_referral_url(product, config["campaign_id"], template["surface"])
            input_tokens = 640
            output_tokens = 220 if template["category"] in {"engagement", "outreach"} else 160
            total_tokens = input_tokens + output_tokens + int(template.get("planning_tokens_share", 0) or 0)
            total_cost = round(
                compute_cost(input_tokens, output_tokens) + float(template.get("planning_cost_share", 0.0) or 0.0),
                4,
            )
            response_text = (
                template.get("proposed_response")
                or build_proposed_response(config, product, template)
            )
            source_link = template.get("source_url") or source_url(template["surface"], str(uuid4()))
            intent_score = template.get("intent_score") or {
                "relevance": 82 if template["category"] in {"engagement", "outreach"} else 70,
                "intent": 78 if template["surface"] in {"reddit", "twitter", "forum"} else 64,
                "fit": 88,
                "receptivity": 72,
                "composite": 80 if template["category"] in {"engagement", "outreach"} else 68,
            }

            payload = {
                "event_type": "proposal",
                "category": template["category"],
                "surface": template["surface"],
                "description": template["description"],
                "source_url": source_link,
                "source_content": template["content"],
                "source_author": template["author"],
                "source_context": template["description"],
                "subreddit_or_channel": template.get("subreddit_or_channel"),
                "target_audience": template["audience"],
                "intent_score": intent_score,
                "action_type": map_action_type(template),
                "product_id": product["id"],
                "referral_url": tracked_url,
                "proposed_response": response_text,
                "rationale": build_rationale(template, product),
                "execution_instructions": (
                    template.get("execution_instructions")
                    or build_execution_instructions(template, source_link, response_text)
                ),
                "tokens_used": total_tokens,
                "compute_cost_usd": total_cost,
                "expected_impact": (
                    "high" if template["category"] in {"engagement", "outreach"} else "medium"
                ),
                "model_provider": template.get("model_provider"),
                "model_name": template.get("model_name"),
                "competition_score": template.get("competition_score", template.get("expected_return_score", 0)),
                "timestamp": now_iso(),
            }
            result = post_event(client, config["reporting"]["events_endpoint"], api_key, payload)
            counters["actions_by_day"][current_day] += 1
            counters["surfaces_by_day"][current_day].add(template["surface"])
            counters["tokens_by_day"][current_day] += total_tokens
            counters["cost_by_day"][current_day] += total_cost
            remember_source_url(state_path, runtime_state, source_link)

            if result.get("budget_exhausted"):
                maybe_emit_strategy_update(client, config, api_key, counters, current_day)
                time.sleep(30)
                continue

            maybe_emit_strategy_update(client, config, api_key, counters, current_day)
            time.sleep(
                LIVE_PROPOSAL_INTERVAL_SECONDS if using_live_discovery else FALLBACK_PROPOSAL_INTERVAL_SECONDS
            )
        except KeyboardInterrupt:
            return 0
        except Exception:
            time.sleep(10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
