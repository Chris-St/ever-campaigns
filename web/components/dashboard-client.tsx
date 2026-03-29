"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { CampaignChart } from "@/components/campaign-chart";
import { DashboardMetricCard } from "@/components/dashboard-metric-card";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import {
  formatCurrency,
  formatDate,
  formatMultiplier,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  ActivityEntry,
  CampaignOverview,
  ListenerAnalytics,
  ListenerStatus,
  ProductPerformanceRow,
  TimeSeriesPoint,
} from "@/lib/types";

type Period = "7d" | "30d" | "90d" | "all";
type FeedFilter = "all" | "proposal" | "action" | "strategy" | "click" | "conversion" | "match";

function activityTone(category?: string | null) {
  switch (category) {
    case "outreach":
      return "border-blue-400/20 bg-blue-500/10 text-blue-100";
    case "content_creation":
      return "border-fuchsia-400/20 bg-fuchsia-500/10 text-fuchsia-100";
    case "engagement":
      return "border-emerald-400/20 bg-emerald-500/10 text-emerald-100";
    case "research":
      return "border-white/10 bg-white/6 text-slate-200";
    case "strategy":
      return "border-amber-400/20 bg-amber-500/10 text-amber-100";
    case "proposal":
      return "border-blue-400/20 bg-blue-500/10 text-blue-100";
    case "conversion":
      return "border-emerald-400/20 bg-emerald-500/10 text-emerald-100";
    default:
      return "border-white/10 bg-white/6 text-slate-200";
  }
}

