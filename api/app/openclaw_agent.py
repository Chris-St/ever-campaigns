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
from urllib.parse import quote
from uuid import uuid4

import httpx


RUNNING = True


DEMO_TEMPLATES: list[dict[str, str]] = [
    {
        "surface": "reddit",
        "channel": "running",
        "author": "u/runner_jane",
        "content": "What underwear doesn't chafe on long runs?",
        "context": "Thread about marathon training gear",
    },
    {
        "surface": "reddit",
        "channel": "XXrunning",
        "author": "u/tempo_casey",
        "content": "Any recommendations for workout underwear that stays put during intervals?",
        "context": "Conversation about race day comfort",
    },
    {
        "surface": "reddit",
        "channel": "cycling",
        "author": "u/cadence_loop",
        "content": "Need breathable underwear for indoor cycling that disappears under leggings.",
        "context": "Gear thread for low-bulk training layers",
    },
    {
        "surface": "twitter",
        "channel": "workout underwear recommendation",
        "author": "@milejournal",
        "content": "need a workout underwear recommendation that doesn't move around mid-run",
        "context": "Short post asking for recs",
    },
    {
        "surface": "twitter",
        "channel": "best athletic thong",
        "author": "@studionotes",
        "content": "best athletic thong for hot yoga and walking all day?",
        "context": "Looking for something breathable and soft",
    },
]


def stop_agent(*_: object) -> None:
    global RUNNING
    RUNNING = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def surface_source_url(surface: str, channel: str, seed: str) -> str:
    if surface == "twitter":
        return f"https://x.com/everagent/status/{seed[:12]}?query={quote(channel)}"
    return f"https://reddit.com/r/{channel}/comments/{seed[:12]}"


def score_template(template: dict[str, str], product: dict[str, Any], threshold: int) -> dict[str, float]:
    text = f"{template['content']} {template['context']}".lower()
    score = {
        "relevance": 58.0,
        "intent": 54.0,
        "fit": 48.0,
        "receptivity": 52.0,
    }
    for keyword in ["running", "cycling", "yoga", "workout", "breathable", "chaf", "recommendation"]:
        if keyword in text:
            score["relevance"] += 6
            score["intent"] += 4
    for activity in product.get("activities", []):
        if activity.lower() in text:
            score["fit"] += 8
    if product.get("category") and product["category"].replace("_", " ") in text:
        score["fit"] += 10
    if "?" in template["content"]:
        score["receptivity"] += 18
    score = {key: min(value, 100.0) for key, value in score.items()}
    score["composite"] = round(
        score["relevance"] * 0.3
        + score["intent"] * 0.3
        + score["fit"] * 0.2
        + score["receptivity"] * 0.2,
        1,
    )
    score["should_respond"] = score["composite"] >= threshold
    return score


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens / 1000 * 0.003) + (output_tokens / 1000 * 0.015), 4)


