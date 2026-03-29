export interface CampaignMini {
  id: string;
  merchant_id: string;
  merchant_slug?: string | null;
  merchant_name: string;
  domain: string;
  status: string;
  budget_monthly: number;
  budget_spent: number;
}

export interface CurrentUser {
  id: string;
  email: string;
  campaigns: CampaignMini[];
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: CurrentUser;
}

export interface StructuredProduct {
  id?: string;
  source_url?: string | null;
  name: string;
  category?: string | null;
  subcategory?: string | null;
  price: number;
  currency: string;
  description?: string | null;
  attributes: Record<string, unknown>;
  images: string[];
  status: string;
}

export interface StoreScanResponse {
  merchant_id: string;
  merchant_slug?: string | null;
  domain: string;
  name: string;
  ships_to: string[];
  products: StructuredProduct[];
}

export interface BillingInvoice {
  id: string;
  date: string;
  amount: number;
  status: string;
}

export interface BillingSummary {
  mode: string;
  plan_name: string;
  payment_method: string;
  invoices: BillingInvoice[];
}

export interface AgentChannelStatus {
  status: string;
  label: string;
  badge: string;
  description: string;
  public_url?: string | null;
  preview_url?: string | null;
  global_public_url?: string | null;
  global_preview_url?: string | null;
  feed_url?: string | null;
  quick_test_prompt?: string | null;
}

export interface AgentEndpoints {
  merchant_slug: string;
  connected_surfaces: string;
  summary: string;
  mcp: AgentChannelStatus;
  acp: AgentChannelStatus;
  ucp: AgentChannelStatus;
  openclaw: OpenClawEndpoint;
}

export interface OpenClawEndpoint {
  status: string;
  label: string;
  badge: string;
  description: string;
  config_url: string;
  events_url: string;
  skill_download_url?: string | null;
  config_download_url?: string | null;
  bundle_download_url?: string | null;
  api_key?: string | null;
  api_key_preview?: string | null;
  skill_path?: string | null;
  config_path?: string | null;
  launch_command?: string | null;
}

export interface BrandVoiceProfile {
  brand_name: string;
  story: string;
  values: string[];
  tone: string;
  target_customer?: string | null;
  dos: string[];
  donts: string[];
  sample_responses: Record<string, string>;
}

export interface ListenerThresholds {
  composite_min: number;
  receptivity_min: number;
}

export interface ListenerSafeguards {
  max_actions_per_day: number;
  max_responses_per_surface_per_day: number;
  max_responses_per_day: number;
  max_thread_replies: number;
  minimum_minutes_between_surface_responses: number;
  minimum_post_age_minutes: number;
  never_respond_to_same_author_within_hours: number;
  one_response_per_author_per_day: boolean;
  always_disclose_ai: boolean;
  pause_if_downvote_rate_exceeds: number;
  auto_post_confidence_threshold: number;
}

export interface ListenerSurfaceConfig {
  type: "reddit" | "twitter";
  enabled: boolean;
  subreddits: string[];
  keywords: string[];
  search_queries: string[];
  poll_interval_seconds: number;
}

export interface ListenerConfig {
  listener_mode: "simulation" | "live";
  aggressiveness: "conservative" | "balanced" | "aggressive";
  review_mode: "manual" | "auto";
  auto_post_after_approvals: number;
  max_actions_per_day: number;
  quality_threshold: number;
  thresholds: ListenerThresholds;
  safeguards: ListenerSafeguards;
  surfaces: ListenerSurfaceConfig[];
}

export interface ListenerStatus {
  campaign_id: string;
  status: "running" | "stopped" | "paused" | "budget_exhausted";
  last_active?: string | null;
  last_polled_at?: string | null;
  actions_today: number;
  strategy_updates_today: number;
  active_surfaces: string[];
  active_surface_count: number;
  signals_today: number;
  responses_today: number;
  surfaces_active: string[];
  surfaces_active_count: number;
  budget_remaining: number;
  uptime_hours: number;
  signals_detected_today: number;
  responses_pending_review: number;
  compute_spent_today: number;
  approved_response_count: number;
  brand_voice_profile: BrandVoiceProfile;
  config: ListenerConfig;
}

export interface ReviewQueueItem {
  response_id: string;
  signal_id: string;
  surface: string;
  subreddit_or_channel?: string | null;
  content_text: string;
  context_text?: string | null;
  content_url?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  intent_score: Record<string, number | string | boolean>;
  response_text: string;
  referral_url?: string | null;
  confidence: number;
  needs_review: boolean;
  review_status: string;
  created_at: string;
  relative_time: string;
}

