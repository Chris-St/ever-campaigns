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


def build_runtime_skill(campaign) -> str:
    brand_name = campaign.brand_voice_profile.get("brand_name") or campaign.merchant.name or "Brand"
    surfaces = [
        surface.get("type", "surface")
        for surface in campaign.listener_config.get("surfaces", [])
        if surface.get("enabled", True)
    ]
    safeguards = campaign.listener_config.get("safeguards", {})
    review_mode = campaign.listener_config.get("review_mode", "auto")
    skill_template_path = SKILL_ROOT / "SKILL.md"
    template = (
        skill_template_path.read_text(encoding="utf-8").strip()
        if skill_template_path.exists()
        else "# Ever Intent Listener Agent"
    )
    campaign_context = [
        "",
        "## Runtime Context",
        f"- Brand: {brand_name}",
        f"- Campaign ID: {campaign.id}",
        f"- Store domain: {campaign.merchant.domain}",
        f"- Surfaces enabled: {', '.join(surfaces) if surfaces else 'none'}",
        f"- Review mode: {review_mode}",
        f"- Max responses per day: {safeguards.get('max_responses_per_day', 50)}",
        (
            "- Use the generated config.json in this same runtime folder to fetch live config "
            "and authenticate with Ever."
        ),
    ]
    return "\n".join([template, *campaign_context]).strip() + "\n"


def write_openclaw_runtime_files(campaign, api_key: str) -> dict[str, str]:
    openclaw_dir = campaign_openclaw_dir(campaign.id)
    openclaw_dir.mkdir(parents=True, exist_ok=True)
    config_path = campaign_runtime_config_path(campaign.id)
    skill_path = campaign_runtime_skill_path(campaign.id)
    config_path.write_text(
        json.dumps(
            {
                "campaign_id": campaign.id,
                "config_endpoint": f"{settings.public_api_url}/api/campaigns/{campaign.id}/agent-config",
                "api_key": api_key,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    skill_path.write_text(build_runtime_skill(campaign), encoding="utf-8")
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
