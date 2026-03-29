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
    openclaw: dict[str, Any] = Field(default_factory=dict)


class BrandVoiceProfile(BaseModel):
    brand_name: str
    story: str
    values: list[str] = Field(default_factory=list)
    tone: str
    target_customer: str | None = None
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    sample_responses: dict[str, str] = Field(default_factory=dict)


class ListenerThresholds(BaseModel):
    composite_min: int = 70
    receptivity_min: int = 60


class ListenerSafeguards(BaseModel):
    max_responses_per_surface_per_day: int = 10
    max_responses_per_day: int = 50
    max_thread_replies: int = 2
    minimum_minutes_between_surface_responses: int = 5
    minimum_post_age_minutes: int = 10
    never_respond_to_same_author_within_hours: int = 24
    one_response_per_author_per_day: bool = True
    always_disclose_ai: bool = True
    pause_if_downvote_rate_exceeds: float = 0.2
    auto_post_confidence_threshold: int = 70


class ListenerSurfaceConfig(BaseModel):
    type: Literal["reddit", "twitter"]
    enabled: bool = True
    subreddits: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    poll_interval_seconds: int = 180


class ListenerConfig(BaseModel):
    listener_mode: Literal["simulation", "live"] = "simulation"
    aggressiveness: Literal["conservative", "balanced", "aggressive"] = "balanced"
    review_mode: Literal["manual", "auto"] = "manual"
    auto_post_after_approvals: int = 50
    thresholds: ListenerThresholds = Field(default_factory=ListenerThresholds)
    safeguards: ListenerSafeguards = Field(default_factory=ListenerSafeguards)
    surfaces: list[ListenerSurfaceConfig] = Field(default_factory=list)


class ListenerStatus(BaseModel):
    campaign_id: str
    status: Literal["running", "stopped", "paused", "budget_exhausted"]
    last_active: str | None = None
    last_polled_at: str | None = None
    signals_today: int
    responses_today: int
    surfaces_active: list[str] = Field(default_factory=list)
    surfaces_active_count: int = 0
    budget_remaining: float
    uptime_hours: float
    signals_detected_today: int
    responses_pending_review: int
    compute_spent_today: float
    approved_response_count: int
    brand_voice_profile: BrandVoiceProfile
    config: ListenerConfig


class ListenerConfigUpdateRequest(BaseModel):
    brand_voice_profile: BrandVoiceProfile | None = None
    config: ListenerConfig | None = None


class ReviewQueueItem(BaseModel):
    response_id: str
    signal_id: str
    surface: str
    subreddit_or_channel: str | None = None
    content_text: str
    context_text: str | None = None
    content_url: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    intent_score: dict[str, Any] = Field(default_factory=dict)
    response_text: str
    referral_url: str | None = None
    confidence: float
    needs_review: bool
    review_status: str
    created_at: str
    relative_time: str


class ReviewResponseEditRequest(BaseModel):
    response_text: str


class ListenerTopSurface(BaseModel):
    surface: str
    subreddit: str | None = None
    query: str | None = None
    subreddit_or_channel: str | None = None
    responses: int = 0
    signals_detected: int
    responses_sent: int
    clicks: int
    conversions: int
    revenue: float
    compute_cost: float
    roc: float


class ListenerTopProduct(BaseModel):
    product_id: str | None = None
    name: str | None = None
    product_name: str | None = None
    surface: str | None = None
    responses: int = 0
    responses_sent: int
    clicks: int
    conversions: int
    revenue: float
    compute_cost: float
    roc: float


class ListenerCountBreakdown(BaseModel):
    label: str
    count: int


class ListenerAnalyticsPoint(BaseModel):
    date: str
    signals_detected: int
    responses_sent: int
    clicks: int
    conversions: int
    revenue: float
    compute_cost: float


