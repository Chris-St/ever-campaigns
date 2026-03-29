from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_runtime import router as agent_runtime_router
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.campaigns import router as campaigns_router
from app.api.context import router as context_router
from app.api.feeds import router as feeds_router
from app.api.listener import agent_router as listener_agent_router
from app.api.listener import router as listener_router
from app.api.mcp import router as mcp_router
from app.api.onboarding import router as onboarding_router
from app.api.proposals import router as proposals_router
from app.api.products import router as products_router
from app.api.tracking import router as tracking_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Agent-first acquisition infrastructure centered on Return on Compute.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Ever Campaigns API"}


app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(campaigns_router)
app.include_router(context_router)
app.include_router(proposals_router)
app.include_router(products_router)
app.include_router(billing_router)
app.include_router(tracking_router)
app.include_router(feeds_router)
app.include_router(mcp_router)
app.include_router(listener_router)
app.include_router(listener_agent_router)
app.include_router(agent_runtime_router)
