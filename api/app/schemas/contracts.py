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
    status: Literal[
        "active",
        "pending_payment",
        "paused_budget",
        "paused_manual",
        "canceled",
        "draft",
    ] | None = None
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
    status: str | None = None
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


class BrandContextProfile(BaseModel):
    positioning: str = ""
    ideal_customer: str = ""
    key_messages: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    objection_handling: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    additional_context: str = ""


class CompetitionLaneConfig(BaseModel):
    id: str
    provider: str
    model: str
    label: str
    available: bool = True
    enabled: bool = True
    role: str = "planner"


class CompetitionConfig(BaseModel):
    enabled: bool = False
    mode: Literal["single_lane", "shadow", "best_of_n"] = "single_lane"
    max_candidates_per_cycle: int = 3
    lanes: list[CompetitionLaneConfig] = Field(default_factory=list)


class ListenerThresholds(BaseModel):
    composite_min: int = 70
    receptivity_min: int = 60


class ListenerSafeguards(BaseModel):
    max_actions_per_day: int = 50
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
    max_actions_per_day: int = 50
    quality_threshold: int = 60
    thresholds: ListenerThresholds = Field(default_factory=ListenerThresholds)
    safeguards: ListenerSafeguards = Field(default_factory=ListenerSafeguards)
    surfaces: list[ListenerSurfaceConfig] = Field(default_factory=list)
    competition: CompetitionConfig = Field(default_factory=CompetitionConfig)


class ListenerStatus(BaseModel):
    campaign_id: str
    status: Literal["running", "stopped", "paused", "budget_exhausted"]
    last_active: str | None = None
    last_polled_at: str | None = None
    actions_today: int = 0
    strategy_updates_today: int = 0
    active_surfaces: list[str] = Field(default_factory=list)
    active_surface_count: int = 0
    signals_today: int
    responses_today: int
    surfaces_active: list[str] = Field(default_factory=list)
    surfaces_active_count: int = 0
    budget_remaining: float
    uptime_hours: float
    signals_detected_today: int
    responses_pending_review: int
    proposals_pending: int = 0
    compute_spent_today: float
    approved_response_count: int
    operating_mode: str = "propose_only"
    manual_execution_required: bool = True
    approval_required: bool = True
    brand_voice_profile: BrandVoiceProfile
    brand_context_profile: BrandContextProfile
    config: ListenerConfig


class ListenerConfigUpdateRequest(BaseModel):
    brand_voice_profile: BrandVoiceProfile | None = None
    brand_context_profile: BrandContextProfile | None = None
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
    actions_reported: int = 0
    strategy_updates: int = 0
    signals_detected: int
    responses_sent: int
    clicks: int
    conversions: int
    revenue: float
    compute_cost: float


class ListenerChannelBreakdown(BaseModel):
    surface: str
    actions: int
    clicks: int
    conversions: int
    revenue: float
    compute_cost: float
    return_on_compute: float


class ListenerStrategyEntry(BaseModel):
    id: str
    description: str
    channels_used: list[str] = Field(default_factory=list)
    total_actions: int = 0
    compute_cost: float = 0.0
    timestamp: str
    relative_time: str


class ListenerModelBreakdown(BaseModel):
    provider: str
    model: str
    label: str
    proposals: int
    approved: int
    executed: int
    conversions: int
    revenue: float
    compute_cost: float
    return_on_compute: float


class ListenerAnalytics(BaseModel):
    period: str
    actions_reported: int = 0
    strategy_updates: int = 0
    signals_detected: int
    responses_sent: int
    responses_pending_review: int
    proposals_generated: int = 0
    proposals_approved: int = 0
    proposals_executed: int = 0
    execution_rate: float = 0.0
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
    channel_breakdown: list[ListenerChannelBreakdown] = Field(default_factory=list)
    model_breakdown: list[ListenerModelBreakdown] = Field(default_factory=list)
    strategy_feed: list[ListenerStrategyEntry] = Field(default_factory=list)
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
    event_type: str
    category: str | None = None
    surface: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_content: str | None = None
    source_author: str | None = None
    source_context: str | None = None
    subreddit_or_channel: str | None = None
    target_audience: str | None = None
    intent_score: AgentIntentScore = Field(default_factory=AgentIntentScore)
    action_taken: str | None = None
    action_type: str | None = None
    response_text: str | None = None
    proposed_response: str | None = None
    rationale: str | None = None
    referral_url: str | None = None
    execution_instructions: str | None = None
    product_id: str | None = None
    tokens_used: int = 0
    compute_cost_usd: float = 0.0
    expected_impact: str | None = None
    channels_used: list[str] = Field(default_factory=list)
    total_actions: int | None = None
    model_provider: str | None = None
    model_name: str | None = None
    competition_score: float | None = None
    timestamp: str


class AgentEventResponse(BaseModel):
    event_id: str | None = None
    proposal_id: str | None = None
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
    key_selling_points: list[str] = Field(default_factory=list)


class AgentConstraintsConfig(BaseModel):
    always_disclose_ai: bool = True
    always_use_referral_links: bool = True
    never_spam: bool = True
    never_disparage_competitors: bool = True
    max_actions_per_day: int


