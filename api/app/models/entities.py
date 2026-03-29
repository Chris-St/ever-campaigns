from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="user")
    merchants: Mapped[list["Merchant"]] = relationship(back_populates="owner_user")


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    domain: Mapped[str] = mapped_column(String, unique=True, index=True)
    merchant_slug: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str] = mapped_column(String, default="shopify")
    ships_to: Mapped[list[str]] = mapped_column(JSON, default=list)
    trust_score: Mapped[float] = mapped_column(Float, default=50.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_crawled: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")

    owner_user: Mapped[User | None] = relationship(back_populates="merchants")
    products: Mapped[list["Product"]] = relationship(back_populates="merchant")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="merchant")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="USD")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    images: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_crawled: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String, default="active")

    merchant: Mapped[Merchant] = relationship(back_populates="products")
    matches: Mapped[list["Match"]] = relationship(back_populates="product")
    clicks: Mapped[list["Click"]] = relationship(back_populates="product")
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="product")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    budget_monthly: Mapped[float] = mapped_column(Float)
    budget_spent: Mapped[float] = mapped_column(Float, default=0.0)
    auto_optimize: Mapped[bool] = mapped_column(Boolean, default=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    listener_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    listener_api_key_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    listener_api_key_last_four: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_voice_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    brand_context_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    listener_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    listener_status: Mapped[str] = mapped_column(String, default="stopped")
    listener_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    listener_last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_response_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending_payment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="campaigns")
    user: Mapped[User] = relationship(back_populates="campaigns")
    matches: Mapped[list["Match"]] = relationship(back_populates="campaign")
    clicks: Mapped[list["Click"]] = relationship(back_populates="campaign")
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="campaign")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="campaign")
    intent_signals: Mapped[list["IntentSignal"]] = relationship(back_populates="campaign")
    agent_responses: Mapped[list["AgentResponse"]] = relationship(back_populates="campaign")
    agent_events: Mapped[list["AgentEvent"]] = relationship(back_populates="campaign")


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    agent_source: Mapped[str | None] = mapped_column(String, nullable=True)
    channel: Mapped[str] = mapped_column(String, default="mcp")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    matches: Mapped[list["Match"]] = relationship(back_populates="query")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id"),
        index=True,
        nullable=True,
    )
    score: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer)
    compute_cost: Mapped[float] = mapped_column(Float, default=0.0)
    channel: Mapped[str] = mapped_column(String, default="mcp")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="matches")
    product: Mapped[Product] = relationship(back_populates="matches")
    campaign: Mapped[Campaign | None] = relationship(back_populates="matches")
    clicks: Mapped[list["Click"]] = relationship(back_populates="match")


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("matches.id"), index=True, nullable=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id"),
        index=True,
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String, default="mcp")
    source: Mapped[str] = mapped_column(String, default="mcp")
    surface: Mapped[str | None] = mapped_column(String, nullable=True)
    response_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_responses.id"),
        index=True,
        nullable=True,
    )
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposals.id"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    match: Mapped[Match | None] = relationship(back_populates="clicks")
    product: Mapped[Product] = relationship(back_populates="clicks")
    campaign: Mapped[Campaign | None] = relationship(back_populates="clicks")
    response: Mapped[AgentResponse | None] = relationship(back_populates="clicks")
    proposal: Mapped[Proposal | None] = relationship(back_populates="clicks")
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="click")


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    click_id: Mapped[str | None] = mapped_column(ForeignKey("clicks.id"), index=True, nullable=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id"),
        index=True,
        nullable=True,
    )
    order_value: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String, default="mcp")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    click: Mapped[Click | None] = relationship(back_populates="conversions")
    product: Mapped[Product] = relationship(back_populates="conversions")
    campaign: Mapped[Campaign | None] = relationship(back_populates="conversions")


class IntentSignal(Base):
    __tablename__ = "intent_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    surface: Mapped[str] = mapped_column(String)
    platform_content_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content_text: Mapped[str] = mapped_column(Text)
    content_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    subreddit_or_channel: Mapped[str | None] = mapped_column(String, nullable=True)
    intent_score: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    should_respond: Mapped[bool] = mapped_column(Boolean, default=False)
    response_type: Mapped[str] = mapped_column(String, default="skip")
    scoring_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    scoring_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="intent_signals")
    product: Mapped[Product | None] = relationship()
    responses: Mapped[list["AgentResponse"]] = relationship(back_populates="signal")


class AgentResponse(Base):
    __tablename__ = "agent_responses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    signal_id: Mapped[str] = mapped_column(ForeignKey("intent_signals.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    surface: Mapped[str] = mapped_column(String, default="reddit")
    response_text: Mapped[str] = mapped_column(Text)
    referral_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_placement: Mapped[str] = mapped_column(String, default="inline")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    platform_appropriate: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String, default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted: Mapped[bool] = mapped_column(Boolean, default=False)
    posted_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generation_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    generation_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    signal: Mapped[IntentSignal] = relationship(back_populates="responses")
    campaign: Mapped[Campaign] = relationship(back_populates="agent_responses")
    product: Mapped[Product | None] = relationship()
    clicks: Mapped[list[Click]] = relationship(back_populates="response")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    surface: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_author: Mapped[str | None] = mapped_column(String, nullable=True)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_score: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action_type: Mapped[str] = mapped_column(String, default="other")
    proposed_response: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="proposed")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    compute_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="proposals")
    product: Mapped[Product | None] = relationship()
    clicks: Mapped[list[Click]] = relationship(back_populates="proposal")


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    event_type: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    surface: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_author: Mapped[str | None] = mapped_column(String, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    referral_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    compute_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    expected_impact: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="agent_events")
    product: Mapped[Product | None] = relationship()
