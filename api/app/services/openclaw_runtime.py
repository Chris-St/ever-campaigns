from __future__ import annotations

import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR, settings


REPO_ROOT = BASE_DIR.parent
PROCESS_RUNTIME_ROOT = BASE_DIR / ".runtime" / "openclaw"
OPENCLAW_RUNTIME_ROOT = REPO_ROOT / ".openclaw" / "runtime" / "campaigns"
EXTERNAL_AGENT_ROOT = REPO_ROOT / "agent"


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


def external_agent_config_path() -> Path:
    return EXTERNAL_AGENT_ROOT / "config.json"


def external_agent_prompt_path() -> Path:
    return EXTERNAL_AGENT_ROOT / "CLAUDE.md"


def external_agent_launch_path() -> Path:
    return EXTERNAL_AGENT_ROOT / "launch.sh"


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


def product_slug_key(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace("&", "and")
        .replace("-", "_")
        .replace(" ", "_")
    )


def build_referral_urls(campaign) -> dict[str, str]:
    referral_urls: dict[str, str] = {}
    for product in campaign.merchant.products:
        if product.status != "active":
            continue
        referral_urls[product_slug_key(product.name)] = (
            f"{settings.public_api_url}/go/{product.id}?src=agent&cid={campaign.id}"
        )
    return referral_urls


def build_openclaw_config_payload(campaign, api_key: str) -> dict[str, Any]:
    config_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/agent-config"
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    referral_urls = build_referral_urls(campaign)
    return {
        "campaign_id": campaign.id,
        "config_endpoint": config_endpoint,
        "events_endpoint": events_endpoint,
        "api_key": api_key,
        "ever_api": {
            "base_url": settings.public_api_url,
            "campaign_id": campaign.id,
            "config_endpoint": config_endpoint,
            "events_endpoint": events_endpoint,
            "api_key": api_key,
        },
        "reddit": {
            "client_id": "PASTE_REDDIT_CLIENT_ID",
            "client_secret": "PASTE_REDDIT_CLIENT_SECRET",
            "username": settings.reddit_username or "PASTE_REDDIT_USERNAME",
            "password": "PASTE_REDDIT_PASSWORD",
        },
        "email": {
            "address": "PASTE_EMAIL_ADDRESS",
            "password": "PASTE_EMAIL_APP_PASSWORD",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
        },
        "referral_urls": referral_urls,
        "generated_at": utcnow_iso(),
    }


def build_runtime_skill(campaign, api_key: str) -> str:
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "Brand"
    profile = campaign.brand_voice_profile
    context = campaign.brand_context_profile
    tone = profile.get("tone", "Helpful and confident")
    story = profile.get("story", "")
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    referral_urls = build_referral_urls(campaign)
    product_lines = []
    for product in campaign.merchant.products:
        if product.status != "active":
            continue
        product_lines.append(
            f"- {product.name} ({product.currency} {product.price:.2f}) — "
            f"{product.description or 'Use the product page and catalog for details.'}"
        )
    product_catalog = "\n".join(product_lines) or "- No active products configured."
    referral_block = "\n".join(
        f"- {key}: {value}" for key, value in sorted(referral_urls.items())
    ) or "- No referral URLs available yet."
    prompt = f"""# {brand_name} Autonomous Sales Agent

You are an autonomous sales agent for {brand_name}. Your single objective is to generate more revenue than you cost in compute.

## Your Identity
- Brand: {brand_name}
- Voice: {tone}
- Story: {story or "Use the catalog, brand context, and observed internet behavior as your source of truth."}
- Disclosure: You MUST always identify yourself as an AI agent for {brand_name} when communicating with any human.

## Your Products
{product_catalog}

Store: https://{campaign.merchant.domain}

## Your Objective
Maximize:

attributed_revenue - compute_cost

You have a compute budget of ${campaign.budget_monthly:.2f}. Your job is to find ways to sell real products to real humans while keeping your compute cost below the value you generate.

## Your Tracked Links
Use these tracked URLs whenever you recommend or link to a product:
{referral_block}

If you do not have a tracked link for a product yet, use the raw product URL and add ?ref=ever.

## Your Tools
You have full access to:
- A web browser
- Reddit and other public communities
- Email and DM style outreach when credentials are available
- The file system
- Shell commands if needed

## Your Constraints
1. Always disclose that you are an AI agent for {brand_name}
2. Never make health or medical claims
3. Never spam or blast identical messages
4. Never disparage competitors
5. Stay genuinely helpful first
6. Respect platform rules
7. Stay within the compute budget
8. Do nothing illegal

## Your Freedom
Everything else is up to you. You decide the platform, tactic, format, angle, timing, and experiments.

## Brand Context
- Positioning: {context.get("positioning") or "No extra positioning provided yet."}
- Ideal customer: {context.get("ideal_customer") or "People with strong fit to the product catalog."}
- Key messages:
{format_guideline_block(context.get("key_messages", []), "") or "- Use real product fit and product truth."}
- Proof points:
{format_guideline_block(context.get("proof_points", []), "") or "- Use grounded product truth only."}
- Objection handling:
{format_guideline_block(context.get("objection_handling", []), "") or "- Answer objections honestly and directly."}
- Prohibited claims:
{format_guideline_block(context.get("prohibited_claims", []), "Do not ") or "- Do not invent unsupported claims."}
- Additional context:
{context.get("additional_context") or "No additional operator context has been added yet."}

## Reporting
After every action, report it to Ever:

POST {events_endpoint}
Authorization: Bearer {api_key}

Use event_type="action" for real actions and event_type="strategy_update" for learning summaries. If you are not ready to act yet, you may still report a proposal via event_type="proposal" so the operator can execute it.

Every report should include:
- category
- surface
- description
- source_url
- response_text when relevant
- referral_url when relevant
- product_id when relevant
- tokens_used
- compute_cost_usd
- timestamp

If the response includes budget_exhausted: true, stop all activity.

## Your Memory
Keep learning notes in memory.md. After every action, write:
- What you did
- What happened
- What you learned
- What to try next

Read memory.md at the start of every session.

## Suggested Starting Points
- Browse communities where people actively ask for workout underwear recommendations
- Find creators, editors, and communities where a Bia product genuinely fits
- Reach out directly when the fit is strong
- Create content if owned content has a better expected return than reply-based outreach
- Try unusual tactics if they appear efficient

Go.
"""
    return prompt.strip() + "\n"


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
    if manifest.get("status") in {"running", "external-ready"}:
        return manifest

    runtime_files = write_openclaw_runtime_files(campaign, api_key)
    config_path = runtime_files["config_path"]
    skill_path = runtime_files["skill_path"]
    launch_command = f"cd {EXTERNAL_AGENT_ROOT} && bash launch.sh"

    if os.environ.get("PYTEST_CURRENT_TEST"):
        manifest = {
            "campaign_id": campaign.id,
            "status": "test-mode",
            "pid": None,
            "started_at": utcnow_iso(),
            "config_path": config_path,
            "skill_path": skill_path,
            "log_path": str(log_path),
            "launch_command": launch_command,
        }
        write_manifest(campaign.id, manifest)
        return manifest

    manifest = {
        "campaign_id": campaign.id,
        "status": "external-ready",
        "pid": None,
        "started_at": utcnow_iso(),
        "config_path": config_path,
        "skill_path": skill_path,
        "log_path": str(log_path),
        "launch_command": launch_command,
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
