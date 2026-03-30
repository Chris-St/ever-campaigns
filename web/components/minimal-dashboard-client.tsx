"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Logo } from "@/components/logo";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber } from "@/lib/format";
import type { ActivityEntry, CampaignOverview, ListenerStatus } from "@/lib/types";

function statusTone(status: string) {
  if (status === "running") {
    return "border-emerald-400/20 bg-emerald-500/10 text-emerald-100";
  }
  return "border-white/10 bg-white/6 text-slate-300";
}

export function MinimalDashboardClient() {
  const router = useRouter();
  const { token, user, loading, logout } = useAuth();
  const [overview, setOverview] = useState<CampaignOverview | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

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
    async function load() {
      try {
        const [nextOverview, nextListenerStatus, nextActivity] = await Promise.all([
          apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, { method: "GET", token }),
          apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
            method: "GET",
            token,
          }),
          apiRequest<ActivityEntry[]>(`/campaigns/${campaignId}/activity?limit=12&event_type=all`, {
            method: "GET",
            token,
          }),
        ]);
        if (cancelled) {
          return;
        }
        setOverview(nextOverview);
        setListenerStatus(nextListenerStatus);
        setActivity(nextActivity);
        setError(null);
      } catch (caughtError) {
        if (!cancelled) {
          setError(caughtError instanceof Error ? caughtError.message : "Unable to load dashboard.");
        }
      }
    }
    void load();
    const interval = window.setInterval(() => void load(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [campaignId, token]);

  async function handleStartAgent() {
    if (!token || !campaignId) {
      return;
    }
    try {
      const nextStatus = await apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/start`, {
        method: "POST",
        token,
      });
      setListenerStatus(nextStatus);
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to start the agent.");
    }
  }

  if (loading || !token || !campaignId || !overview || !listenerStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        Loading dashboard...
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-5 py-6 sm:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <Logo />
          <div className="flex items-center gap-2">
            <Link
              href="/dashboard"
              className="rounded-full bg-white px-4 py-2 text-sm text-slate-950"
            >
              Dashboard
            </Link>
            <Link
              href="/proposals"
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200"
            >
              Proposals
            </Link>
            <Link
              href="/settings"
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200"
            >
              Settings
            </Link>
            <button
              onClick={() => {
                logout();
                router.push("/");
              }}
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200"
            >
              Sign out
            </button>
          </div>
        </header>

        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <section className="panel p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="eyebrow">Live experiment</p>
              <h1 className="font-display text-3xl text-white">Return on Compute</h1>
              <p className="mt-2 text-sm leading-7 text-slate-400">
                Minimal tracker for the live run. Spend, proposals, revenue, and RoC.
              </p>
            </div>
            <div className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.22em] ${statusTone(listenerStatus.status)}`}>
              {listenerStatus.status}
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Spend</p>
              <p className="mt-2 font-display text-3xl text-white">{formatCurrency(overview.compute_spent)}</p>
              <p className="mt-2 text-sm text-slate-400">
                {formatCurrency(overview.budget_spent)} of {formatCurrency(overview.budget_monthly)}
              </p>
            </div>
            <div className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Proposals</p>
              <p className="mt-2 font-display text-3xl text-white">{formatNumber(overview.proposals.pending)}</p>
              <p className="mt-2 text-sm text-slate-400">{formatNumber(overview.proposals.total)} total</p>
            </div>
            <div className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Revenue</p>
              <p className="mt-2 font-display text-3xl text-white">{formatCurrency(overview.revenue)}</p>
              <p className="mt-2 text-sm text-slate-400">{formatNumber(overview.conversions)} conversions</p>
            </div>
            <div className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">RoC</p>
              <p className="mt-2 font-display text-3xl text-white">{formatMultiplier(overview.return_on_compute)}</p>
              <p className="mt-2 text-sm text-slate-400">
                {listenerStatus.status === "running" ? "Agent is learning live." : "Agent is stopped."}
              </p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            {listenerStatus.status !== "running" ? (
              <button
                onClick={() => void handleStartAgent()}
                className="rounded-full bg-emerald-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
              >
                Launch agent
              </button>
            ) : null}
            <Link
              href="/proposals"
              className="rounded-full border border-white/10 bg-white/6 px-5 py-3 text-sm text-slate-200"
            >
              Open proposals
            </Link>
            <span className="text-sm text-slate-500">
              {formatNumber(listenerStatus.active_surface_count)} active surfaces • {formatCurrency(listenerStatus.budget_remaining)} remaining
            </span>
          </div>
        </section>

        <section className="panel p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="eyebrow">Activity</p>
              <h2 className="text-xl text-white">Latest moves</h2>
            </div>
            <Link href="/proposals" className="text-sm text-slate-400 hover:text-white">
              View queue
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {activity.length ? (
              activity.map((entry) => (
                <article
                  key={entry.id}
                  className="rounded-[1.2rem] border border-white/8 bg-white/4 px-4 py-3"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium text-white">{entry.title}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-400">{entry.detail}</p>
                    </div>
                    <div className="text-right text-xs uppercase tracking-[0.22em] text-slate-500">
                      <p>{entry.relative_time}</p>
                      {entry.compute_cost ? <p className="mt-1">{formatCurrency(entry.compute_cost)}</p> : null}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <p className="text-sm text-slate-500">No activity yet.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