class ListenerAnalytics(BaseModel):
    period: str
    signals_detected: int
    responses_sent: int
    responses_pending_review: int
    approval_rate: float
    response_rate: float
    clicks: int
    click_through_rate: float
    conversions: int
    conversion_rate: float
    revenue: float
    compute_cost: float
    return_on_compute: float
    top_surfaces: list[ListenerTopSurface] = Field(default_factory=list)
    top_products: list[ListenerTopProduct] = Field(default_factory=list)
    top_subreddits: list[ListenerCountBreakdown] = Field(default_factory=list)
    intent_score_distribution: list[ListenerCountBreakdown] = Field(default_factory=list)
    daily: list[ListenerAnalyticsPoint] = Field(default_factory=list)
    daily_series: list[ListenerAnalyticsPoint] = Field(default_factory=list)


class CampaignAgentKeyResponse(BaseModel):
    api_key: str
    api_key_preview: str


class AgentIntentScore(BaseModel):
    relevance: float = 0
    intent: float = 0
    fit: float = 0
    receptivity: float = 0
    composite: float = 0


class AgentEventRequest(BaseModel):
    event_type: Literal[
        "intent_detected",
        "response_posted",
        "response_skipped",
        "response_pending_review",
        "dm_sent",
        "email_sent",
        "skip",
    ]
    surface: Literal["reddit", "twitter", "hackernews", "forum", "other"]
    source_url: str | None = None
    source_content: str
    source_author: str | None = None
    source_context: str | None = None
    subreddit_or_channel: str | None = None
    intent_score: AgentIntentScore = Field(default_factory=AgentIntentScore)
    action_taken: Literal["reply", "dm", "email", "skip"]
    response_text: str | None = None
    referral_url: str | None = None
    product_id: str | None = None
    tokens_used: int = 0
    compute_cost_usd: float = 0.0
    timestamp: str


class AgentEventResponse(BaseModel):
    event_id: str
    status: str
    budget_remaining: float
    budget_exhausted: bool


class AgentBrandConfig(BaseModel):
    name: str
    domain: str
    voice: str
    story: str | None = None
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    disclosure: str


class AgentProductConfig(BaseModel):
    id: str
    name: str
    price: float
    currency: str
    description: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    material: str | None = None
    activities: list[str] = Field(default_factory=list)
    url: str | None = None
    referral_base: str


class AgentSurfaceRuleConfig(BaseModel):
    enabled: bool = False
    subreddits: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)


class AgentRulesConfig(BaseModel):
    intent_threshold: int
    max_responses_per_surface_per_day: int
    max_responses_per_subreddit_per_day: int
    max_responses_per_day: int
    min_minutes_between_responses_same_surface: int
    never_respond_to_same_author_within_hours: int
    never_respond_to_posts_younger_than_minutes: int
    max_responses_per_thread: int
    always_disclose: bool = True
    pause_if_downvote_rate_exceeds: float
    review_mode: bool
    auto_post_confidence_threshold: int


class AgentBudgetConfig(BaseModel):
    monthly: float
    spent: float
    remaining: float
    currency: str


class AgentReportingConfig(BaseModel):
    events_endpoint: str
    api_key: str


class AgentConfigResponse(BaseModel):
    campaign_id: str
    status: str | None = None
    campaign_status: str | None = None
    brand: AgentBrandConfig
    products: list[AgentProductConfig] = Field(default_factory=list)
    surfaces: dict[str, AgentSurfaceRuleConfig] = Field(default_factory=dict)
    rules: AgentRulesConfig
    budget: AgentBudgetConfig
    reporting: AgentReportingConfig


class OpenClawSkillBundleResponse(BaseModel):
    campaign_id: str
    brand_name: str
    file_name: str = "SKILL.md"
    config_file_name: str = "config.json"
    skill_markdown: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class OpenClawConfigResponse(BaseModel):
    campaign_id: str
    config_json: dict[str, Any] = Field(default_factory=dict)


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
    event_type: Literal["match", "click", "conversion", "response"]
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
