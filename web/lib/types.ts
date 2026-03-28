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
  event_type: "match" | "click" | "conversion";
  channel: string;
  title: string;
  detail: string;
  timestamp: string;
  relative_time: string;
  product_id?: string | null;
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