def choose_product(products: list[dict[str, Any]], template: dict[str, str]) -> dict[str, Any]:
    text = f"{template['content']} {template['context']}".lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for product in products:
        fit_score = 0
        if product.get("category") and product["category"].replace("_", " ") in text:
            fit_score += 10
        for activity in product.get("activities", []):
            if activity.lower() in text:
                fit_score += 8
        if "chaf" in text and "High Movement" in product["name"]:
            fit_score += 18
        if "yoga" in text and "Supersoft" in product["name"]:
            fit_score += 18
        if "recovery" in text and "Recovery" in product["name"]:
            fit_score += 18
        scored.append((fit_score, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else products[0]


def build_response_text(config: dict[str, Any], product: dict[str, Any], surface: str) -> str:
    disclosure = config["brand"]["disclosure"]
    if surface == "twitter":
        return (
            f"If the goal is comfort during movement, I'd look for something breathable that stays put. "
            f"{product['name']} fits that well because it was built around {', '.join(product.get('activities', [])[:2])}. "
            f"{disclosure}"
        )
    return (
        f"If the problem is chafing or movement, the biggest unlock is a piece that stays put and dries fast. "
        f"{product['name']} is a good fit because it was built for {', '.join(product.get('activities', [])[:3])}. "
        f"{disclosure}"
    )


def build_referral_url(product: dict[str, Any], campaign_id: str, surface: str, interaction_id: str) -> str:
    return f"{product['referral_base']}?src={quote(surface)}&cid={quote(campaign_id)}&iid={quote(interaction_id)}"


def can_respond(
    counters: dict[str, Any],
    rules: dict[str, Any],
    template: dict[str, str],
    current_day: str,
) -> bool:
    if counters["responses_by_day"][current_day] >= rules["max_responses_per_day"]:
        return False
    if counters["responses_by_surface"][f"{current_day}:{template['surface']}"] >= rules["max_responses_per_subreddit_per_day"]:
        return False
    author_key = f"{current_day}:{template['author']}"
    if counters["authors_today"][author_key] >= 1:
        return False
    return True


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
        return payload["config_endpoint"], payload["api_key"]
    if args.campaign_id and args.api_base and args.api_key:
        return f"{args.api_base}/api/campaigns/{args.campaign_id}/agent-config", args.api_key
    raise ValueError("Missing OpenClaw runtime credentials")


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

    client = httpx.Client()
    last_config_refresh = 0.0
    config: dict[str, Any] | None = None
    template_index = random.randint(0, len(DEMO_TEMPLATES) - 1)
    counters = {
        "responses_by_day": defaultdict(int),
        "responses_by_surface": defaultdict(int),
        "authors_today": defaultdict(int),
    }

    while RUNNING:
        try:
            if config is None or time.time() - last_config_refresh > 1800:
                config = fetch_config(client, config_endpoint, api_key)
                last_config_refresh = time.time()

            if (
                not config["budget"]["remaining"]
                or config.get("campaign_status") == "paused"
                or not config.get("products")
            ):
                time.sleep(30)
                continue

            enabled_surfaces = {
                surface: details
                for surface, details in config["surfaces"].items()
                if details.get("enabled")
            }
            if not enabled_surfaces:
                time.sleep(30)
                continue

            template = DEMO_TEMPLATES[template_index % len(DEMO_TEMPLATES)]
            template_index += 1
            if template["surface"] not in enabled_surfaces:
                time.sleep(6)
                continue

            product = choose_product(config["products"], template)
            score = score_template(template, product, config["rules"]["intent_threshold"])
            source_url = surface_source_url(template["surface"], template["channel"], uuid4().hex)

            scoring_input_tokens = 620
            scoring_output_tokens = 180
            scoring_cost = compute_cost(scoring_input_tokens, scoring_output_tokens)
            intent_payload = {
                "event_type": "intent_detected",
                "surface": template["surface"],
                "source_url": source_url,
                "source_content": template["content"],
                "source_author": template["author"],
                "source_context": template["context"],
                "intent_score": {
                    "relevance": score["relevance"],
                    "intent": score["intent"],
                    "fit": score["fit"],
                    "receptivity": score["receptivity"],
                    "composite": score["composite"],
                },
                "action_taken": "skip",
                "response_text": None,
                "referral_url": None,
                "product_id": product["id"],
                "tokens_used": scoring_input_tokens + scoring_output_tokens,
                "compute_cost_usd": scoring_cost,
                "timestamp": now_iso(),
            }
            post_event(client, config["reporting"]["events_endpoint"], api_key, intent_payload)

            current_day = datetime.now(timezone.utc).date().isoformat()
            if not score["should_respond"] or not can_respond(
                counters,
                config["rules"],
                template,
                current_day,
            ):
                skip_payload = {
                    **intent_payload,
                    "event_type": "response_skipped",
                    "timestamp": now_iso(),
                }
                post_event(client, config["reporting"]["events_endpoint"], api_key, skip_payload)
                time.sleep(6)
                continue

            interaction_id = str(uuid4())
            referral_url = build_referral_url(
                product,
                config["campaign_id"],
                template["surface"],
                interaction_id,
            )
            response_text = build_response_text(config, product, template["surface"])
            generation_input_tokens = 910
            generation_output_tokens = 240
            generation_cost = compute_cost(generation_input_tokens, generation_output_tokens)
            response_payload = {
                "event_type": (
                    "response_pending_review"
                    if config["rules"]["review_mode"]
                    else "response_posted"
                ),
                "surface": template["surface"],
                "source_url": source_url,
                "source_content": template["content"],
                "source_author": template["author"],
                "source_context": template["context"],
                "intent_score": {
                    "relevance": score["relevance"],
                    "intent": score["intent"],
                    "fit": score["fit"],
                    "receptivity": score["receptivity"],
                    "composite": score["composite"],
                },
                "action_taken": "reply",
                "response_text": response_text,
                "referral_url": referral_url,
                "product_id": product["id"],
                "tokens_used": generation_input_tokens + generation_output_tokens,
                "compute_cost_usd": generation_cost,
                "timestamp": now_iso(),
            }
            event_result = post_event(
                client,
                config["reporting"]["events_endpoint"],
                api_key,
                response_payload,
            )
            if event_result.get("budget_exhausted"):
                time.sleep(30)
            counters["responses_by_day"][current_day] += 1
            counters["responses_by_surface"][f"{current_day}:{template['surface']}"] += 1
            counters["authors_today"][f"{current_day}:{template['author']}"] += 1
            time.sleep(6)
        except KeyboardInterrupt:
            return 0
        except Exception:
            time.sleep(10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
