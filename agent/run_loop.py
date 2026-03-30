from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
API_ENV_PATH = ROOT.parent / "api" / ".env"
METER_STATE_PATH = ROOT / ".meter_state.json"
SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
TURN_MESSAGE = (
    "Read CLAUDE.md, soul.md, and memory.md in this workspace. Start working the Bia campaign. "
    "Before you commit to a proposal, deliberately look across multiple opportunity classes rather than defaulting to the easiest familiar surface. "
    "Avoid another near-duplicate Reddit proposal unless it is clearly the best available option after broader exploration. "
    "Find one real public opportunity with a real source URL, use the tracked Bia links, and report either an action or a proposal back to Ever through the configured events endpoint. "
    "Any proposal you log must include real source_content, source_context, a concrete action_type, a linked product when possible, a tracked referral_url, and a rationale."
)


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{timestamp}] {message}", flush=True)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_provider_env() -> None:
    values = load_env_file(API_ENV_PATH)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if not os.environ.get(key) and values.get(key):
            os.environ[key] = values[key]


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_meter_state() -> dict[str, object]:
    if not METER_STATE_PATH.exists():
        return {}
    try:
        return json.loads(METER_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_meter_state(state: dict[str, object]) -> None:
    METER_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def fetch_agent_config(base_url: str, campaign_id: str, api_key: str) -> dict:
    request = Request(
        f"{base_url}/api/campaigns/{campaign_id}/agent-config",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_agent_event(base_url: str, campaign_id: str, api_key: str, payload: dict[str, object]) -> dict:
    request = Request(
        f"{base_url}/api/campaigns/{campaign_id}/events",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def openclaw_turn(thinking: str) -> int:
    command = [
        "openclaw",
        "agent",
        "--local",
        "--agent",
        "main",
        "--thinking",
        thinking,
        "--message",
        TURN_MESSAGE,
    ]
    log(f"Starting agent turn with thinking={thinking}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    log(f"Agent turn finished with exit code {completed.returncode}")
    return completed.returncode


def prepare_prompt() -> None:
    subprocess.run(["python3", "prepare.py"], cwd=ROOT, check=True)


def status_summary(payload: dict) -> str:
    budget = payload.get("budget", {})
    return (
        f"campaign_status={payload.get('campaign_status')} "
        f"listener_status={payload.get('status')} "
        f"budget_remaining=${budget.get('remaining', 0):.2f}"
    )


def latest_session_log() -> Path | None:
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_usage_rows(path: Path, from_line: int = 0) -> tuple[int, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for index, raw_line in enumerate(lines[from_line:], start=from_line):
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "message":
            continue
        message = payload.get("message") or {}
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage") or {}
        cost_block = usage.get("cost") or {}
        total_cost = float(cost_block.get("total", 0.0) or 0.0)
        total_tokens = int(usage.get("totalTokens", 0) or 0)
        if total_cost <= 0 and total_tokens <= 0:
            continue
        rows.append(
            {
                "line_index": index,
                "provider": message.get("provider") or "unknown",
                "model": message.get("model") or "unknown",
                "tokens": total_tokens,
                "cost": total_cost,
                "timestamp": payload.get("timestamp"),
            }
        )
    return len(lines), rows


def aggregate_usage(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, float | int]]:
    groups: dict[tuple[str, str], dict[str, float | int]] = defaultdict(
        lambda: {
            "tokens": 0,
            "cost": 0.0,
            "start_line": -1,
            "end_line": -1,
            "count": 0,
        }
    )
    for row in rows:
        key = (str(row["provider"]), str(row["model"]))
        group = groups[key]
        group["tokens"] += int(row["tokens"])
        group["cost"] += float(row["cost"])
        line_index = int(row["line_index"])
        group["start_line"] = line_index if int(group["start_line"]) < 0 else min(int(group["start_line"]), line_index)
        group["end_line"] = max(int(group["end_line"]), line_index)
        group["count"] += 1
    return groups


def reconcile_provider_metering(
    base_url: str,
    campaign_id: str,
    api_key: str,
    agent_config: dict,
) -> dict[str, object]:
    session_path = latest_session_log()
    if session_path is None:
        return {"posted": 0, "cost": 0.0}

    line_count, all_rows = load_usage_rows(session_path, from_line=0)
    total_cost = round(sum(float(row["cost"]) for row in all_rows), 6)
    total_tokens = sum(int(row["tokens"]) for row in all_rows)
    state = load_meter_state()
    same_session = state.get("session_path") == str(session_path)
    prior_line_count = int(state.get("line_count", 0) or 0) if same_session else 0
    budget_spent = float((agent_config.get("budget") or {}).get("spent", 0.0) or 0.0)
    posted = 0
    posted_cost = 0.0

    if same_session and prior_line_count > line_count:
        prior_line_count = 0

    if not same_session and total_cost > budget_spent + 0.01:
        missing_cost = round(total_cost - budget_spent, 6)
        all_groups = aggregate_usage(all_rows)
        if len(all_groups) == 1:
            (provider, model), group = next(iter(all_groups.items()))
            tokens_used = int(group["tokens"])
            model_provider = provider
            model_name = model
        else:
            tokens_used = total_tokens
            model_provider = "external"
            model_name = "session-log"
        event_id = f"metering:{session_path.stem}:reconcile:v1"
        description = (
            f"Reconciled external provider spend from the OpenClaw session log. "
            f"This adjusts Ever's budget meter to match real provider cost already incurred."
        )
        result = post_agent_event(
            base_url,
            campaign_id,
            api_key,
            {
                "event_id": event_id,
                "event_type": "metering",
                "category": "metering",
                "surface": "agent_runtime",
                "description": description,
                "tokens_used": tokens_used,
                "compute_cost_usd": missing_cost,
                "model_provider": model_provider,
                "model_name": model_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        posted += 1
        posted_cost += missing_cost
        log(
            f"Reconciled ${missing_cost:.4f} of historical provider spend from session log "
            f"({result.get('budget_remaining', 'unknown')} remaining)."
        )

    if same_session and prior_line_count < line_count:
        _, new_rows = load_usage_rows(session_path, from_line=prior_line_count)
        groups = aggregate_usage(new_rows)
        for (provider, model), group in groups.items():
            cost = round(float(group["cost"]), 6)
            if cost <= 0:
                continue
            event_id = (
                f"metering:{session_path.stem}:{int(group['start_line'])}-{int(group['end_line'])}:{provider}:{model}"
            )
            description = (
                f"Metered external provider spend from the OpenClaw session log for {provider}/{model} "
                f"over lines {int(group['start_line'])}-{int(group['end_line'])}."
            )
            result = post_agent_event(
                base_url,
                campaign_id,
                api_key,
                {
                    "event_id": event_id,
                    "event_type": "metering",
                    "category": "metering",
                    "surface": "agent_runtime",
                    "description": description,
                    "tokens_used": int(group["tokens"]),
                    "compute_cost_usd": cost,
                    "model_provider": provider,
                    "model_name": model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            posted += 1
            posted_cost += cost
            log(
                f"Metered ${cost:.4f} for {provider}/{model} "
                f"({result.get('budget_remaining', 'unknown')} remaining)."
            )

    save_meter_state(
        {
            "session_path": str(session_path),
            "line_count": line_count,
            "session_total_cost": total_cost,
            "session_total_tokens": total_tokens,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"posted": posted, "cost": round(posted_cost, 6)}


def should_stop(payload: dict) -> tuple[bool, str]:
    budget = payload.get("budget", {})
    remaining = float(budget.get("remaining", 0) or 0)
    campaign_status = payload.get("campaign_status")
    listener_status = payload.get("status")

    if campaign_status != "active":
        return True, f"campaign status is {campaign_status}"
    if listener_status in {"stopped", "paused", "budget_exhausted"}:
        return True, f"listener status is {listener_status}"
    if remaining <= 0:
        return True, "budget is exhausted"
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ever external agent in a simple continuous loop.")
    parser.add_argument("--interval", type=int, default=180, help="Seconds to wait between agent turns.")
    parser.add_argument("--thinking", default="medium", help="OpenClaw thinking level.")
    parser.add_argument("--max-turns", type=int, default=0, help="Optional cap on turns. 0 means unlimited.")
    parser.add_argument("--once", action="store_true", help="Run exactly one turn, then exit.")
    args = parser.parse_args()

    ensure_provider_env()
    prepare_prompt()

    config = load_config()
    ever_api = config["ever_api"]
    base_url = ever_api["base_url"].rstrip("/")
    campaign_id = ever_api["campaign_id"]
    api_key = ever_api["api_key"]

    turns = 0
    consecutive_failures = 0

    log("Ever overnight loop starting")
    log(f"Campaign ID: {campaign_id}")

    while True:
        try:
            agent_config = fetch_agent_config(base_url, campaign_id, api_key)
        except (HTTPError, URLError, TimeoutError) as exc:
            consecutive_failures += 1
            sleep_for = min(args.interval * max(consecutive_failures, 1), 900)
            log(f"Failed to fetch agent-config: {exc}. Retrying in {sleep_for}s.")
            time.sleep(sleep_for)
            continue

        reconciliation = reconcile_provider_metering(base_url, campaign_id, api_key, agent_config)
        if reconciliation["posted"]:
            agent_config = fetch_agent_config(base_url, campaign_id, api_key)

        stop, reason = should_stop(agent_config)
        log(status_summary(agent_config))
        if stop:
            log(f"Stopping loop because {reason}.")
            return 0

        exit_code = openclaw_turn(args.thinking)
        turns += 1

        agent_config = fetch_agent_config(base_url, campaign_id, api_key)
        reconciliation = reconcile_provider_metering(base_url, campaign_id, api_key, agent_config)
        if reconciliation["posted"]:
            agent_config = fetch_agent_config(base_url, campaign_id, api_key)
        stop, reason = should_stop(agent_config)
        if stop:
            log(f"Stopping loop because {reason}.")
            return exit_code

        if args.once or (args.max_turns and turns >= args.max_turns):
            log("Finished requested number of turns.")
            return exit_code

        if exit_code != 0:
            consecutive_failures += 1
            sleep_for = min(args.interval * max(consecutive_failures, 1), 900)
            log(f"Agent turn failed. Backing off for {sleep_for}s.")
        else:
            consecutive_failures = 0
            sleep_for = args.interval
            log(f"Sleeping for {sleep_for}s before the next turn.")

        time.sleep(sleep_for)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("Stopped by operator.")
        raise SystemExit(130)