export interface ListenerTopSurface {
  surface: string;
  subreddit?: string | null;
  query?: string | null;
  subreddit_or_channel?: string | null;
  responses: number;
  signals_detected: number;
  responses_sent: number;
  clicks: number;
  conversions: number;
  revenue: number;
  compute_cost: number;
  roc: number;
}

export interface ListenerTopProduct {
  product_id?: string | null;
  name?: string | null;
  product_name?: string | null;
  surface?: string | null;
  responses: number;
  responses_sent: number;
  clicks: number;
  conversions: number;
  revenue: number;
  compute_cost: number;
  roc: number;
}

export interface ListenerCountBreakdown {
  label: string;
  count: number;
}

export interface ListenerAnalyticsPoint {
  date: string;
  actions_reported: number;
  strategy_updates: number;
  signals_detected: number;
  responses_sent: number;
  clicks: number;
  conversions: number;
  revenue: number;
  compute_cost: number;
}

export interface ListenerChannelBreakdown {
  surface: string;
  actions: number;
  clicks: number;
  conversions: number;
  revenue: number;
  compute_cost: number;
  return_on_compute: number;
}

export interface ListenerStrategyEntry {
  id: string;
  description: string;
  channels_used: string[];
  total_actions: number;
  compute_cost: number;
  timestamp: string;
  relative_time: string;
}

export interface ListenerAnalytics {
  period: string;
  actions_reported: number;
  strategy_updates: number;
  signals_detected: number;
  responses_sent: number;
  responses_pending_review: number;
  approval_rate: number;
  response_rate: number;
  clicks: number;
  click_through_rate: number;
  conversions: number;
  conversion_rate: number;
  revenue: number;
  compute_cost: number;
  return_on_compute: number;
  top_surfaces: ListenerTopSurface[];
  top_products: ListenerTopProduct[];
  top_subreddits: ListenerCountBreakdown[];
  intent_score_distribution: ListenerCountBreakdown[];
  channel_breakdown: ListenerChannelBreakdown[];
  strategy_feed: ListenerStrategyEntry[];
  daily: ListenerAnalyticsPoint[];
  daily_series: ListenerAnalyticsPoint[];
}

export interface CampaignOverview {
  id: string;
  merchant_id: string;
  merchant_slug: string;
  merchant_name: string;
  domain: string;
  status: string;
  auto_optimize: boolean;
  budget_monthly: number;
  budget_spent: number;
  budget_utilization: number;
  projected_monthly_spend: number;
  compute_spent: number;
  conversions: number;
  revenue: number;
  return_on_compute: number;
  compute_series: number[];
  revenue_series: number[];
  alerts: string[];
  billing: BillingSummary;
  agent_endpoints: AgentEndpoints;
}

export interface TimeSeriesPoint {
  date: string;
  compute_spend: number;
  revenue: number;
  conversions: number;
}

export interface ProductPerformanceRow {
  product_id: string;
  name: string;
  price: number;
  currency: string;
  image?: string | null;
  matches: number;
  clicks: number;
  conversions: number;
  revenue: number;
  return_on_compute: number;
  status: "top" | "stable" | "watch";
}

export interface ActivityEntry {
  id: string;
  event_type: string;
  channel: string;
  category?: string | null;
  surface?: string | null;
  title: string;
  detail: string;
  timestamp: string;
  relative_time: string;
  product_id?: string | null;
  product_name?: string | null;
  compute_cost?: number;
  expected_impact?: string | null;
  source_url?: string | null;
}

export interface CampaignAgentKeyResponse {
  api_key: string;
  api_key_preview: string;
}

export interface QueryInsight {
  query_text: string;
  agent_source?: string | null;
  score: number;
  timestamp: string;
  constraint_matches: string[];
}

export interface ProductDetail {
  id: string;
  merchant_id: string;
  source_url?: string | null;
  name: string;
  category?: string | null;
  subcategory?: string | null;
  price: number;
  currency: string;
  description?: string | null;
  attributes: Record<string, unknown>;
  images: string[];
  performance: ProductPerformanceRow;
  matched_queries: QueryInsight[];
}

export interface BillingCheckoutResponse {
  mode: string;
  campaign_id: string;
  activated: boolean;
  message: string;
  checkout_url?: string | null;
}
