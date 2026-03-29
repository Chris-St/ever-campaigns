"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatDate } from "@/lib/format";
import type { CampaignOverview, ListenerStatus } from "@/lib/types";

export function SettingsClient() {
  const router = useRouter();
  const { token, user, loading, logout } = useAuth();
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [budget, setBudget] = useState(2400);
  const [status, setStatus] = useState<"active" | "paused" | "pending_payment" | "draft">(
    "active",
  );
  const [autoOptimize, setAutoOptimize] = useState(true);
  const [listenerMode, setListenerMode] =
    useState<ListenerStatus["config"]["listener_mode"]>("simulation");
  const [listenerAggressiveness, setListenerAggressiveness] =
    useState<ListenerStatus["config"]["aggressiveness"]>("balanced");
  const [listenerReviewMode, setListenerReviewMode] =
    useState<ListenerStatus["config"]["review_mode"]>("manual");
  const [listenerTone, setListenerTone] = useState("");
  const [listenerStory, setListenerStory] = useState("");
  const [redditSubreddits, setRedditSubreddits] = useState("");
  const [twitterQueries, setTwitterQueries] = useState("");
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
      setStatus(
        response.status as "active" | "paused" | "pending_payment" | "draft",
      );
      setAutoOptimize(response.auto_optimize);
      setListenerStatus(nextListenerStatus);
      setListenerMode(nextListenerStatus.config.listener_mode);
      setListenerAggressiveness(nextListenerStatus.config.aggressiveness);
      setListenerReviewMode(nextListenerStatus.config.review_mode);
      setListenerTone(nextListenerStatus.brand_voice_profile.tone);
      setListenerStory(nextListenerStatus.brand_voice_profile.story);
      setRedditSubreddits(
        nextListenerStatus.config.surfaces
          .find((surface) => surface.type === "reddit")
          ?.subreddits.join("\n") ?? "",
      );
      setTwitterQueries(
        nextListenerStatus.config.surfaces
          .find((surface) => surface.type === "twitter")
          ?.search_queries.join("\n") ?? "",
      );
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to load settings.",
      );
    }
  }

  async function handleSaveSettings() {
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
          auto_optimize: autoOptimize,
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

  async function handleSaveListenerSettings() {
    if (!token || !campaign || !listenerStatus) {
      return;
    }
    setListenerSaving(true);
    try {
      const nextConfig = {
        ...listenerStatus.config,
        listener_mode: listenerMode,
        aggressiveness: listenerAggressiveness,
        review_mode: listenerReviewMode,
        thresholds:
          listenerAggressiveness === "conservative"
            ? { composite_min: 78, receptivity_min: 68 }
            : listenerAggressiveness === "aggressive"
              ? { composite_min: 58, receptivity_min: 48 }
              : { composite_min: 70, receptivity_min: 60 },
        surfaces: listenerStatus.config.surfaces.map((surface) =>
          surface.type === "reddit"
            ? {
                ...surface,
                subreddits: redditSubreddits
                  .split("\n")
                  .map((item) => item.trim())
                  .filter(Boolean),
              }
            : surface.type === "twitter"
              ? {
                  ...surface,
                  search_queries: twitterQueries
                    .split("\n")
                    .map((item) => item.trim())
                    .filter(Boolean),
                }
              : surface,
        ),
      };
      const nextBrandVoiceProfile = {
        ...listenerStatus.brand_voice_profile,
        tone: listenerTone,
        story: listenerStory,
      };
      const response = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
        method: "PUT",
        token,
        body: {
          brand_voice_profile: nextBrandVoiceProfile,
          config: nextConfig,
        },
      });
      setListenerStatus(response);
      setListenerMode(response.config.listener_mode);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to update listener settings.",
      );
    } finally {
      setListenerSaving(false);
    }
  }

  async function handleToggleListener(nextStatus: "start" | "stop") {
    if (!token || !campaign) {
      return;
    }
    setListenerSaving(true);
    try {
      const response = await apiRequest<ListenerStatus>(
        `/campaigns/${campaign.id}/listener/${nextStatus}`,
        {
          method: "POST",
          token,
        },
      );
      setListenerStatus(response);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : `Unable to ${nextStatus} the listener.`,
      );
    } finally {
      setListenerSaving(false);
    }
  }

  if (loading || !token || !campaign) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        {error ?? "Loading settings..."}
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AppHeader
        title="Settings"
        subtitle="Pause or resume campaigns, adjust budget, revisit products, and review billing."
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
              <h2 className="font-display text-2xl text-white">Budget and delivery</h2>

              <div className="mt-6 space-y-5">
                <div className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                  <label className="block space-y-3">
                    <span className="text-sm text-slate-300">Monthly compute budget</span>
                    <input
                      type="range"
                      min="100"
                      max="10000"
                      step="100"
                      value={budget}
                      onChange={(event) => setBudget(Number(event.target.value))}
                      className="w-full accent-emerald-400"
                    />
                    <div className="font-display text-4xl text-white">
                      {formatCurrency(budget)}
                    </div>
                  </label>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Status</span>
                    <select
                      value={status}
                      onChange={(event) =>
                        setStatus(
                          event.target.value as "active" | "paused" | "pending_payment" | "draft",
                        )
                      }
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    >
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                      <option value="pending_payment">Pending payment</option>
                      <option value="draft">Draft</option>
                    </select>
                  </label>

                  <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Optimization</span>
                    <div className="mt-4 flex items-center gap-3 rounded-[1rem] border border-white/10 bg-slate-950/60 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={autoOptimize}
                        onChange={(event) => setAutoOptimize(event.target.checked)}
                        className="h-4 w-4 accent-emerald-400"
                      />
                      <span className="text-sm text-slate-200">
                        Automatically allocate compute to highest-converting products
                      </span>
                    </div>
                  </label>
                </div>

                <button
                  onClick={handleSaveSettings}
                  disabled={saving}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {saving ? "Saving..." : "Save changes"}
                </button>
              </div>
            </section>

            {listenerStatus ? (
              <section className="panel p-6">
                <div className="flex flex-col gap-4 border-b border-white/8 pb-5 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="eyebrow">Intent listener</p>
                    <h2 className="font-display text-2xl text-white">Surfaces and review</h2>
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
                        void handleToggleListener(
                          listenerStatus.status === "running" ? "stop" : "start",
                        )
                      }
                      disabled={listenerSaving}
                      className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {listenerStatus.status === "running" ? "Stop listener" : "Start listener"}
                    </button>
                    <Link
                      href="/review"
                      className="rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100 transition hover:bg-blue-500/15"
                    >
                      Open review queue
                    </Link>
                  </div>
                </div>

                <div className="mt-6 space-y-5">
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <span className="text-sm text-slate-300">Signal source</span>
                      <select
                        value={listenerMode}
                        onChange={(event) =>
                          setListenerMode(
                            event.target.value as ListenerStatus["config"]["listener_mode"],
                          )
                        }
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      >
                        <option value="simulation">Simulation</option>
                        <option value="live">Live OpenClaw agent</option>
                      </select>
                      <p className="mt-3 text-sm leading-7 text-slate-400">
                        Simulation keeps the seeded demo flow alive. Live mode stops fake signal
                        generation and waits for real OpenClaw bridge events.
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
                    </label>
                    <label className="rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <span className="text-sm text-slate-300">Review mode</span>
                      <select
                        value={listenerReviewMode}
                        onChange={(event) =>
                          setListenerReviewMode(
                            event.target.value as ListenerStatus["config"]["review_mode"],
                          )
                        }
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      >
                        <option value="manual">Manual</option>
                        <option value="auto">Auto after 50 approvals</option>
                      </select>
                    </label>
                  </div>

                  <label className="block rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Listener tone</span>
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
                      rows={4}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>

                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="block rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <span className="text-sm text-slate-300">Reddit subreddits</span>
                      <textarea
                        value={redditSubreddits}
                        onChange={(event) => setRedditSubreddits(event.target.value)}
                        rows={7}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                    <label className="block rounded-[1.5rem] border border-white/8 bg-white/4 p-5">
                      <span className="text-sm text-slate-300">X search queries</span>
                      <textarea
                        value={twitterQueries}
                        onChange={(event) => setTwitterQueries(event.target.value)}
                        rows={7}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                  </div>

                  <button
                    onClick={handleSaveListenerSettings}
                    disabled={listenerSaving}
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {listenerSaving ? "Saving..." : "Save listener settings"}
                  </button>
                </div>
              </section>
            ) : null}
          </div>

          <div className="space-y-6">
            <section className="panel p-6">
              <p className="eyebrow">Products</p>
              <h2 className="font-display text-2xl text-white">Catalog management</h2>
              <p className="mt-3 text-sm leading-7 text-slate-400">
                Re-scan your store or revisit the onboarding review flow to update product
                attributes and agent-facing structured data.
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
                  View performance
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
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                    Payment method
                  </p>
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
                  <p className="text-sm text-slate-400">Signed in as</p>
                  <p className="text-lg text-white">{user?.email}</p>
                </div>
                <button
                  onClick={() => {
                    logout();
                    router.push("/");
                  }}
                  className="rounded-full border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 transition hover:bg-rose-500/15"
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
