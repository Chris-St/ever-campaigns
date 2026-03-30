#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

EVER_BASE="${EVER_BASE:-http://localhost:8000}"

echo "Enter your JWT token (from login):"
read -r TOKEN

echo "Enter your campaign ID (from dashboard):"
read -r CAMPAIGN_ID

CAMPAIGN_JSON=$(curl -fsS -H "Authorization: Bearer $TOKEN" \
  "$EVER_BASE/campaigns/$CAMPAIGN_ID")

API_KEY_JSON=$(curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  "$EVER_BASE/campaigns/$CAMPAIGN_ID/agent-key/regenerate")

PRODUCTS_JSON=$(curl -fsS -H "Authorization: Bearer $TOKEN" \
  "$EVER_BASE/campaigns/$CAMPAIGN_ID/products")

export CAMPAIGN_JSON API_KEY_JSON PRODUCTS_JSON EVER_BASE CAMPAIGN_ID

python3 <<'PY'
import json
import os
from pathlib import Path

config_path = Path("config.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
campaign = json.loads(os.environ["CAMPAIGN_JSON"])
api_key_payload = json.loads(os.environ["API_KEY_JSON"])
products = json.loads(os.environ["PRODUCTS_JSON"])

def product_key(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace("&", "and")
        .replace("-", "_")
        .replace(" ", "_")
    )

referral_urls = {
    product_key(item["name"]): (
        f"{os.environ['EVER_BASE']}/go/{item['product_id']}?src=agent&cid={os.environ['CAMPAIGN_ID']}"
    )
    for item in products
}

config["ever_api"] = {
    "base_url": os.environ["EVER_BASE"],
    "campaign_id": os.environ["CAMPAIGN_ID"],
    "api_key": api_key_payload["api_key"],
    "events_endpoint": f"{os.environ['EVER_BASE']}/api/campaigns/{os.environ['CAMPAIGN_ID']}/events",
}
config["referral_urls"] = {**config.get("referral_urls", {}), **referral_urls}

config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

print("")
print(f"Campaign: {campaign['merchant_name']} ({campaign['id']})")
print(f"Budget: ${campaign['budget_monthly']:.2f}")
print(f"API key: {api_key_payload['api_key']}")
print("Updated agent/config.json with live Ever values.")
PY

echo ""
echo "Next:"
echo "1. Add your Reddit and email credentials to agent/config.json"
echo "2. Run: bash launch.sh"
