"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { CampaignChart } from "@/components/campaign-chart";
import { DashboardMetricCard } from "@/components/dashboard-metric-card";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import {
  formatCurrency,
  formatMultiplier,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  ActivityEntry,
  CampaignAgentKeyResponse,
  CampaignOverview,
  ListenerAnalytics,
  ListenerStatus,
  ProductPerformanceRow,
  TimeSeriesPoint,
} from "@/lib/types";

type Period = "7d" | "30d" | "90d" | "all";
type SortKey =
  | "name"
  | "price"
  | "matches"
  | "clicks"
  | "conversions"
  | "revenue"
  | "return_on_compute";

export function DashboardClient() {
  const router = useRouter();
  const { token, user, loading } = useAuth();
  const [campaignId, setCampaignIdState] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("30d");
  const [eventFilter, setEventFilter] = useState<"all" | "match" | "click" | "conversion" | "response">(
    "all",
  );
  const [sortKey, setSortKey] = useState<SortKey>("revenue");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [overview, setOverview] = useState<CampaignOverview | null>(null);
  const [metrics, setMetrics] = useState<TimeSeriesPoint[]>([]);
  const [products, setProducts] = useState<ProductPerformanceRow[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [listenerAnalytics, setListenerAnalytics] = useState<ListenerAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRegeneratingKey, setIsRegeneratingKey] = useState(false);
  const [endpointsOpen, setEndpointsOpen] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
      return;
    }
    if (!loading && token && user) {
      const storedCampaignId = getActiveCampaignId();
      const fallbackCampaignId = user.campaigns[0]?.id ?? null;
      const nextCampaignId =
        user.campaigns.find((campaign) => campaign.id === storedCampaignId)?.id ??
        fallbackCampaignId;

      if (!nextCampaignId) {
        router.replace("/onboarding");
        return;
      }

      setActiveCampaignId(nextCampaignId);
      setCampaignIdState(nextCampaignId);
    }
  }, [loading, router, token, user]);

  useEffect(() => {
    if (!token || !campaignId) {
      return;
    }

    let cancelled = false;
    async function loadDashboardData() {
      setIsRefreshing(true);
      try {
        const [nextOverview, nextMetrics, nextProducts, nextActivity, nextListenerStatus, nextListenerAnalytics] =
          await Promise.all([
          apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, {
            method: "GET",
            token,
          }),
          apiRequest<TimeSeriesPoint[]>(`/campaigns/${campaignId}/metrics?period=${period}`, {
            method: "GET",
            token,
          }),
          apiRequest<ProductPerformanceRow[]>(`/campaigns/${campaignId}/products`, {
            method: "GET",
            token,
          }),
          apiRequest<ActivityEntry[]>(
            `/campaigns/${campaignId}/activity?limit=24&event_type=${eventFilter}`,
            {
              method: "GET",
              token,
            },
          ),
          apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
            method: "GET",
            token,
          }),
          apiRequest<ListenerAnalytics>(
            `/campaigns/${campaignId}/listener/analytics?period=${period}`,
            {
              method: "GET",
              token,
            },
          ),
        ]);

        if (cancelled) {
          return;
        }

        setOverview(nextOverview);
        setMetrics(nextMetrics);
        setProducts(nextProducts);
        setActivity(nextActivity);
        setListenerStatus(nextListenerStatus);
        setListenerAnalytics(nextListenerAnalytics);
        setError(null);
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : "Unable to load dashboard data.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsRefreshing(false);
        }
      }
    }

    void loadDashboardData();
    const interval = window.setInterval(() => {
      void loadDashboardData();
    }, 20_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [campaignId, eventFilter, period, token]);

  if (loading || !token || !campaignId || !overview) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        Loading dashboard...
      </div>
    );
  }

  const conversionSparkline = metrics.slice(-14).map((point) => point.conversions);
  const rocSparkline = metrics.slice(-14).map((point) =>
    point.compute_spend > 0 ? point.revenue / point.compute_spend : 0,
  );
  const listenerSignalSparkline =
    listenerAnalytics?.daily.slice(-14).map((point) => point.signals_detected) ?? [];
  const listenerResponseSparkline =
    listenerAnalytics?.daily.slice(-14).map((point) => point.responses_sent) ?? [];
  const listenerCtrSparkline =
    listenerAnalytics?.daily.slice(-14).map((point) =>
      point.responses_sent > 0 ? point.clicks / point.responses_sent : 0,
    ) ?? [];
  const listenerRocSparkline =
    listenerAnalytics?.daily.slice(-14).map((point) =>
      point.compute_cost > 0 ? point.revenue / point.compute_cost : 0,
    ) ?? [];

  const sortedProducts = [...products].sort((left, right) => {
    const leftValue = left[sortKey];
    const rightValue = right[sortKey];

    if (typeof leftValue === "string" && typeof rightValue === "string") {
      return sortDirection === "asc"
        ? leftValue.localeCompare(rightValue)
        : rightValue.localeCompare(leftValue);
    }

    return sortDirection === "asc"
      ? Number(leftValue) - Number(rightValue)
      : Number(rightValue) - Number(leftValue);
  });

  const rocToneClass =
    overview.return_on_compute >= 1
      ? "bg-emerald-400/10 text-emerald-200"
      : overview.return_on_compute >= 0.5
        ? "bg-amber-400/10 text-amber-100"
        : "bg-rose-400/10 text-rose-100";

  function handleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection((currentDirection) =>
        currentDirection === "asc" ? "desc" : "asc",
      );
      return;
    }
    setSortKey(nextKey);
    setSortDirection("desc");
  }

  async function handleCopy(label: string, value: string | null | undefined) {
    if (!value) {
      return;
    }
    await navigator.clipboard.writeText(value);
    setCopiedField(label);
    window.setTimeout(() => {
      setCopiedField((current) => (current === label ? null : current));
    }, 1600);
  }

  async function handleDownload(label: string, url: string | null | undefined, fileName: string) {
    if (!url || !token) {
      return;
    }
    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error(`Unable to download ${label}.`);
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = fileName;
      document.body.append(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : `Unable to download ${label}.`,
      );
    }
  }

  async function handleStartListener() {
    if (!token || !campaignId) {
      return;
    }
    setIsRefreshing(true);
    try {
      const nextListenerStatus = await apiRequest<ListenerStatus>(
        `/campaigns/${campaignId}/listener/start`,
        {
          method: "POST",
          token,
        },
      );
      const [nextOverview, nextListenerAnalytics] = await Promise.all([
        apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, {
          method: "GET",
          token,
        }),
        apiRequest<ListenerAnalytics>(`/campaigns/${campaignId}/listener/analytics?period=${period}`, {
          method: "GET",
          token,
        }),
      ]);
      setOverview(nextOverview);
      setListenerStatus(nextListenerStatus);
      setListenerAnalytics(nextListenerAnalytics);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to start the intent listener.",
      );
    } finally {
      setIsRefreshing(false);
    }
  }

  async function handleRegenerateAgentKey() {
    if (!token || !campaignId) {
      return;
    }
    setIsRegeneratingKey(true);
    try {
      const response = await apiRequest<CampaignAgentKeyResponse>(
        `/campaigns/${campaignId}/agent-key/regenerate`,
        {
          method: "POST",
          token,
        },
      );
      setOverview((current) =>
        current
          ? {
              ...current,
              agent_endpoints: {
                ...current.agent_endpoints,
                openclaw: {
                  ...current.agent_endpoints.openclaw,
                  api_key: response.api_key,
                  api_key_preview: response.api_key_preview,
                },
              },
            }
          : current,
      );
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to regenerate the agent API key.",
      );
    } finally {
      setIsRegeneratingKey(false);
    }
  }

  const endpoints = overview.agent_endpoints;
  const openclaw = endpoints.openclaw;
  const openclawKeyValue = openclaw.api_key ?? null;
  const openclawSurfaces = listenerStatus?.surfaces_active.join(", ") ?? "";

  return (
    <div className="min-h-screen">
      <AppHeader
        title={overview.merchant_name}
        subtitle={`Compute-powered acquisition for ${overview.domain}. Dashboard refreshes every 20 seconds so spend, conversions, and Return on Compute stay in view.`}
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-[1.5rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-4">
          <DashboardMetricCard
            label="Compute Spent"
            value={overview.compute_spent}
            format="currency"
            accentClass="bg-blue-400/10 text-blue-100"
            caption={`${formatCurrency(overview.budget_spent)} of ${formatCurrency(overview.budget_monthly)} budget`}
            sparkline={overview.compute_series}
            progress={overview.budget_utilization}
          />
          <DashboardMetricCard
            label="Conversions"
            value={overview.conversions}
            accentClass="bg-blue-400/10 text-blue-100"
            caption="Daily trend from attributed campaign purchases"
            sparkline={conversionSparkline}
          />
          <DashboardMetricCard
            label="Revenue"
            value={overview.revenue}
            format="currency"
            accentClass="bg-emerald-400/10 text-emerald-100"
            caption="Attributed merchant revenue from AI surfaces"
            sparkline={overview.revenue_series}
          />
          <DashboardMetricCard
            label="Return on Compute"
            value={overview.return_on_compute}
            format="multiplier"
            accentClass="bg-emerald-400/10 text-emerald-100"
            caption={overview.return_on_compute >= 1 ? "Healthy efficiency curve" : "Needs optimization"}
            sparkline={rocSparkline}
          />
        </div>

        {listenerStatus && listenerAnalytics ? (
          <section className="panel p-6">
            <div className="flex flex-col gap-4 border-b border-white/8 pb-5 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="eyebrow">Intent listener</p>
                <h2 className="font-display text-2xl text-white">
                  Human-web monitoring and response engine
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
                  Reddit and X signals flow through scoring, response generation, human review,
                  and tracked referrals so RoC stays visible outside MCP traffic too.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] ${
                    listenerStatus.status === "running"
                      ? "border border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
                      : "border border-white/10 bg-white/5 text-slate-300"
                  }`}
                >
                  {listenerStatus.status === "running" ? "Running" : "Stopped"}
                </span>
                {listenerStatus.status !== "running" ? (
                  <button
                    onClick={() => void handleStartListener()}
                    className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Start listener
                  </button>
                ) : null}
                <Link
                  href="/review"
                  className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                >
                  Open review queue
                </Link>
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-4">
              <DashboardMetricCard
                label="Intents Detected"
                value={listenerAnalytics.signals_detected}
                accentClass="bg-blue-400/10 text-blue-100"
                caption={`${formatNumber(listenerStatus.signals_detected_today)} found today across ${formatNumber(listenerStatus.surfaces_active_count)} active surfaces${openclawSurfaces ? ` (${openclawSurfaces})` : ""}`}
                sparkline={listenerSignalSparkline}
              />
              <DashboardMetricCard
                label="Responses Sent"
                value={listenerAnalytics.responses_sent}
                accentClass="bg-blue-400/10 text-blue-100"
                caption={`${formatPercent(listenerAnalytics.response_rate)} of detected signals received a response`}
                sparkline={listenerResponseSparkline}
              />
              <DashboardMetricCard
                label="Listener CTR"
                value={listenerAnalytics.click_through_rate}
                format="percent"
                accentClass="bg-amber-400/10 text-amber-100"
                caption={`${formatNumber(listenerAnalytics.responses_pending_review)} replies currently awaiting approval`}
                sparkline={listenerCtrSparkline}
              />
              <DashboardMetricCard
                label="Listener RoC"
                value={listenerAnalytics.return_on_compute}
                format="multiplier"
                accentClass="bg-emerald-400/10 text-emerald-100"
                caption={`${formatCurrency(listenerAnalytics.revenue)} revenue on ${formatCurrency(listenerAnalytics.compute_cost)} compute`}
                sparkline={listenerRocSparkline}
              />
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="eyebrow">Top surfaces</p>
                    <h3 className="font-display text-2xl text-white">
                      Where outreach is converting
                    </h3>
                  </div>
                  <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                    {period.toUpperCase()}
                  </span>
                </div>

                <div className="mt-5 space-y-3">
                  {listenerAnalytics.top_surfaces.length ? (
                    listenerAnalytics.top_surfaces.map((surface) => (
                      <div
                        key={`${surface.surface}-${surface.subreddit_or_channel ?? "surface"}`}
                        className="rounded-[1.4rem] border border-white/8 bg-slate-950/45 p-4"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <p className="font-medium text-white">
                              {surface.subreddit_or_channel ?? surface.surface}
                            </p>
                            <p className="mt-1 text-sm text-slate-400">
                              {formatNumber(surface.signals_detected)} signals,{" "}
                              {formatNumber(surface.responses)} responses,{" "}
                              {formatNumber(surface.clicks)} clicks
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-display text-2xl text-white">
                              {formatMultiplier(surface.roc)}
                            </p>
                            <p className="text-sm text-slate-400">
                              {formatCurrency(surface.revenue)}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/45 p-4 text-sm leading-7 text-slate-400">
                      No listener surface data yet. Start the engine to begin ranking channels.
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="eyebrow">Review pressure</p>
                  <h3 className="font-display text-2xl text-white">Queue and approval health</h3>
                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 p-4">
                      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        Pending review
                      </p>
                      <p className="mt-2 font-display text-3xl text-white">
                        {formatNumber(listenerStatus.responses_pending_review)}
                      </p>
                    </div>
                    <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 p-4">
                      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        Approval rate
                      </p>
                      <p className="mt-2 font-display text-3xl text-white">
                        {formatPercent(listenerAnalytics.approval_rate)}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="eyebrow">Top communities</p>
                  <h3 className="font-display text-2xl text-white">Where intent clusters</h3>
                  <div className="mt-5 space-y-3">
                    {listenerAnalytics.top_subreddits.map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between rounded-[1.3rem] border border-white/8 bg-slate-950/45 px-4 py-3"
                      >
                        <p className="text-sm text-white">{item.label}</p>
                        <p className="text-sm text-slate-300">{formatNumber(item.count)}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="eyebrow">Top products</p>
                  <h3 className="font-display text-2xl text-white">What outreach actually sells</h3>
                  <div className="mt-5 space-y-3">
                    {listenerAnalytics.top_products.slice(0, 3).map((product) => (
                      <div
                        key={product.product_id ?? product.name ?? product.product_name}
                        className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 px-4 py-4"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <p className="text-sm font-medium text-white">
                              {product.name ?? product.product_name ?? "Product"}
                            </p>
                            <p className="mt-1 text-sm text-slate-400">
                              {formatNumber(product.responses)} responses,{" "}
                              {formatNumber(product.clicks)} clicks,{" "}
                              {formatNumber(product.conversions)} conversions
                            </p>
                          </div>
                          <p className="font-display text-2xl text-white">
                            {formatMultiplier(product.roc)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.55fr]">
          <section className="panel p-6">
            <div className="flex flex-col gap-4 border-b border-white/8 pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="eyebrow">Hero visualization</p>
                <h2 className="font-display text-2xl text-white">
                  Spend vs attributed revenue
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  The fastest way to see if compute is converting into revenue.
                </p>
              </div>

              <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/6 p-1">
                {(["7d", "30d", "90d", "all"] as Period[]).map((value) => (
                  <button
                    key={value}
                    onClick={() => setPeriod(value)}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      period === value
                        ? "bg-white text-slate-950"
                        : "text-slate-300 hover:text-white"
                    }`}
                  >
                    {value.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-6">
              <CampaignChart data={metrics} />
            </div>
          </section>

          <aside className="space-y-6">
            <section className="panel p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">Budget status</p>
                  <h2 className="font-display text-2xl text-white">Spend pacing</h2>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${rocToneClass}`}>
                  {formatMultiplier(overview.return_on_compute)}
                </span>
              </div>

              <div className="mt-6 h-3 rounded-full bg-white/8">
                <div
                  className="h-3 rounded-full bg-gradient-to-r from-blue-400 to-emerald-400"
                  style={{ width: `${Math.min(overview.budget_utilization * 100, 100)}%` }}
                />
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                    Utilization
                  </p>
                  <p className="mt-2 font-display text-3xl text-white">
                    {formatPercent(overview.budget_utilization)}
                  </p>
                </div>
                <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                    Projected month-end
                  </p>
                  <p className="mt-2 font-display text-3xl text-white">
                    {formatCurrency(overview.projected_monthly_spend)}
                  </p>
                </div>
              </div>

              {overview.alerts.length ? (
                <div className="mt-5 space-y-3">
                  {overview.alerts.map((alert) => (
                    <div
                      key={alert}
                      className="rounded-[1.3rem] border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100"
                    >
                      {alert}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-5 text-sm leading-7 text-slate-400">
                  Budget pacing looks healthy. Active ranking boost remains fully in force.
                </p>
              )}
            </section>

            <section className="panel p-6">
              <div className="flex flex-col gap-4 border-b border-white/8 pb-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="eyebrow">Activity feed</p>
                    <h2 className="font-display text-2xl text-white">Agent interactions</h2>
                  </div>
                  <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
                    {isRefreshing ? "Refreshing" : "Live"}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {(["all", "match", "response", "click", "conversion"] as const).map((value) => (
                    <button
                      key={value}
                      onClick={() => setEventFilter(value)}
                      className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] transition ${
                        eventFilter === value
                          ? "bg-white text-slate-950"
                          : "border border-white/10 bg-white/5 text-slate-300"
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 space-y-3">
                {activity.map((entry) => (
                  <Link
                    key={entry.id}
                    href={entry.product_id ? `/products/${entry.product_id}` : "#"}
                    className="block rounded-[1.4rem] border border-white/8 bg-white/4 p-4 transition hover:bg-white/7"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <p className="text-sm font-medium text-white">{entry.title}</p>
                        <span className="rounded-full border border-white/10 bg-slate-950/60 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-300">
                          {entry.channel}
                        </span>
                      </div>
                      <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        {entry.relative_time}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-7 text-slate-400">{entry.detail}</p>
                  </Link>
                ))}
              </div>
            </section>

            <section className="panel p-6">
              <button
                onClick={() => setEndpointsOpen((current) => !current)}
                className="flex w-full items-center justify-between gap-4"
              >
                <div className="text-left">
                  <p className="eyebrow">Agent endpoints</p>
                  <h2 className="font-display text-2xl text-white">
                    MCP, OpenClaw, ACP, and UCP surfaces
                  </h2>
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.22em] text-slate-300">
                  {endpointsOpen ? "Hide" : "Show"}
                </span>
              </button>

              {endpointsOpen ? (
                <div className="mt-6 space-y-4 border-t border-white/8 pt-5">
                  <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <span
                            className={`h-2.5 w-2.5 rounded-full ${
                              endpoints.mcp.status === "live"
                                ? "bg-emerald-300"
                                : "bg-slate-500"
                            }`}
                          />
                          <p className="text-sm font-medium text-white">MCP server URL</p>
                        </div>
                        <button
                          onClick={() => handleCopy("dashboard-mcp", endpoints.mcp.public_url)}
                          className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                        >
                          {copiedField === "dashboard-mcp" ? "Copied" : "Copy"}
                        </button>
                      </div>
                      <p className="break-all text-sm leading-7 text-slate-200">
                        {endpoints.mcp.public_url}
                      </p>
                      <p className="text-sm leading-7 text-slate-400">
                        Share this URL with any AI agent developer to make your products discoverable.
                      </p>
                    </div>
                  </div>

                  <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <div className="flex flex-col gap-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <span
                            className={`h-2.5 w-2.5 rounded-full ${
                              openclaw.status === "running"
                                ? "bg-emerald-300"
                                : openclaw.status === "paused"
                                  ? "bg-amber-300"
                                  : "bg-slate-500"
                            }`}
                          />
                          <div>
                            <p className="text-sm font-medium text-white">OpenClaw listener runtime</p>
                            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                              {openclaw.badge}
                            </p>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => void handleCopy("dashboard-openclaw-config", openclaw.config_url)}
                            className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                          >
                            {copiedField === "dashboard-openclaw-config" ? "Copied" : "Copy config URL"}
                          </button>
                          <button
                            onClick={() => void handleCopy("dashboard-openclaw-events", openclaw.events_url)}
                            className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                          >
                            {copiedField === "dashboard-openclaw-events" ? "Copied" : "Copy events URL"}
                          </button>
                          {openclaw.skill_download_url ? (
                            <button
                              onClick={() =>
                                void handleDownload(
                                  "skill file",
                                  openclaw.skill_download_url,
                                  "SKILL.md",
                                )
                              }
                              className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                            >
                              Download skill
                            </button>
                          ) : null}
                          {openclaw.config_download_url ? (
                            <button
                              onClick={() =>
                                void handleDownload(
                                  "config file",
                                  openclaw.config_download_url,
                                  "config.json",
                                )
                              }
                              className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-blue-100 transition hover:bg-blue-500/15"
                            >
                              Download config
                            </button>
                          ) : null}
                        </div>
                      </div>

                      <p className="text-sm leading-7 text-slate-400">
                        {openclaw.description}
                      </p>

                      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                        <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                              Campaign API key
                            </p>
                            <div className="flex gap-2">
                              {openclawKeyValue ? (
                                <button
                                  onClick={() => void handleCopy("dashboard-openclaw-key", openclawKeyValue)}
                                  className="rounded-full border border-white/10 bg-white/7 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                                >
                                  {copiedField === "dashboard-openclaw-key" ? "Copied" : "Copy key"}
                                </button>
                              ) : null}
                              <button
                                onClick={() => void handleRegenerateAgentKey()}
                                disabled={isRegeneratingKey}
                                className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-blue-100 transition hover:bg-blue-500/15 disabled:cursor-not-allowed disabled:opacity-70"
                              >
                                {isRegeneratingKey ? "Generating" : openclawKeyValue ? "Regenerate" : "Reveal / regenerate"}
                              </button>
                            </div>
                          </div>
                          <p className="mt-3 break-all font-mono text-sm text-white">
                            {openclawKeyValue ?? openclaw.api_key_preview ?? "Generate a campaign key to start the listener."}
                          </p>
                          <p className="mt-2 text-sm leading-7 text-slate-400">
                            The full key is shown only after creation or regeneration. Store it in the generated OpenClaw runtime config.
                          </p>
                        </div>

                        <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 p-4">
                          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                            Runtime files
                          </p>
                          <p className="mt-3 break-all text-sm leading-7 text-slate-200">
                            Skill: {openclaw.skill_path ?? "Pending generation"}
                          </p>
                          <p className="mt-2 break-all text-sm leading-7 text-slate-200">
                            Config: {openclaw.config_path ?? "Pending generation"}
                          </p>
                        </div>
                      </div>

                      <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/45 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                            Local launch command
                          </p>
                          <button
                            onClick={() => void handleCopy("dashboard-openclaw-command", openclaw.launch_command)}
                            className="rounded-full border border-white/10 bg-white/7 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                          >
                            {copiedField === "dashboard-openclaw-command" ? "Copied" : "Copy command"}
                          </button>
                        </div>
                        <p className="mt-3 break-all font-mono text-sm leading-7 text-slate-200">
                          {openclaw.launch_command}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4">
                    <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <div className="flex items-center justify-between gap-4">
                        <p className="text-sm font-medium text-white">ACP feed</p>
                        <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-amber-100">
                          Ready, pending submission
                        </span>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <a
                          href={endpoints.acp.preview_url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                        >
                          Preview link
                        </a>
                        <button
                          onClick={() => handleCopy("dashboard-acp", endpoints.acp.feed_url)}
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                        >
                          {copiedField === "dashboard-acp" ? "Copied" : "Copy feed URL"}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <div className="flex items-center justify-between gap-4">
                        <p className="text-sm font-medium text-white">UCP feed</p>
                        <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-amber-100">
                          Ready, pending submission
                        </span>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <a
                          href={endpoints.ucp.preview_url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                        >
                          Preview link
                        </a>
                        <button
                          onClick={() => handleCopy("dashboard-ucp", endpoints.ucp.feed_url)}
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                        >
                          {copiedField === "dashboard-ucp" ? "Copied" : "Copy feed URL"}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                      Connected surfaces
                    </p>
                    <p className="mt-2 text-sm leading-7 text-slate-200">
                      {endpoints.connected_surfaces}
                    </p>
                  </div>
                </div>
              ) : null}
            </section>
          </aside>
        </div>

        <section className="panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/8 px-6 py-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Product performance</p>
              <h2 className="font-display text-2xl text-white">
                Which products are converting compute into revenue
              </h2>
            </div>
            <p className="text-sm text-slate-400">
              Click a row for product-level query and attribute detail.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-white/6">
              <thead className="bg-white/4 text-left text-xs uppercase tracking-[0.22em] text-slate-400">
                <tr>
                  {[
                    { label: "Product", key: "name" },
                    { label: "Price", key: "price" },
                    { label: "Matches", key: "matches" },
                    { label: "Clicks", key: "clicks" },
                    { label: "Conversions", key: "conversions" },
                    { label: "Revenue", key: "revenue" },
                    { label: "RoC", key: "return_on_compute" },
                  ].map((column) => (
                    <th key={column.key} className="px-6 py-4">
                      <button
                        onClick={() => handleSort(column.key as SortKey)}
                        className="flex items-center gap-2 text-left transition hover:text-white"
                      >
                        {column.label}
                        {sortKey === column.key ? (
                          <span>{sortDirection === "desc" ? "↓" : "↑"}</span>
                        ) : null}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/6">
                {sortedProducts.map((product) => (
                  <tr
                    key={product.product_id}
                    onClick={() => router.push(`/products/${product.product_id}`)}
                    className={`cursor-pointer transition hover:bg-white/5 ${
                      product.status === "top"
                        ? "border-l-2 border-emerald-400"
                        : product.status === "watch"
                          ? "border-l-2 border-amber-400"
                          : "border-l-2 border-transparent"
                    }`}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-4">
                        <Image
                          src={product.image ?? fallbackImageSrc}
                          alt={product.name}
                          width={96}
                          height={112}
                          unoptimized
                          className="h-14 w-12 rounded-[1rem] object-cover"
                        />
                        <div>
                          <p className="font-medium text-white">{product.name}</p>
                          <p className="text-sm text-slate-400">
                            {product.status === "top"
                              ? "Top performer"
                              : product.status === "watch"
                                ? "Needs attention"
                                : "Stable"}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {formatCurrency(product.price, product.currency)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {formatNumber(product.matches)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {formatNumber(product.clicks)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {formatNumber(product.conversions)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">
                      {formatCurrency(product.revenue, product.currency)}
                    </td>
                    <td className="px-6 py-4 text-sm font-semibold text-white">
                      {formatMultiplier(product.return_on_compute)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
