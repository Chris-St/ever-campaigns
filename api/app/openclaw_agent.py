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


def stop_agent(*_: object) -> None:
    global RUNNING
    RUNNING = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def choose_product(products: list[dict[str, Any]], template: dict[str, str]) -> dict[str, Any]:
    text = f"{template['content']} {template['description']}".lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for product in products:
        fit_score = 0
        if product.get("category") and product["category"].replace("_", " ") in text:
            fit_score += 8
        for point in product.get("key_selling_points", []):
            if point.lower().split()[0] in text:
                fit_score += 6
        for activity in product.get("activities", []):
            if activity.lower() in text:
                fit_score += 8
        if "chaf" in text and "High Movement" in product["name"]:
            fit_score += 16
        scored.append((fit_score, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else products[0]


def build_response_text(config: dict[str, Any], product: dict[str, Any]) -> str:
    disclosure = config["brand"]["disclosure"]
    selling_points = product.get("key_selling_points", [])[:2]
    selling_line = ", ".join(selling_points) if selling_points else product["name"]
    return (
        f"If the goal is a better fit during movement, I'd bias toward something that stays put and feels premium. "
        f"{product['name']} stands out because of {selling_line}. {disclosure}"
    )


def build_referral_url(product: dict[str, Any], campaign_id: str, surface: str, interaction_id: str) -> str:
    return f"{product['referral_base']}?src={quote(surface)}&cid={quote(campaign_id)}&iid={quote(interaction_id)}"


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
            f"Focused on {', '.join(channels) if channels else 'the best available channels'} today. "
            f"Logged {counters['actions_by_day'][current_day]} actions and will double down on what generates clicks efficiently."
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

    client = httpx.Client()
    last_config_refresh = 0.0
    config: dict[str, Any] | None = None
    template_index = random.randint(0, len(DEMO_TEMPLATES) - 1)
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
                or config.get("campaign_status") == "paused"
                or not config.get("products")
            ):
                time.sleep(30)
                continue

            current_day = datetime.now(timezone.utc).date().isoformat()
            if counters["actions_by_day"][current_day] >= config["constraints"]["max_actions_per_day"]:
                maybe_emit_strategy_update(client, config, api_key, counters, current_day)
                time.sleep(30)
                continue

            template = DEMO_TEMPLATES[template_index % len(DEMO_TEMPLATES)]
            template_index += 1
            product = choose_product(config["products"], template)

            interaction_id = str(uuid4())
            tracked_url = (
                build_referral_url(product, config["campaign_id"], template["surface"], interaction_id)
                if template["category"] in {"engagement", "outreach"}
                else None
            )
            input_tokens = 640
            output_tokens = 220 if template["category"] in {"engagement", "outreach"} else 120
            total_tokens = input_tokens + output_tokens
            total_cost = compute_cost(input_tokens, output_tokens)

            payload = {
                "event_type": "action",
                "category": template["category"],
                "surface": template["surface"],
                "description": template["description"],
                "source_url": source_url(template["surface"], interaction_id),
                "source_content": template["content"],
                "source_author": template["author"],
                "target_audience": template["audience"],
                "product_id": product["id"],
                "referral_url": tracked_url,
                "response_text": (
                    build_response_text(config, product)
                    if template["category"] in {"engagement", "outreach"}
                    else None
                ),
                "tokens_used": total_tokens,
                "compute_cost_usd": total_cost,
                "expected_impact": (
                    "high" if template["category"] in {"engagement", "outreach"} else "medium"
                ),
                "timestamp": now_iso(),
            }
            result = post_event(client, config["reporting"]["events_endpoint"], api_key, payload)
            counters["actions_by_day"][current_day] += 1
            counters["surfaces_by_day"][current_day].add(template["surface"])
            counters["tokens_by_day"][current_day] += total_tokens
            counters["cost_by_day"][current_day] += total_cost

            if result.get("budget_exhausted"):
                maybe_emit_strategy_update(client, config, api_key, counters, current_day)
                time.sleep(30)
                continue

            maybe_emit_strategy_update(client, config, api_key, counters, current_day)
            time.sleep(6)
        except KeyboardInterrupt:
            return 0
        except Exception:
            time.sleep(10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
