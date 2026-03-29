"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import type { CampaignOverview, ListenerStatus } from "@/lib/types";

const aggressivenessProfiles = {
  conservative: { max_actions_per_day: 25, quality_threshold: 78 },
  balanced: { max_actions_per_day: 50, quality_threshold: 64 },
  aggressive: { max_actions_per_day: 100, quality_threshold: 52 },
} as const;

export function SettingsClient() {
  const router = useRouter();
  const { token, user, loading, logout } = useAuth();
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [budget, setBudget] = useState(2400);
  const [status, setStatus] = useState<"active" | "paused" | "pending_payment" | "draft">("active");
  const [listenerMode, setListenerMode] = useState<ListenerStatus["config"]["listener_mode"]>("simulation");
  const [listenerAggressiveness, setListenerAggressiveness] =
    useState<ListenerStatus["config"]["aggressiveness"]>("balanced");
  const [listenerTone, setListenerTone] = useState("");
  const [listenerStory, setListenerStory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [listenerSaving, setListenerSaving] = useState(false);

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
      return;
    }
    if (!loading && token && user) {
      const storedCampaignId = getActiveCampaignId();
      const activeCampaignId =
        user.campaigns.find((campaignItem) => campaignItem.id === storedCampaignId)?.id ??
        user.campaigns[0]?.id;

      if (!activeCampaignId) {
        router.replace("/onboarding");
        return;
      }

      setActiveCampaignId(activeCampaignId);
      void loadCampaign(activeCampaignId, token);
    }
  }, [loading, router, token, user]);

  async function loadCampaign(campaignId: string, resolvedToken: string) {
    try {
      const [response, nextListenerStatus] = await Promise.all([
        apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, {
          method: "GET",
          token: resolvedToken,
        }),
        apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
          method: "GET",
          token: resolvedToken,
        }),
      ]);
      setCampaign(response);
      setBudget(response.budget_monthly);
      setStatus(response.status as "active" | "paused" | "pending_payment" | "draft");
      setListenerStatus(nextListenerStatus);
      setListenerMode(nextListenerStatus.config.listener_mode);
      setListenerAggressiveness(nextListenerStatus.config.aggressiveness);
      setListenerTone(nextListenerStatus.brand_voice_profile.tone);
      setListenerStory(nextListenerStatus.brand_voice_profile.story);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to load settings.",
      );
    }
  }

  async function handleSaveCampaign() {
    if (!token || !campaign) {
      return;
    }
    setSaving(true);
    try {
      const response = await apiRequest<CampaignOverview>(`/campaigns/${campaign.id}`, {
        method: "PUT",
        token,
        body: {
          budget_monthly: budget,
          status,
        },
      });
      setCampaign(response);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to update campaign settings.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveAgentSettings() {
    if (!token || !campaign || !listenerStatus) {
      return;
    }
    setListenerSaving(true);
    try {
      const profile = aggressivenessProfiles[listenerAggressiveness];
      const response = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
        method: "PUT",
        token,
        body: {
          brand_voice_profile: {
            ...listenerStatus.brand_voice_profile,
            tone: listenerTone,
            story: listenerStory,
          },
          config: {
            ...listenerStatus.config,
            listener_mode: listenerMode,
            aggressiveness: listenerAggressiveness,
            max_actions_per_day: profile.max_actions_per_day,
            quality_threshold: profile.quality_threshold,
            safeguards: {
              ...listenerStatus.config.safeguards,
              max_actions_per_day: profile.max_actions_per_day,
            },
          },
        },
      });
      setListenerStatus(response);
      setListenerMode(response.config.listener_mode);
      setListenerAggressiveness(response.config.aggressiveness);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to update agent settings.",
      );
    } finally {
      setListenerSaving(false);
    }
  }

  async function handleToggleAgent(nextStatus: "start" | "stop") {
    if (!token || !campaign) {
      return;
    }
    setListenerSaving(true);
    try {
      const response = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/${nextStatus}`, {
        method: "POST",
        token,
      });
      setListenerStatus(response);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : `Unable to ${nextStatus} the agent.`,
      );
    } finally {
      setListenerSaving(false);
    }
  }

  if (loading || !token || !campaign || !listenerStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        {error ?? "Loading settings..."}
      </div>
    );
  }

  const profile = aggressivenessProfiles[listenerAggressiveness];

  return (
    <div className="min-h-screen">
      <AppHeader
        title="Settings"
        subtitle="Control budget, launch mode, and the brand identity your autonomous agent carries into the market."
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-6">
            <section className="panel p-6">
              <p className="eyebrow">Campaign controls</p>
              <h2 className="font-display text-2xl text-white">Budget and lifecycle</h2>

              <div className="mt-6 space-y-5">
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <label className="block space-y-3">
                    <span className="text-sm text-slate-300">Monthly compute budget</span>
                    <input
                      type="range"
                      min="50"
                      max="10000"
                      step="50"
                      value={budget}
                      onChange={(event) => setBudget(Number(event.target.value))}
                      className="w-full accent-emerald-400"
                    />
                    <div className="font-display text-4xl text-white">{formatCurrency(budget)}</div>
                  </label>
                </div>

                <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <span className="text-sm text-slate-300">Campaign status</span>
                  <select
                    value={status}
                    onChange={(event) =>
                      setStatus(event.target.value as "active" | "paused" | "pending_payment" | "draft")
                    }
                    className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                  >
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="pending_payment">Pending payment</option>
                    <option value="draft">Draft</option>
                  </select>
                </label>

                <button
                  onClick={handleSaveCampaign}
                  disabled={saving}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {saving ? "Saving..." : "Save campaign settings"}
                </button>
              </div>
            </section>

            <section className="panel p-6">
              <div className="flex flex-col gap-4 border-b border-white/8 pb-5 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="eyebrow">Autonomous agent</p>
                  <h2 className="font-display text-2xl text-white">Mode and identity</h2>
                </div>
                <div className="flex flex-wrap gap-3">
                  <span
                    className={`rounded-full px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] ${
                      listenerStatus.status === "running"
                        ? "border border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
                        : "border border-white/10 bg-white/6 text-slate-300"
                    }`}
                  >
                    {listenerStatus.status}
                  </span>
                  <button
                    onClick={() =>
                      void handleToggleAgent(listenerStatus.status === "running" ? "stop" : "start")
                    }
                    disabled={listenerSaving}
                    className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {listenerStatus.status === "running" ? "Stop agent" : "Launch agent"}
                  </button>
                </div>
              </div>

              <div className="mt-6 space-y-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Mode</span>
                    <select
                      value={listenerMode}
                      onChange={(event) =>
                        setListenerMode(event.target.value as ListenerStatus["config"]["listener_mode"])
                      }
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    >
                      <option value="simulation">Simulation</option>
                      <option value="live">Live OpenClaw agent</option>
                    </select>
                    <p className="mt-3 text-sm leading-7 text-slate-400">
                      Simulation keeps the demo data flowing. Live mode waits for a real autonomous
                      agent to fetch config and report actions back into Ever.
                    </p>
                  </label>

                  <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Aggressiveness</span>
                    <select
                      value={listenerAggressiveness}
                      onChange={(event) =>
                        setListenerAggressiveness(
                          event.target.value as ListenerStatus["config"]["aggressiveness"],
                        )
                      }
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    >
                      <option value="conservative">Conservative</option>
                      <option value="balanced">Balanced</option>
                      <option value="aggressive">Aggressive</option>
                    </select>
                    <p className="mt-3 text-sm leading-7 text-slate-400">
                      Current limit: {formatNumber(profile.max_actions_per_day)} actions/day.
                    </p>
                  </label>
                </div>

                <label className="block rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <span className="text-sm text-slate-300">Brand voice</span>
                  <input
                    value={listenerTone}
                    onChange={(event) => setListenerTone(event.target.value)}
                    className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                  />
                </label>

                <label className="block rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <span className="text-sm text-slate-300">Brand story</span>
                  <textarea
                    value={listenerStory}
                    onChange={(event) => setListenerStory(event.target.value)}
                    rows={5}
                    className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                  />
                </label>

                <button
                  onClick={handleSaveAgentSettings}
                  disabled={listenerSaving}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {listenerSaving ? "Saving..." : "Save agent settings"}
                </button>
              </div>
            </section>
          </div>

          <div className="space-y-6">
            <section className="panel p-6">
              <p className="eyebrow">Agent summary</p>
              <h2 className="font-display text-2xl text-white">Current operating profile</h2>

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Actions today</p>
                  <p className="mt-2 font-display text-3xl text-white">{listenerStatus.actions_today}</p>
                </div>
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Discovered surfaces</p>
                  <p className="mt-2 font-display text-3xl text-white">{listenerStatus.active_surface_count}</p>
                </div>
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Compute today</p>
                  <p className="mt-2 font-display text-3xl text-white">
                    {formatCurrency(listenerStatus.compute_spent_today)}
                  </p>
                </div>
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Budget remaining</p>
                  <p className="mt-2 font-display text-3xl text-white">
                    {formatCurrency(listenerStatus.budget_remaining)}
                  </p>
                </div>
              </div>
            </section>

            <section className="panel p-6">
              <p className="eyebrow">Products</p>
              <h2 className="font-display text-2xl text-white">Catalog and performance</h2>
              <p className="mt-3 text-sm leading-7 text-slate-400">
                Re-scan your store or head back to the dashboard to watch which products the autonomous agent is finding traction with.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  href="/onboarding"
                  className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                >
                  Re-scan store
                </Link>
                <Link
                  href="/dashboard"
                  className="rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100 transition hover:bg-blue-500/15"
                >
                  View dashboard
                </Link>
              </div>
            </section>

            <section className="panel p-6">
              <p className="eyebrow">Billing</p>
              <h2 className="font-display text-2xl text-white">Plan and invoices</h2>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Plan</p>
                  <p className="mt-2 text-lg text-white">{campaign.billing.plan_name}</p>
                </div>
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Payment method</p>
                  <p className="mt-2 text-lg text-white">{campaign.billing.payment_method}</p>
                </div>
              </div>

              <div className="mt-6 space-y-3">
                {campaign.billing.invoices.map((invoice) => (
                  <div
                    key={invoice.id}
                    className="flex items-center justify-between rounded-[1.4rem] border border-white/8 bg-white/4 px-4 py-4"
                  >
                    <div>
                      <p className="text-sm font-medium text-white">{invoice.id}</p>
                      <p className="text-sm text-slate-400">{formatDate(invoice.date)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-white">{formatCurrency(invoice.amount)}</p>
                      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        {invoice.status}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel p-6">
              <p className="eyebrow">Account</p>
              <h2 className="font-display text-2xl text-white">Identity and access</h2>
              <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm text-slate-300">{user?.email}</p>
                  <p className="text-sm text-slate-500">Single-brand account access</p>
                </div>
                <button
                  onClick={() => {
                    logout();
                    router.push("/");
                  }}
                  className="rounded-full border border-amber-400/20 bg-amber-500/8 px-4 py-3 text-sm text-amber-100 transition hover:bg-amber-500/15"
                >
                  Sign out
                </button>
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
