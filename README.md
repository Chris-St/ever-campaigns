# Ever Campaigns

Ever Campaigns is a full-stack v1 demo of an agent-first acquisition platform where brands allocate compute budget instead of buying impressions or clicks. The product is centered around Return on Compute (RoC) and includes:

- A premium Next.js landing page and auth flow
- A five-step onboarding flow that scans a store, structures products, sets budget, and launches a campaign
- A live dashboard with spend, revenue, conversions, RoC, product performance, and an activity feed
- Product detail and settings screens
- A FastAPI backend with auth, store scanning, campaign analytics, tracking, billing stubs, and MCP-style search tools

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

- Billing is implemented in demo mode through `/billing/create-checkout`, with an API shape ready to replace with Stripe.
- Store scanning tries Shopify's public `/products.json` first, then HTML/JSON-LD fallback, and includes seeded Bia demo products for the initial showcase flow.
- The MCP surface is exposed through `/mcp`, `/mcp/tools`, and dedicated tool routes for search, get, and compare.
- The backend targets Python 3.10+.
