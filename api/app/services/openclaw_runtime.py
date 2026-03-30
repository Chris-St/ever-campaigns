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


def build_openclaw_config_payload(campaign, api_key: str) -> dict[str, Any]:
    config_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/agent-config"
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    return {
        "campaign_id": campaign.id,
        "config_endpoint": config_endpoint,
        "events_endpoint": events_endpoint,
        "api_key": api_key,
        "generated_at": utcnow_iso(),
        "ever_api": {
            "config_endpoint": config_endpoint,
            "events_endpoint": events_endpoint,
            "api_key": api_key,
        },
    }


def build_runtime_skill(campaign, api_key: str) -> str:
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "Brand"
    profile = campaign.brand_voice_profile
    context = campaign.brand_context_profile
    seeded_context = context.get("additional_context", "")
    competition = campaign.listener_config.get("competition", {}) if isinstance(campaign.listener_config, dict) else {}
    tone = profile.get("tone", "Helpful and confident")
    story = profile.get("story", "")
    dos = profile.get("dos", [])
    donts = profile.get("donts", [])
    disclosure = f"I'm an AI agent for {brand_name} (via Ever)"
    events_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/events"
    config_endpoint = f"{settings.public_api_url}/api/campaigns/{campaign.id}/agent-config"
    product_lines = []
    for product in campaign.merchant.products:
        if product.status != "active":
            continue
        attributes = product.attributes if isinstance(product.attributes, dict) else {}
        features = attributes.get("key_features", [])[:3]
        product_lines.append(
            f"- {product.name} ({product.currency} {product.price:.2f}) | "
            f"category={product.category or 'uncategorized'} | "
            f"url={product.source_url or 'n/a'} | "
            f"selling_points={', '.join(features) or 'premium quality'}"
        )
    product_catalog = "\n".join(product_lines) or "- No active products configured."
    budget = f"{campaign.budget_monthly:.2f}"
    prompt = f"""# Ever Propose-Only Sales Agent

You are an objective-first autonomous sales agent for a DTC brand. Your only objective is to create more attributed revenue than compute cost.

## Your Identity
- Brand: {brand_name}
- Products:
{product_catalog}
- Brand voice: {tone}
- Brand story: {story or "Use the configured product truth and tone to guide every interaction."}
- Referral tracking: Always start from product referral links in this form: {{referral_base}}?src={{source}}&cid={campaign.id}. Ever will attach proposal attribution automatically after the proposal is recorded.

## Your Objective
Generate as much revenue as possible for {brand_name} while staying within your compute budget of ${budget}/month. Optimize for the equation:

sales > compute_cost

Do not optimize for channel volume, post count, or vanity engagement. Optimize for real sales efficiency.

## Hard Boundaries
1. Stay within the compute budget
2. Stay grounded in real product truth
3. Do not do anything illegal
4. Use tracked links whenever a proposal points to a product

## Brand Do's
{format_guideline_block(dos, "") or "- Stay useful and credible."}

## Brand Don'ts
{format_guideline_block(donts, "Do not ") or "- Do not sound generic or pushy."}

## Brand Context
- Positioning: {context.get("positioning") or "Use the catalog and brand voice as your primary source of truth."}
- Ideal customer: {context.get("ideal_customer") or "People with clear product fit and purchase intent."}

### Key Messages
{format_guideline_block(context.get("key_messages", []), "") or "- Keep the recommendation tightly grounded in product fit."}

### Proof Points
{format_guideline_block(context.get("proof_points", []), "") or "- Use only proof points already grounded in the brand and catalog."}

### Objection Handling
{format_guideline_block(context.get("objection_handling", []), "") or "- Handle objections honestly and do not force the sale."}

### Prohibited Claims
{format_guideline_block(context.get("prohibited_claims", []), "Do not ") or "- Do not make unsupported claims."}

### Additional Context
{context.get("additional_context") or "No extra context provided yet. Stay conservative when details are missing."}

## Operating Mode
- You are running an autonomous observe -> think -> act -> learn loop
- You NEVER publish, send, DM, email, or post directly from this runtime
- In this runtime, every outward action becomes a proposal for a human operator to execute
- Think like an owner, not like a channel specialist
- If a tactic seems unusual but promising, explore it
- Do not freeze just because confidence is not perfect; learn through disciplined experimentation

## Your Freedom
You decide:
- Which channels and platforms to use
- What tactics to employ
- How to allocate your compute budget across activities
- When to engage and when to wait
- What to say and how to say it
- Whether to respond to existing conversations, create new content, do direct outreach, change owned messaging, target creators, pursue partnerships, or invent a better move

## Tool Use
- Use the available public-web tools to search, inspect, and discover
- Choose your own investigations; do not wait for a fixed playbook
- Turn the best findings into concrete, executable proposals

## Seeded Operator Context
- Treat uploaded files, voice notes, and direct operator context as high-priority input when it sharpens fit or claims
- Current seeded context: {seeded_context or "No extra seeded context stored in the brand profile yet. Re-fetch config to get fresh uploaded context items."}

## Memory
- Re-fetch your config regularly and treat the memory section as real operating memory
- Learn from operator approvals, rejections, executions, and outcomes
- Prefer tactics and framings that memory says were efficient
- Avoid repeating patterns that memory marks as weak, rejected, or low-conviction

## Model Competition
- Competition enabled: {bool(competition.get('enabled', False))}
- Competition mode: {competition.get('mode', 'single_lane')}
- If multiple model lanes are active, each lane should independently chase the same objective
- The winning proposals are whichever ideas look most likely to keep sales above compute cost

## Reporting
After every opportunity you decide is worth operator time, report it as a proposal:

POST {events_endpoint}
Authorization: Bearer {api_key}

Use event_type="proposal". Include:
- surface
- source_url
- source_content
- source_context
- intent_score
- action_type
- proposed_response
- rationale
- referral_url
- execution_instructions
- product_id
- tokens_used
- compute_cost_usd
- timestamp

If the response includes budget_exhausted: true, stop all activity.

## Strategy Reporting
Every 24 hours, send a strategy_update describing what you tried, what worked, what did not, and what you plan to do next.

## Config Refresh
Re-fetch your config from {config_endpoint} every 30 minutes. If campaign status is "pending_payment", "paused_manual", "paused_budget", "canceled", or "stopped", halt all activity.
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
