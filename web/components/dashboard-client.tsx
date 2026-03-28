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
  CampaignOverview,
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
  const [eventFilter, setEventFilter] = useState<"all" | "match" | "click" | "conversion">(
    "all",
  );
  const [sortKey, setSortKey] = useState<SortKey>("revenue");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [overview, setOverview] = useState<CampaignOverview | null>(null);
  const [metrics, setMetrics] = useState<TimeSeriesPoint[]>([]);
  const [products, setProducts] = useState<ProductPerformanceRow[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
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
        const [nextOverview, nextMetrics, nextProducts, nextActivity] = await Promise.all([
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
        ]);

        if (cancelled) {
          return;
        }

        setOverview(nextOverview);
        setMetrics(nextMetrics);
        setProducts(nextProducts);
        setActivity(nextActivity);
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

  const endpoints = overview.agent_endpoints;

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
                  {(["all", "match", "click", "conversion"] as const).map((value) => (
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
                    MCP, ACP, and UCP surfaces
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
