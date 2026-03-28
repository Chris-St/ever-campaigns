from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AuthRequest(BaseModel):
    email: str
    password: str


class CampaignMini(SchemaModel):
    id: str
    merchant_id: str
    merchant_slug: str | None = None
    merchant_name: str
    domain: str
    status: str
    budget_monthly: float
    budget_spent: float


class CurrentUser(SchemaModel):
    id: str
    email: str
    campaigns: list[CampaignMini] = Field(default_factory=list)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


class StructuredProductPayload(SchemaModel):
    id: str | None = None
    source_url: str | None = None
    name: str
    category: str | None = None
    subcategory: str | None = None
    price: float
    currency: str = "USD"
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    status: str = "active"


class StoreScanRequest(BaseModel):
    url: str


class StoreScanResponse(BaseModel):
    merchant_id: str
    merchant_slug: str | None = None
    domain: str
    name: str
    ships_to: list[str]
    products: list[StructuredProductPayload]


class ConfirmProductsRequest(BaseModel):
    products: list[StructuredProductPayload]


class CampaignCreateRequest(BaseModel):
    merchant_id: str
    budget_monthly: float
    auto_optimize: bool = True


class CampaignUpdateRequest(BaseModel):
    budget_monthly: float | None = None
    status: Literal["active", "paused", "pending_payment", "draft"] | None = None
    auto_optimize: bool | None = None


class BillingInvoice(BaseModel):
    id: str
    date: str
    amount: float
    status: str


class BillingSummary(BaseModel):
    mode: str
    plan_name: str
    payment_method: str
    invoices: list[BillingInvoice] = Field(default_factory=list)


class AgentChannelStatus(BaseModel):
    status: str
    label: str
    badge: str
    description: str
    public_url: str | None = None
    preview_url: str | None = None
    global_public_url: str | None = None
    global_preview_url: str | None = None
    feed_url: str | None = None
    quick_test_prompt: str | None = None


class AgentEndpoints(BaseModel):
    merchant_slug: str
    connected_surfaces: str
    summary: str
    mcp: AgentChannelStatus
    acp: AgentChannelStatus
    ucp: AgentChannelStatus


class CampaignOverview(BaseModel):
    id: str
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    domain: str
    status: str
    auto_optimize: bool
    budget_monthly: float
    budget_spent: float
    budget_utilization: float
    projected_monthly_spend: float
    compute_spent: float
    conversions: int
    revenue: float
    return_on_compute: float
    compute_series: list[float] = Field(default_factory=list)
    revenue_series: list[float] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    billing: BillingSummary
    agent_endpoints: AgentEndpoints


class TimeSeriesPoint(BaseModel):
    date: str
    compute_spend: float
    revenue: float
    conversions: int


class ProductPerformanceRow(BaseModel):
    product_id: str
    name: str
    price: float
    currency: str
    image: str | None = None
    matches: int
    clicks: int
    conversions: int
    revenue: float
    return_on_compute: float
    status: Literal["top", "stable", "watch"]


class QueryInsight(BaseModel):
    query_text: str
    agent_source: str | None = None
    score: float
    timestamp: str
    constraint_matches: list[str] = Field(default_factory=list)


class ProductDetailResponse(BaseModel):
    id: str
    merchant_id: str
    source_url: str | None = None
    name: str
    category: str | None = None
    subcategory: str | None = None
    price: float
    currency: str
    description: str | None = None
    attributes: dict[str, Any]
    images: list[str]
    performance: ProductPerformanceRow
    matched_queries: list[QueryInsight] = Field(default_factory=list)


class ActivityEntry(BaseModel):
    id: str
    event_type: Literal["match", "click", "conversion"]
    channel: str = "mcp"
    title: str
    detail: str
    timestamp: str
    relative_time: str
    product_id: str | None = None


class BillingCheckoutRequest(BaseModel):
    campaign_id: str


class BillingCheckoutResponse(BaseModel):
    mode: str
    campaign_id: str
    activated: bool
    message: str
    checkout_url: str | None = None


class ShopifyOrderWebhook(BaseModel):
    campaign_id: str
    product_id: str
    order_value: float
    query_id: str | None = None


class SearchProductsRequest(BaseModel):
    query: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    limit: int = 5
    agent_source: str = "Claude"


class SearchResult(BaseModel):
    product_id: str
    merchant_id: str
    merchant_slug: str | None = None
    merchant_name: str
    name: str
    price: float
    currency: str
    category: str | None = None
    subcategory: str | None = None
    score: float
    reason: str
    images: list[str] = Field(default_factory=list)
    source_url: str | None = None
    redirect_url: str


class SearchProductsResponse(BaseModel):
    query_id: str
    scope: str
    constraints: dict[str, Any]
    results: list[SearchResult]


class CatalogItem(BaseModel):
    product_id: str
    merchant_id: str
    merchant_slug: str | None = None
    name: str
    price: float
    currency: str
    category: str | None = None
    subcategory: str | None = None
    images: list[str] = Field(default_factory=list)
    source_url: str | None = None


class CatalogResponse(BaseModel):
    scope: str
    total: int
    products: list[CatalogItem]


class CompareProductsRequest(BaseModel):
    product_ids: list[str]


class CompareProductsResponse(BaseModel):
    products: list[dict[str, Any]]


class MCPEnvelope(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: str | int | None = None
