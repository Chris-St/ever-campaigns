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
    status: Mapped[str] = mapped_column(String, default="pending_payment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="campaigns")
    user: Mapped[User] = relationship(back_populates="campaigns")
    matches: Mapped[list["Match"]] = relationship(back_populates="campaign")
    clicks: Mapped[list["Click"]] = relationship(back_populates="campaign")
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="campaign")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    match: Mapped[Match | None] = relationship(back_populates="clicks")
    product: Mapped[Product] = relationship(back_populates="clicks")
    campaign: Mapped[Campaign | None] = relationship(back_populates="clicks")
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
