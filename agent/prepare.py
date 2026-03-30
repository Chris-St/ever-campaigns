from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
TEMPLATE_PATH = ROOT / "CLAUDE.template.md"
OUTPUT_PATH = ROOT / "CLAUDE.md"


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    prompt = TEMPLATE_PATH.read_text(encoding="utf-8")

    referral_urls = config.get("referral_urls", {})
    replacements = {
        "{EVER_EVENTS_URL}": config["ever_api"]["events_endpoint"],
        "{EVER_API_KEY}": config["ever_api"]["api_key"],
        "{REFERRAL_URL_THONG}": referral_urls.get("high_movement_thong", ""),
        "{REFERRAL_URL_SUPERSOFT}": referral_urls.get("supersoft_thong", ""),
        "{REFERRAL_URL_SHORTS}": referral_urls.get("recovery_shorts", ""),
        "{REFERRAL_URL_TEE}": referral_urls.get("the_recovery_t", ""),
    }

    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    OUTPUT_PATH.write_text(prompt, encoding="utf-8")

    print("Prepared CLAUDE.md with live config values.")
    print(f"Events endpoint: {config['ever_api']['events_endpoint']}")
    print(f"Campaign ID: {config['ever_api']['campaign_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