export function DashboardClient() {
  const router = useRouter();
  const { token, user, loading } = useAuth();
  const [period, setPeriod] = useState<Period>("30d");
  const [feedFilter, setFeedFilter] = useState<FeedFilter>("all");
  const [overview, setOverview] = useState<CampaignOverview | null>(null);
  const [metrics, setMetrics] = useState<TimeSeriesPoint[]>([]);
  const [products, setProducts] = useState<ProductPerformanceRow[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [listenerAnalytics, setListenerAnalytics] = useState<ListenerAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [endpointsOpen, setEndpointsOpen] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const storedCampaignId = user ? getActiveCampaignId() : null;
  const campaignId = user
    ? user.campaigns.find((campaign) => campaign.id === storedCampaignId)?.id ?? user.campaigns[0]?.id ?? null
    : null;

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
      return;
    }
    if (!loading && token && user) {
      if (!campaignId) {
        router.replace("/onboarding");
        return;
      }
      setActiveCampaignId(campaignId);
    }
  }, [campaignId, loading, router, token, user]);

  useEffect(() => {
    if (!token || !campaignId) {
      return;
    }

    let cancelled = false;
    async function loadDashboardData() {
      try {
        const [
          nextOverview,
          nextMetrics,
          nextProducts,
          nextActivity,
          nextListenerStatus,
          nextListenerAnalytics,
        ] = await Promise.all([
          apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, { method: "GET", token }),
          apiRequest<TimeSeriesPoint[]>(`/campaigns/${campaignId}/metrics?period=${period}`, {
            method: "GET",
            token,
          }),
          apiRequest<ProductPerformanceRow[]>(`/campaigns/${campaignId}/products`, {
            method: "GET",
            token,
          }),
          apiRequest<ActivityEntry[]>(
            `/campaigns/${campaignId}/activity?limit=24&event_type=${feedFilter}`,
            { method: "GET", token },
          ),
          apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
            method: "GET",
            token,
          }),
          apiRequest<ListenerAnalytics>(`/campaigns/${campaignId}/listener/analytics?period=${period}`, {
            method: "GET",
            token,
          }),
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
  }, [campaignId, feedFilter, period, token]);

  async function handleStartAgent() {
    if (!token || !campaignId) {
      return;
    }
    try {
      const nextStatus = await apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/start`, {
        method: "POST",
        token,
      });
      const nextAnalytics = await apiRequest<ListenerAnalytics>(
        `/campaigns/${campaignId}/listener/analytics?period=${period}`,
        {
          method: "GET",
          token,
        },
      );
      setListenerStatus(nextStatus);
      setListenerAnalytics(nextAnalytics);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to start the autonomous agent.",
      );
    }
  }

  async function handleCopy(label: string, value: string | null | undefined) {
    if (!value) {
      return;
    }
    await navigator.clipboard.writeText(value);
    setCopiedField(label);
    window.setTimeout(() => {
      setCopiedField((current) => (current === label ? null : current));
    }, 1400);
  }

  if (loading || !token || !campaignId || !overview || !listenerStatus || !listenerAnalytics) {
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
  const actionSparkline = listenerAnalytics.daily_series.map((point) => point.actions_reported);
  const strategySparkline = listenerAnalytics.daily_series.map((point) => point.strategy_updates);
  const listenerRocSparkline = listenerAnalytics.daily_series.map((point) =>
    point.compute_cost > 0 ? point.revenue / point.compute_cost : 0,
  );

  return (
    <div className="min-h-screen">
      <AppHeader
        title="Paid Experiment Dashboard"
        subtitle="The agent discovers opportunities and drafts proposals. You approve, execute, and record outcomes. Ever tracks whether that loop is producing Return on Compute."
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-5">
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
            label="Pending Proposals"
            value={overview.proposals.pending}
            accentClass="bg-blue-400/10 text-blue-100"
            caption={`${formatNumber(overview.proposals.total)} total proposals generated`}
            sparkline={listenerAnalytics.daily_series.map((point) => point.actions_reported)}
          />
          <DashboardMetricCard
            label="Conversions"
            value={overview.conversions}
            accentClass="bg-blue-400/10 text-blue-100"
            caption="Attributed purchases tied back to proposals or tracked links"
            sparkline={conversionSparkline}
          />
          <DashboardMetricCard
            label="Revenue"
            value={overview.revenue}
            format="currency"
            accentClass="bg-emerald-400/10 text-emerald-100"
            caption="Revenue generated from tracked referral activity"
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

        <section className="panel p-6">
          <div className="flex flex-col gap-4 border-b border-white/8 pb-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="eyebrow">Autonomous agent</p>
              <h2 className="font-display text-2xl text-white">What the agent is actually doing</h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
                Ever no longer assumes fixed channels. The agent decides where to spend compute,
                reports opportunities as proposals, and waits for your approval before anything goes live.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] ${
                  listenerStatus.status === "running"
                    ? "border border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
                    : "border border-white/10 bg-white/6 text-slate-300"
                }`}
              >
                {listenerStatus.status}
              </span>
              {listenerStatus.status !== "running" ? (
                <button
                  onClick={() => void handleStartAgent()}
                  className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                >
                  Launch propose-only agent
                </button>
              ) : null}
              <span className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-xs uppercase tracking-[0.22em] text-slate-300">
                approval required
              </span>
              <Link
                href="/proposals"
                className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
              >
                Open proposals
              </Link>
            </div>
          </div>

          <div className="mt-6 grid gap-4 xl:grid-cols-5">
            <DashboardMetricCard
              label="Proposals Generated"
              value={listenerAnalytics.proposals_generated}
              accentClass="bg-blue-400/10 text-blue-100"
              caption={`${formatNumber(listenerStatus.proposals_pending)} waiting in the queue`}
              sparkline={actionSparkline}
            />
            <DashboardMetricCard
              label="Strategy Updates"
              value={listenerAnalytics.strategy_updates}
              accentClass="bg-amber-400/10 text-amber-100"
              caption={`${formatNumber(listenerStatus.strategy_updates_today)} summaries reported today`}
              sparkline={strategySparkline}
            />
            <DashboardMetricCard
              label="Approval Rate"
              value={listenerAnalytics.approval_rate}
              format="percent"
              accentClass="bg-blue-400/10 text-blue-100"
              caption={`${formatNumber(listenerAnalytics.proposals_approved)} approved from ${formatNumber(listenerAnalytics.proposals_generated)} proposals`}
              sparkline={listenerAnalytics.daily_series.map((point) =>
                point.actions_reported > 0 ? point.responses_sent / point.actions_reported : 0,
              )}
            />
            <DashboardMetricCard
              label="Execution Rate"
              value={listenerAnalytics.execution_rate}
              format="percent"
              accentClass="bg-amber-400/10 text-amber-100"
              caption={`${formatNumber(listenerAnalytics.proposals_executed)} executed manually`}
              sparkline={listenerAnalytics.daily_series.map((point) =>
                point.responses_sent > 0 ? point.clicks / point.responses_sent : 0,
              )}
            />
            <DashboardMetricCard
              label="Agent RoC"
              value={listenerAnalytics.return_on_compute}
              format="multiplier"
              accentClass="bg-emerald-400/10 text-emerald-100"
              caption={`${formatCurrency(listenerAnalytics.revenue)} revenue on ${formatCurrency(listenerAnalytics.compute_cost)} compute`}
              sparkline={listenerRocSparkline}
            />
          </div>
        </section>

        <div className="grid gap-6 xl:grid-cols-[1.45fr_0.55fr]">
          <section className="panel p-6">
            <div className="flex flex-col gap-4 border-b border-white/8 pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="eyebrow">Hero visualization</p>
                <h2 className="font-display text-2xl text-white">Spend vs attributed revenue</h2>
                <p className="mt-1 text-sm text-slate-400">
                  The clearest read on whether autonomous activity is translating into revenue.
                </p>
              </div>

              <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/6 p-1">
                {(["7d", "30d", "90d", "all"] as Period[]).map((value) => (
                  <button
                    key={value}
                    onClick={() => setPeriod(value)}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      period === value ? "bg-white text-slate-950" : "text-slate-300 hover:text-white"
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
              <p className="eyebrow">Budget status</p>
              <h2 className="font-display text-2xl text-white">Runway and pacing</h2>

              <div className="mt-6 h-3 rounded-full bg-white/8">
                <div
                  className="h-3 rounded-full bg-gradient-to-r from-blue-400 to-emerald-400"
                  style={{ width: `${Math.min(overview.budget_utilization * 100, 100)}%` }}
                />
              </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Utilization</p>
                  <p className="mt-2 font-display text-3xl text-white">
                    {formatPercent(overview.budget_utilization)}
                  </p>
                </div>
                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Projected month-end</p>
                    <p className="mt-2 font-display text-3xl text-white">
                      {formatCurrency(overview.projected_monthly_spend)}
                    </p>
                  </div>
                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Confirmed attribution</p>
                    <p className="mt-2 font-display text-3xl text-white">
                      {formatNumber(overview.attribution_confidence.confirmed)}
                    </p>
                  </div>
                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Estimated attribution</p>
                    <p className="mt-2 font-display text-3xl text-white">
                      {formatNumber(overview.attribution_confidence.estimated)}
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
                  The agent still has healthy compute runway. Right now it is searching across{" "}
                  {formatNumber(listenerStatus.active_surface_count)} discovered surfaces and queueing proposals for approval.
                </p>
              )}
            </section>

            <section className="panel p-6">
              <button
                onClick={() => setEndpointsOpen((current) => !current)}
                className="flex w-full items-center justify-between gap-4"
              >
                <div className="text-left">
                  <p className="eyebrow">Agent endpoints</p>
                  <h2 className="font-display text-2xl text-white">Runtime handoff</h2>
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.22em] text-slate-300">
                  {endpointsOpen ? "Hide" : "Show"}
                </span>
              </button>

              {endpointsOpen ? (
                <div className="mt-6 space-y-4 border-t border-white/8 pt-5">
                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white">Config URL</p>
                      <button
                        onClick={() =>
                          void handleCopy("config-url", overview.agent_endpoints.openclaw.config_url)
                        }
                        className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                      >
                        {copiedField === "config-url" ? "Copied" : "Copy"}
                      </button>
                    </div>
                    <p className="mt-3 break-all text-sm text-slate-300">
                      {overview.agent_endpoints.openclaw.config_url}
                    </p>
                  </div>

                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white">Events URL</p>
                      <button
                        onClick={() =>
                          void handleCopy("events-url", overview.agent_endpoints.openclaw.events_url)
                        }
                        className="rounded-full border border-white/10 bg-white/7 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white transition hover:bg-white/12"
                      >
                        {copiedField === "events-url" ? "Copied" : "Copy"}
                      </button>
                    </div>
                    <p className="mt-3 break-all text-sm text-slate-300">
                      {overview.agent_endpoints.openclaw.events_url}
                    </p>
                  </div>

                  <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                    <p className="text-sm font-medium text-white">Campaign API key</p>
                    <p className="mt-3 text-sm text-slate-300">
                      {overview.agent_endpoints.openclaw.api_key_preview ?? "Generate from the API if needed"}
                    </p>
                    <p className="mt-2 text-sm leading-7 text-slate-400">
                      The agent fetches config from Ever, chooses its own channels and tactics, and reports every action back through this authenticated event stream.
                    </p>
                  </div>
                </div>
              ) : null}
            </section>
          </aside>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="panel p-6">
            <div className="flex items-center justify-between border-b border-white/8 pb-5">
              <div>
                <p className="eyebrow">Channel breakdown</p>
                <h2 className="font-display text-2xl text-white">Discovered channels ranked by RoC</h2>
              </div>
              <span className="text-xs uppercase tracking-[0.22em] text-slate-500">{period.toUpperCase()}</span>
            </div>

            <div className="mt-5 space-y-3">
              {listenerAnalytics.channel_breakdown.length ? (
                listenerAnalytics.channel_breakdown.map((channel) => (
                  <div
                    key={channel.surface}
                    className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-white">{channel.surface}</p>
                          <span className="rounded-full border border-white/10 bg-slate-950/60 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300">
                            {formatNumber(channel.actions)} proposals
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-slate-400">
                          {formatNumber(channel.clicks)} clicks, {formatNumber(channel.conversions)} conversions,{" "}
                          {formatCurrency(channel.compute_cost)} compute
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-display text-3xl text-white">
                          {formatMultiplier(channel.return_on_compute)}
                        </p>
                        <p className="text-sm text-slate-400">{formatCurrency(channel.revenue)}</p>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-slate-400">
                  No proposals have been reported yet. Launch the agent or switch to simulation to populate this view.
                </div>
              )}
            </div>
          </section>

          <section className="panel p-6">
            <div className="border-b border-white/8 pb-5">
              <p className="eyebrow">Strategy feed</p>
                <h2 className="font-display text-2xl text-white">How the agent thinks it is winning</h2>
            </div>
            <div className="mt-5 space-y-3">
              {listenerAnalytics.strategy_feed.length ? (
                listenerAnalytics.strategy_feed.map((entry) => (
                  <article
                    key={entry.id}
                    className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-white">
                        {formatDate(entry.timestamp)}
                      </p>
                      <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        {entry.relative_time}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-300">{entry.description}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {entry.channels_used.map((channel) => (
                        <span
                          key={`${entry.id}-${channel}`}
                          className="rounded-full border border-white/10 bg-slate-950/60 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300"
                        >
                          {channel}
                        </span>
                      ))}
                    </div>
                    <p className="mt-4 text-xs uppercase tracking-[0.22em] text-slate-500">
                      {formatNumber(entry.total_actions)} actions • {formatCurrency(entry.compute_cost)} compute
                    </p>
                  </article>
                ))
              ) : (
                <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-slate-400">
                  Strategy updates appear when the agent reports what it tried, what worked, and where it wants to spend compute next.
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <section className="panel p-6">
            <div className="flex flex-col gap-3 border-b border-white/8 pb-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="eyebrow">Activity feed</p>
                <h2 className="font-display text-2xl text-white">Every proposal, approval, click, and conversion</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {(["all", "proposal", "action", "strategy", "click", "conversion", "match"] as FeedFilter[]).map((value) => (
                  <button
                    key={value}
                    onClick={() => setFeedFilter(value)}
                    className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] transition ${
                      feedFilter === value
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
                <article
                  key={entry.id}
                  className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] ${activityTone(entry.category)}`}
                    >
                      {(entry.category ?? entry.event_type).replace(/_/g, " ")}
                    </span>
                    {entry.surface ? (
                      <span className="rounded-full border border-white/10 bg-slate-950/60 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-300">
                        {entry.surface}
                      </span>
                    ) : null}
                    <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                      {entry.relative_time}
                    </span>
                  </div>
                  <div className="mt-3 flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium text-white">{entry.title}</p>
                      <p className="mt-2 text-sm leading-7 text-slate-400">{entry.detail}</p>
                      {entry.product_name ? (
                        <p className="mt-2 text-sm text-slate-300">Product: {entry.product_name}</p>
                      ) : null}
                      {entry.proposal_status ? (
                        <p className="mt-2 text-sm text-slate-400">
                          Proposal status: {entry.proposal_status.replace(/_/g, " ")}
                        </p>
                      ) : null}
                    </div>
                    {entry.compute_cost ? (
                      <div className="text-right text-xs uppercase tracking-[0.22em] text-slate-500">
                        <p>{formatCurrency(entry.compute_cost)}</p>
                        {entry.expected_impact ? <p className="mt-1">{entry.expected_impact} impact</p> : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel p-6">
            <div className="border-b border-white/8 pb-5">
              <p className="eyebrow">Product performance</p>
              <h2 className="font-display text-2xl text-white">What the agent is pushing effectively</h2>
            </div>

            <div className="mt-5 space-y-3">
              {products.slice(0, 6).map((product) => (
                <div
                  key={product.product_id}
                  className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4"
                >
                  <div className="flex items-center gap-4">
                    <div className="relative h-16 w-16 overflow-hidden rounded-[1rem] border border-white/8 bg-slate-950/70">
                      <Image
                        src={fallbackImageSrc(product.image)}
                        alt={product.name}
                        fill
                        className="object-cover"
                        sizes="64px"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-medium text-white">{product.name}</p>
                          <p className="mt-1 text-sm text-slate-400">
                            {formatCurrency(product.price, product.currency)} • {formatNumber(product.matches)} actions
                          </p>
                        </div>
                        <p className="font-display text-2xl text-white">
                          {formatMultiplier(product.return_on_compute)}
                        </p>
                      </div>
                      <p className="mt-3 text-sm text-slate-300">
                        {formatNumber(product.clicks)} clicks • {formatNumber(product.conversions)} conversions •{" "}
                        {formatCurrency(product.revenue)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