class AgentContextConfig(BaseModel):
    positioning: str = ""
    ideal_customer: str = ""
    key_messages: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    objection_handling: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    additional_context: str = ""
    seeded_context_summary: str = ""
    seeded_context_items: list[dict[str, Any]] = Field(default_factory=list)


class AgentBudgetConfig(BaseModel):
    monthly: float
    spent: float
    remaining: float
    currency: str


class AgentObjectiveConfig(BaseModel):
    primary_goal: str
    optimization_equation: str = "sales > compute_cost"
    budget_limit: float
    operating_principle: str
    tactical_freedom: list[str] = Field(default_factory=list)


class AgentMemoryItem(BaseModel):
    id: str
    kind: str
    title: str
    summary: str
    surface: str | None = None
    action_type: str | None = None
    product_id: str | None = None
    confidence: float = 0.0
    created_at: str
    relative_time: str


class AgentMemoryConfig(BaseModel):
    enabled: bool = True
    summary: str = ""
    winning_patterns: list[str] = Field(default_factory=list)
    caution_patterns: list[str] = Field(default_factory=list)
    operator_feedback: list[str] = Field(default_factory=list)
    recent_items: list[AgentMemoryItem] = Field(default_factory=list)


class AgentReportingConfig(BaseModel):
    events_endpoint: str
    api_key: str


class AgentCompetitionConfig(BaseModel):
    enabled: bool = False
    mode: Literal["single_lane", "shadow", "best_of_n"] = "single_lane"
    lanes: list[CompetitionLaneConfig] = Field(default_factory=list)


class AgentConfigResponse(BaseModel):
    campaign_id: str
    status: str | None = None
    campaign_status: str | None = None
    operating_mode: Literal["propose_only"] = "propose_only"
    manual_execution_required: bool = True
    approval_required: bool = True
    brand: AgentBrandConfig
    products: list[AgentProductConfig] = Field(default_factory=list)
    budget: AgentBudgetConfig
    objective: AgentObjectiveConfig
    memory: AgentMemoryConfig
    reporting: AgentReportingConfig
    constraints: AgentConstraintsConfig
    context: AgentContextConfig
    competition: AgentCompetitionConfig = Field(default_factory=AgentCompetitionConfig)


class ProposalStatsSummary(BaseModel):
    total: int = 0
    pending: int = 0
    approved: int = 0
    executed: int = 0
    rejected: int = 0


class AttributionConfidenceSummary(BaseModel):
    confirmed: int = 0
    estimated: int = 0
    unattributed: int = 0


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
    proposals: ProposalStatsSummary = Field(default_factory=ProposalStatsSummary)
    attribution_confidence: AttributionConfidenceSummary = Field(default_factory=AttributionConfidenceSummary)
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
    event_type: str
    channel: str = "autonomous_agent"
    category: str | None = None
    surface: str | None = None
    title: str
    detail: str
    timestamp: str
    relative_time: str
    product_id: str | None = None
    product_name: str | None = None
    compute_cost: float = 0.0
    expected_impact: str | None = None
    source_url: str | None = None
    proposal_id: str | None = None
    proposal_status: str | None = None
    model_provider: str | None = None
    model_name: str | None = None


class BillingCheckoutRequest(BaseModel):
    campaign_id: str


class BillingCheckoutResponse(BaseModel):
    mode: str
    campaign_id: str
    activated: bool
    message: str
    status: str | None = None
    checkout_url: str | None = None
    checkout_session_id: str | None = None


class ShopifyOrderWebhook(BaseModel):
    campaign_id: str
    product_id: str
    order_value: float
    query_id: str | None = None
    proposal_id: str | None = None


class ProposalRecord(SchemaModel):
    id: str
    campaign_id: str
    product_id: str | None = None
    product_name: str | None = None
    product_image: str | None = None
    product_price: float | None = None
    product_currency: str | None = None
    surface: str | None = None
    source_url: str | None = None
    source_content: str | None = None
    source_author: str | None = None
    source_context: str | None = None
    intent_score: dict[str, Any] = Field(default_factory=dict)
    action_type: str
    proposed_response: str
    rationale: str | None = None
    referral_url: str | None = None
    execution_instructions: str | None = None
    status: str
    approved_at: str | None = None
    rejected_at: str | None = None
    rejection_reason: str | None = None
    executed_at: str | None = None
    execution_notes: str | None = None
    outcome: str | None = None
    outcome_notes: str | None = None
    outcome_recorded_at: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    competition_score: float = 0.0
    tokens_used: int = 0
    compute_cost_usd: float = 0.0
    created_at: str
    relative_time: str
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    attribution_confidence: Literal["confirmed", "estimated", "unattributed"] = "unattributed"


class ProposalRejectRequest(BaseModel):
    reason: str | None = None


class ProposalEditRequest(BaseModel):
    proposed_response: str


class ProposalExecutedRequest(BaseModel):
    notes: str | None = None


class ProposalOutcomeRequest(BaseModel):
    outcome: str
    notes: str | None = None


class ContextItemRecord(SchemaModel):
    id: str
    campaign_id: str
    kind: str
    title: str
    source_name: str | None = None
    mime_type: str | None = None
    content_text: str
    summary: str
    storage_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ContextNoteRequest(BaseModel):
    title: str
    content: str
    kind: Literal["note", "voice_note", "brief"] = "note"


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
