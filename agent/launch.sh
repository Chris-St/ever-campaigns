#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if grep -q "PASTE_" config.json; then
  echo "ERROR: Update config.json with real values first."
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

openclaw
