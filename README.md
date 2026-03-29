# Ever Campaigns

Ever Campaigns is a full-stack agent-first acquisition platform where brands allocate compute budget instead of buying impressions or clicks. The current local build is centered on a first real-money Bia experiment with Return on Compute (RoC) as the main KPI, and includes:

- A premium Next.js landing page and auth flow
- A simplified experiment setup flow that scans a store, defaults to a focused catalog, accepts uploaded/voice context, funds the budget, and launches a propose-only agent
- A live dashboard with spend, proposals, approvals, executions, revenue, conversions, attribution confidence, and RoC
- A dedicated operator queue at `/proposals`
- Product detail and settings screens
- A FastAPI backend with auth, store scanning, campaign analytics, proposal APIs, tracking, Stripe checkout/webhooks, and MCP-style search tools

## Project Structure

- `/web` - Next.js frontend
- `/api` - FastAPI backend

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

## Stripe Test Mode

For the paid experiment flow, set these in `api/.env`:

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
PUBLIC_WEB_URL=http://localhost:3000
PUBLIC_API_URL=http://localhost:8000
```

Forward Stripe webhooks locally:

```bash
stripe listen --forward-to http://localhost:8000/billing/webhooks/stripe
```

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

- Billing now uses Stripe Checkout + webhook activation for the local paid experiment flow.
- The live agent runs in objective-first propose-only mode and can ingest uploaded files plus operator voice/text notes as seeded context.
- With `ANTHROPIC_API_KEY` set, it uses model-driven planning plus memory over live internet observations.
- With both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` set, the runtime turns on first-pass multi-model competition and ranks proposals by expected Return on Compute.
- Manual execution and outcome recording happen in `/proposals`.
- Store scanning tries Shopify's public `/products.json` first, then HTML/JSON-LD fallback, and includes seeded Bia demo products for the initial showcase flow.
- The MCP surface is exposed through `/mcp`, `/mcp/tools`, and dedicated tool routes for search, get, and compare.
- The backend targets Python 3.10+.
