from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR, settings


REPO_ROOT = BASE_DIR.parent
PROCESS_RUNTIME_ROOT = BASE_DIR / ".runtime" / "openclaw"
OPENCLAW_RUNTIME_ROOT = REPO_ROOT / ".openclaw" / "runtime" / "campaigns"
SKILL_ROOT = REPO_ROOT / ".openclaw" / "skills" / "ever-listener"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def campaign_runtime_dir(campaign_id: str) -> Path:
    return PROCESS_RUNTIME_ROOT / campaign_id


def campaign_openclaw_dir(campaign_id: str) -> Path:
    return OPENCLAW_RUNTIME_ROOT / campaign_id


def campaign_runtime_config_path(campaign_id: str) -> Path:
    return campaign_openclaw_dir(campaign_id) / "config.json"


def campaign_runtime_skill_path(campaign_id: str) -> Path:
    return campaign_openclaw_dir(campaign_id) / "SKILL.md"


def campaign_manifest_path(campaign_id: str) -> Path:
    return campaign_runtime_dir(campaign_id) / "manifest.json"


def is_process_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_manifest(campaign_id: str) -> dict[str, Any]:
    path = campaign_manifest_path(campaign_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_manifest(campaign_id: str, payload: dict[str, Any]) -> None:
    runtime_dir = campaign_runtime_dir(campaign_id)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    campaign_manifest_path(campaign_id).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def format_guideline_block(items: list[str], prefix: str) -> str:
    if not items:
        return ""
    return "\n".join(f"- {prefix}{item}" for item in items)


def build_reddit_footer(brand_name: str) -> str:
    return (
        "---\n"
        f"*I'm an AI agent for {brand_name}, built by Ever. I only respond when I think I can help. "
        "Not affiliated with this subreddit.*"
    )


def build_openclaw_config_payload(campaign, api_key: str) -> dict[str, Any]:
    config_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/agent-config"
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    return {
        "campaign_id": campaign.id,
        "config_endpoint": config_endpoint,
        "events_endpoint": events_endpoint,
        "api_key": api_key,
        "reddit": {
            "client_id": settings.reddit_client_id or "",
            "client_secret": settings.reddit_client_secret or "",
            "username": settings.reddit_username,
            "password": settings.reddit_password or "",
            "user_agent": settings.reddit_user_agent,
            "bio": settings.reddit_bot_bio,
        },
        "ever_api": {
            "config_endpoint": config_endpoint,
            "events_endpoint": events_endpoint,
            "api_key": api_key,
        },
    }


def build_runtime_skill(campaign, api_key: str) -> str:
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "Brand"
    tone = campaign.brand_voice_profile.get("tone", "Helpful and confident")
    story = campaign.brand_voice_profile.get("story", "")
    disclosure = f"I'm an AI agent for {brand_name} (via Ever)"
    surfaces = campaign.listener_config.get("surfaces", [])
    reddit_surface = next(
        (surface for surface in surfaces if surface.get("type") == "reddit"),
        {},
    )
    twitter_surface = next(
        (surface for surface in surfaces if surface.get("type") == "twitter"),
        {},
    )
    product_categories = sorted(
        {
            product.category.replace("_", " ")
            for product in campaign.merchant.products
            if product.status == "active" and product.category
        }
    )
    safeguards = campaign.listener_config.get("safeguards", {})
    thresholds = campaign.listener_config.get("thresholds", {})
    dos = campaign.brand_voice_profile.get("dos", [])
    donts = campaign.brand_voice_profile.get("donts", [])
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    reddit_footer = build_reddit_footer(brand_name)
    subreddit_list = ", ".join(reddit_surface.get("subreddits", [])) or "none configured"
    search_queries = ", ".join(twitter_surface.get("search_queries", [])) or "none configured"
    category_list = ", ".join(product_categories) or "your configured product categories"
    example_product = next(
        (product for product in campaign.merchant.products if product.status == "active"),
        None,
    )
    referral_base = (
        f"https://ever.com/go/{example_product.id}"
        if example_product is not None
        else "https://ever.com/go/{product_id}"
    )
    parts = [
        f"# Ever Intent Listener for {brand_name}",
        "",
        f"You are an autonomous sales agent for {brand_name}. You monitor the web for people who might benefit from the brand's products and respond helpfully.",
        "",
        "## On Startup",
        f"Fetch your config: GET {settings.public_api_url}/api/campaigns/{campaign.id}/agent-config",
        f"Authorization: Bearer {api_key}",
        f"Use Reddit account: {settings.reddit_username}",
        f'Reddit profile bio should read: "{settings.reddit_bot_bio}"',
        "",
        "## Core Loop",
        "",
        "### Monitor",
        f"Browse these subreddits: {subreddit_list}",
        f"Search Twitter/X for: {search_queries}",
        f"Look for conversations where someone expresses a need matching: {category_list}",
        "",
        "### Evaluate Each Signal",
        "Score 0-100 on: relevance, intent, fit, receptivity.",
        f"Only act if composite score >= {thresholds.get('composite_min', 70)}.",
        "",
        "### Respond",
        "Write a 2-4 sentence response that:",
        "- Is genuinely helpful first, promotional second",
        "- Addresses the specific need expressed",
        f"- Sounds like: {tone}",
    ]
    if story:
        parts.append(f"- Background context: {story}")
    parts.extend(
        [
            "- Matches platform culture",
            "- Naturally mentions the product only if it fits",
            f'- Ends with: "{disclosure}"',
            f'- For Reddit replies, append exactly:\n{reddit_footer}',
            f"- Includes referral link: {referral_base}?src={{surface}}&cid={campaign.id}&iid={{uuid}}",
            "",
        ]
    )
    dos_block = format_guideline_block(dos, "")
    donts_block = format_guideline_block(donts, "Do not ")
    if dos_block:
        parts.extend([dos_block, ""])
    if donts_block:
        parts.extend([donts_block, ""])
    parts.extend(
        [
            "### Report Every Action",
            f"POST {events_endpoint}",
            f"Authorization: Bearer {api_key}",
            "Content-Type: application/json",
            "",
            "Send the event payload as specified. If response returns budget_exhausted: true, stop.",
            "",
            "### Anti-Spam (NON-NEGOTIABLE)",
            f"- Max {safeguards.get('max_responses_per_surface_per_day', 10)} responses per subreddit per day",
            f"- Max {safeguards.get('max_responses_per_day', 50)} total responses per day",
            f"- Never respond to same author twice in {safeguards.get('never_respond_to_same_author_within_hours', 24)}h",
            f"- Never respond to posts < {safeguards.get('minimum_post_age_minutes', 10)} minutes old",
            f"- Max {safeguards.get('max_thread_replies', 2)} responses per thread",
            f"- Wait {safeguards.get('minimum_minutes_between_surface_responses', 5)} minutes between responses on same surface",
            "- Always include disclosure",
            "- Never trash competitors",
            "- If >20% negative engagement today, pause 6 hours",
            "",
            "### Reddit-Specific Rules",
            "- Account must have bot flair or clearly indicate bot status in profile",
            f"- Every response MUST end with:\n{reddit_footer}",
            "- Never post in subreddits that explicitly ban bots (check sidebar rules before first post)",
            "- Never vote on any content",
            "- Never post top-level submissions, only reply to existing posts/comments",
            "- If a moderator asks you to stop, immediately add that subreddit to a blocklist",
            "- Comply with Reddit API rate limits: max 60 requests per minute",
            f'- User-Agent header must identify the bot: "{settings.reddit_user_agent}"',
            "",
            "### Config Refresh",
            "Re-fetch /agent-config every 30 minutes. If status is \"paused\" or \"stopped\", halt.",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def build_openclaw_skill_bundle(campaign, api_key: str) -> dict[str, Any]:
    config_payload = build_openclaw_config_payload(campaign, api_key)
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "Brand"
    return {
        "campaign_id": campaign.id,
        "brand_name": brand_name,
        "file_name": "SKILL.md",
        "config_file_name": "config.json",
        "skill_markdown": build_runtime_skill(campaign, api_key),
        "config_json": config_payload,
    }


def write_openclaw_runtime_files(campaign, api_key: str) -> dict[str, str]:
    openclaw_dir = campaign_openclaw_dir(campaign.id)
    openclaw_dir.mkdir(parents=True, exist_ok=True)
    config_path = campaign_runtime_config_path(campaign.id)
    skill_path = campaign_runtime_skill_path(campaign.id)
    bundle = build_openclaw_skill_bundle(campaign, api_key)
    config_path.write_text(
        json.dumps(bundle["config_json"], indent=2),
        encoding="utf-8",
    )
    skill_path.write_text(bundle["skill_markdown"], encoding="utf-8")
    return {
        "config_path": str(config_path),
        "skill_path": str(skill_path),
    }


def launch_openclaw_agent(campaign, api_key: str) -> dict[str, Any]:
    runtime_dir = campaign_runtime_dir(campaign.id)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "agent.log"
    manifest = read_manifest(campaign.id)
    existing_pid = manifest.get("pid")
    if is_process_running(existing_pid):
        return manifest

    runtime_files = write_openclaw_runtime_files(campaign, api_key)
    config_path = runtime_files["config_path"]
    skill_path = runtime_files["skill_path"]

    launch_command = [
        sys.executable,
        "-m",
        "app.openclaw_agent",
        "--config-path",
        config_path,
    ]

    if os.environ.get("PYTEST_CURRENT_TEST"):
        manifest = {
            "campaign_id": campaign.id,
            "status": "test-mode",
            "pid": None,
            "started_at": utcnow_iso(),
            "config_path": config_path,
            "skill_path": skill_path,
            "log_path": str(log_path),
            "launch_command": " ".join(launch_command),
        }
        write_manifest(campaign.id, manifest)
        return manifest

    with log_path.open("ab") as log_file:
        process = subprocess.Popen(  # noqa: S603
            launch_command,
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    manifest = {
        "campaign_id": campaign.id,
        "status": "running",
        "pid": process.pid,
        "started_at": utcnow_iso(),
        "config_path": config_path,
        "skill_path": skill_path,
        "log_path": str(log_path),
        "launch_command": " ".join(launch_command),
    }
    write_manifest(campaign.id, manifest)
    return manifest


def stop_openclaw_agent(campaign_id: str) -> dict[str, Any]:
    manifest = read_manifest(campaign_id)
    pid = manifest.get("pid")
    if is_process_running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    manifest.update({"status": "stopped", "stopped_at": utcnow_iso()})
    write_manifest(campaign_id, manifest)
    return manifest
