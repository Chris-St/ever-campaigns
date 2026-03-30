#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

OPENCLAW_BIN="${OPENCLAW_BIN:-$(command -v openclaw || true)}"

if [[ -z "$OPENCLAW_BIN" ]]; then
  echo "ERROR: openclaw CLI not found in PATH."
  echo "Expected one of:"
  echo "  /opt/homebrew/bin/openclaw"
  echo "  $HOME/.local/bin/openclaw"
  echo "  $HOME/.openclaw/bin/openclaw"
  exit 1
fi

if grep -q '"campaign_id": "PASTE_CAMPAIGN_ID"' config.json || \
   grep -q '"api_key": "PASTE_API_KEY"' config.json || \
   grep -q '/api/campaigns/PASTE_CAMPAIGN_ID/events' config.json; then
  echo "ERROR: Update config.json with real Ever values first."
  echo "Run ./setup.sh to populate it from Ever."
  exit 1
fi

if grep -q "PASTE_REDDIT" config.json; then
  echo "WARNING: Reddit credentials are not configured. The agent can browse but may not be able to post."
fi

if grep -q "PASTE_EMAIL" config.json; then
  echo "WARNING: Email credentials are not configured. The agent cannot send outreach mail yet."
fi

python3 prepare.py

echo "Starting Bia autonomous agent..."
echo "Dashboard: http://localhost:3000/dashboard"
echo "Proposals: http://localhost:3000/proposals"
echo ""

gateway_ready=false
for _ in 1 2 3 4 5; do
  if "$OPENCLAW_BIN" gateway status >/dev/null 2>&1; then
    gateway_ready=true
    break
  fi
  sleep 2
done

if [[ "$gateway_ready" != true ]]; then
  echo "OpenClaw gateway is not running."
  echo ""
  echo "Start it in another terminal with:"
  echo "  $OPENCLAW_BIN gateway run --allow-unconfigured --force"
  echo ""
  echo "Then come back here and run:"
  echo "  bash launch.sh"
  exit 1
fi

if [[ "${1:-}" == "tui" ]]; then
  echo "Opening interactive OpenClaw TUI..."
  "$OPENCLAW_BIN" tui
  exit 0
fi

echo "Running continuous overnight loop..."
echo "Tip: use 'bash launch.sh tui' in another terminal if you want to inspect OpenClaw live."
echo ""

python3 run_loop.py "$@"
