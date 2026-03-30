# Ever Campaigns

Ever Campaigns is a full-stack agent-first acquisition platform where brands allocate compute budget instead of buying impressions or clicks. The current local build is centered on a first real-money Bia experiment with Return on Compute (RoC) as the main KPI, and includes:

- A premium Next.js landing page and auth flow
- A simplified experiment setup flow that scans a store, defaults to a focused catalog, accepts uploaded/voice context, and launches an autonomous OpenClaw agent workflow
- A live dashboard with spend, proposals, approvals, executions, revenue, conversions, attribution confidence, and RoC
- A dedicated operator queue at `/proposals`
- Product detail and settings screens
- A FastAPI backend with auth, store scanning, campaign analytics, proposal APIs, tracking, and MCP-style search tools
- A standalone repo-root `agent/` OpenClaw project that operates independently and reports actions back to Ever over HTTP

## Project Structure

- `/web` - Next.js frontend
- `/api` - FastAPI backend
- `/agent` - standalone OpenClaw project

## Local Run

### 1. Start the API

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/api
python3.10 -m pip install -r requirements.txt
python3.10 -m uvicorn app.main:app --reload
```

### 2. Start the frontend

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/web
cp .env.example .env.local
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8000` by default.

## Self-Funded Local Mode

Local experiments default to self-funded mode. That means:
- Ever meters the campaign budget internally
- your model API accounts pay the underlying provider cost
- Stripe stays disabled unless you explicitly turn it back on

Set these in `api/.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
PUBLIC_WEB_URL=http://localhost:3000
PUBLIC_API_URL=http://localhost:8000
SELF_FUNDED_MODE=true
```

If you want to re-enable Stripe later for external brands:

```bash
SELF_FUNDED_MODE=false
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

## External OpenClaw Agent

The internal `api/app/openclaw_agent.py` loop is now disabled by default. Ever is the scoreboard; the real agent lives in `/agent`.

### 1. Create a campaign in Ever

- Start the API and frontend
- Go through onboarding
- Launch the campaign so Ever provisions the API key and runtime handoff

### 2. Populate the agent config

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/agent
bash setup.sh
```

This will:
- ask for your JWT token and campaign ID
- regenerate the campaign API key
- pull campaign metadata from Ever
- write `agent/config.json` with live events/referral URLs

Then add your Reddit and email credentials manually to `agent/config.json`.

### 3. Launch OpenClaw

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/agent
bash launch.sh
```

`launch.sh` regenerates `CLAUDE.md` from `CLAUDE.template.md` using `prepare.py`, then starts OpenClaw in the `agent/` directory.

### 4. Watch Ever update

- Dashboard: `http://localhost:3000/dashboard`
- Proposals: `http://localhost:3000/proposals`

The external agent reports back to:

- `POST /api/campaigns/{campaign_id}/events`

No new backend agent loop is involved.

## Referral Links And Public Testing

Tracked product links use:

```bash
http://localhost:8000/go/{product_id}?src=agent&cid={campaign_id}
```

That logs the click in Ever and redirects to the real merchant product page.

### Localhost limitation

If a real human clicks a localhost tracking link from another machine, it will not work. For the first live test, use a public tunnel.

### Fastest option: ngrok

```bash
ngrok http 8000
```

Then set `PUBLIC_API_URL` in `api/.env` to the ngrok URL and restart the API. New tracked links will use the public redirect endpoint, so real clicks from Reddit/email/DMs can reach Ever.

## Verification

Backend:

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/api
python3.10 -m pytest -q
```

Frontend:

```bash
cd /Users/christian-stl/Desktop/ever-campaigns/web
npm run lint
npm run build
```

## Notes

- Billing defaults to self-funded local mode.
- The live external agent runs from `/agent`, not from the backend.
- Ever keeps the proposals queue, tracking redirects, attribution, and RoC dashboard intact.
- Manual execution and outcome recording happen in `/proposals`.
- Store scanning tries Shopify's public `/products.json` first, then HTML/JSON-LD fallback, and includes seeded Bia demo products for the initial showcase flow.
- The MCP surface is exposed through `/mcp`, `/mcp/tools`, and dedicated tool routes for search, get, and compare.
- The backend targets Python 3.10+.
