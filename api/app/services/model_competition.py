from __future__ import annotations

from typing import Any

from app.core.config import settings


def lane_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def lane_label(provider: str, model: str) -> str:
    if provider == "anthropic":
        return f"Claude ({model})"
    if provider == "openai":
        return f"OpenAI ({model})"
    return "Heuristic baseline"


def available_model_lanes() -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = [
        {
            "id": lane_key("heuristic", "objective-baseline"),
            "provider": "heuristic",
            "model": "objective-baseline",
            "label": "Heuristic baseline",
            "available": True,
            "enabled": True,
            "role": "fallback",
        }
    ]
    if settings.anthropic_api_key:
        lanes.append(
            {
                "id": lane_key("anthropic", settings.anthropic_model),
                "provider": "anthropic",
                "model": settings.anthropic_model,
                "label": lane_label("anthropic", settings.anthropic_model),
                "available": True,
                "enabled": True,
                "role": "planner",
            }
        )
    if settings.openai_api_key:
        lanes.append(
            {
                "id": lane_key("openai", settings.openai_model),
                "provider": "openai",
                "model": settings.openai_model,
                "label": lane_label("openai", settings.openai_model),
                "available": True,
                "enabled": True,
                "role": "challenger",
            }
        )
    return lanes


def default_competition_config() -> dict[str, Any]:
    lanes = available_model_lanes()
    enabled = len([lane for lane in lanes if lane["provider"] != "heuristic"]) >= 1
    mode = "best_of_n" if enabled and len(lanes) > 1 else "single_lane"
    return {
        "enabled": enabled,
        "mode": mode,
        "max_candidates_per_cycle": 3,
        "lanes": lanes,
    }


def normalize_competition_config(config: dict[str, Any] | None) -> dict[str, Any]:
    defaults = default_competition_config()
    config = config or {}
    configured_lanes = {
        str(item.get("id") or lane_key(str(item.get("provider", "")), str(item.get("model", "")))): item
        for item in config.get("lanes", [])
        if isinstance(item, dict)
    }
    normalized_lanes: list[dict[str, Any]] = []
    for lane in available_model_lanes():
        override = configured_lanes.get(lane["id"], {})
        normalized_lanes.append(
            {
                **lane,
                "enabled": bool(override.get("enabled", lane["enabled"])),
                "role": str(override.get("role", lane["role"])),
            }
        )

    normalized = {
        "enabled": bool(config.get("enabled", defaults["enabled"])),
        "mode": str(config.get("mode", defaults["mode"])),
        "max_candidates_per_cycle": int(
            config.get("max_candidates_per_cycle", defaults["max_candidates_per_cycle"]) or 3
        ),
        "lanes": normalized_lanes,
    }

    enabled_non_heuristic = [
        lane
        for lane in normalized_lanes
        if lane["provider"] != "heuristic" and lane["enabled"] and lane["available"]
    ]
    if not enabled_non_heuristic:
        normalized["enabled"] = False
        normalized["mode"] = "single_lane"
    elif normalized["mode"] not in {"single_lane", "shadow", "best_of_n"}:
        normalized["mode"] = defaults["mode"]
    return normalized


def enabled_competition_lanes(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    competition = normalize_competition_config(config)
    lanes = [lane for lane in competition["lanes"] if lane["enabled"] and lane["available"]]
    if not competition["enabled"]:
        for lane in lanes:
            if lane["provider"] != "heuristic":
                return [lane]
        return lanes[:1]
    return lanes
