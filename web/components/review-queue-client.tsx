"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { ListenerStatus, ReviewQueueItem } from "@/lib/types";

export function ReviewQueueClient() {
  const router = useRouter();
  const { token, user, loading } = useAuth();
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
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
    async function loadReviewData() {
      try {
        const [nextStatus, nextQueue] = await Promise.all([
          apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
            method: "GET",
            token,
          }),
          apiRequest<ReviewQueueItem[]>(`/campaigns/${campaignId}/review`, {
            method: "GET",
            token,
          }),
        ]);

        if (cancelled) {
          return;
        }

        setListenerStatus(nextStatus);
        setItems(nextQueue);
        setDrafts(
          Object.fromEntries(nextQueue.map((item) => [item.response_id, item.response_text])),
        );
        setError(null);
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            caughtError instanceof Error ? caughtError.message : "Unable to load the review queue.",
          );
        }
      }
    }

    void loadReviewData();
    const interval = window.setInterval(() => {
      void loadReviewData();
    }, 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [campaignId, token]);

  async function refreshQueue() {
    if (!token || !campaignId) {
      return;
    }
    const [nextStatus, nextQueue] = await Promise.all([
      apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
        method: "GET",
        token,
      }),
      apiRequest<ReviewQueueItem[]>(`/campaigns/${campaignId}/review`, {
        method: "GET",
        token,
      }),
    ]);
    setListenerStatus(nextStatus);
    setItems(nextQueue);
    setDrafts(Object.fromEntries(nextQueue.map((item) => [item.response_id, item.response_text])));
  }

  async function handleStartListener() {
    if (!token || !campaignId) {
      return;
    }
    setBusyId("start");
    try {
      await apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/start`, {
        method: "POST",
        token,
      });
      await refreshQueue();
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to start the listener.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handleApprove(responseId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(responseId);
    try {
      await apiRequest<ReviewQueueItem>(`/campaigns/${campaignId}/review/${responseId}/approve`, {
        method: "POST",
        token,
      });
      await refreshQueue();
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to approve the response.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(responseId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(responseId);
    try {
      await apiRequest<ReviewQueueItem>(`/campaigns/${campaignId}/review/${responseId}/reject`, {
        method: "POST",
        token,
      });
      await refreshQueue();
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to reject the response.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handleSaveEdit(responseId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(responseId);
    try {
      await apiRequest<ReviewQueueItem>(`/campaigns/${campaignId}/review/${responseId}/edit`, {
        method: "POST",
        token,
        body: { response_text: drafts[responseId] ?? "" },
      });
      await refreshQueue();
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to save edits.",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (loading || !token || !campaignId || !listenerStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        {error ?? "Loading review queue..."}
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AppHeader
        title="Human Review"
        subtitle="Optional approval queue for responses that need a second look before the autonomous agent publishes them."
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-4">
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Listener status</p>
            <p className="mt-3 font-display text-3xl text-white">{listenerStatus.status}</p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Pending review</p>
            <p className="mt-3 font-display text-3xl text-white">
              {formatNumber(listenerStatus.responses_pending_review)}
            </p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Approved so far</p>
            <p className="mt-3 font-display text-3xl text-white">
              {formatNumber(listenerStatus.approved_response_count)}
            </p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Compute today</p>
            <p className="mt-3 font-display text-3xl text-white">
              {formatCurrency(listenerStatus.compute_spent_today)}
            </p>
          </div>
        </div>

        {listenerStatus.status === "stopped" ? (
          <section className="panel p-6">
            <p className="eyebrow">Agent offline</p>
            <h2 className="font-display text-2xl text-white">Launch the autonomous agent</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
              This queue only fills when the agent surfaces responses that still need human approval.
              Launch it first, then come back here if you want to edit or approve anything sensitive.
            </p>
            <button
              onClick={handleStartListener}
              disabled={busyId === "start"}
              className="mt-6 rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {busyId === "start" ? "Launching..." : "Launch agent"}
            </button>
          </section>
        ) : null}

        <section className="panel p-6">
          <div className="flex flex-col gap-3 border-b border-white/8 pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Responses awaiting approval</p>
              <h2 className="font-display text-2xl text-white">
                Manual review for edge-case responses
              </h2>
            </div>
            <Link
              href="/settings"
              className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
            >
              Adjust agent settings
            </Link>
          </div>

          <div className="mt-6 space-y-4">
            {items.length ? (
              items.map((item) => (
                <article
                  key={item.response_id}
                  className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5"
                >
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="space-y-4 xl:max-w-[44%]">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-white/10 bg-slate-950/60 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-300">
                          {item.surface}
                        </span>
                        {item.subreddit_or_channel ? (
                          <span className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-100">
                            {item.subreddit_or_channel}
                          </span>
                        ) : null}
                        <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                          {item.relative_time}
                        </span>
                      </div>
                      <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/45 p-4">
                        <p className="text-sm font-medium text-white">Detected intent</p>
                        <p className="mt-3 text-sm leading-7 text-slate-200">{item.content_text}</p>
                        {item.context_text ? (
                          <p className="mt-3 text-sm leading-7 text-slate-400">{item.context_text}</p>
                        ) : null}
                      </div>
                      <div className="grid gap-3 sm:grid-cols-3">
                        {[
                          { label: "Composite", value: Number(item.intent_score.composite ?? 0) },
                          { label: "Fit", value: Number(item.intent_score.fit ?? 0) },
                          { label: "Receptivity", value: Number(item.intent_score.receptivity ?? 0) },
                        ].map((metric) => (
                          <div
                            key={metric.label}
                            className="rounded-[1.2rem] border border-white/8 bg-white/4 p-3"
                          >
                            <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">
                              {metric.label}
                            </p>
                            <p className="mt-2 font-display text-2xl text-white">
                              {formatNumber(metric.value)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-4 xl:w-[56%]">
                      <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/45 p-4">
                        <div className="flex items-center justify-between gap-4">
                          <p className="text-sm font-medium text-white">
                            Proposed response{item.product_name ? ` for ${item.product_name}` : ""}
                          </p>
                          <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-emerald-100">
                            {item.confidence.toFixed(0)} confidence
                          </span>
                        </div>
                        <textarea
                          value={drafts[item.response_id] ?? item.response_text}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [item.response_id]: event.target.value,
                            }))
                          }
                          rows={6}
                          className="mt-4 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </div>

                      <div className="flex flex-wrap gap-3">
                        <button
                          onClick={() => void handleSaveEdit(item.response_id)}
                          disabled={busyId === item.response_id}
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          Save edit
                        </button>
                        <button
                          onClick={() => void handleApprove(item.response_id)}
                          disabled={busyId === item.response_id}
                          className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          Approve and post
                        </button>
                        <button
                          onClick={() => void handleReject(item.response_id)}
                          disabled={busyId === item.response_id}
                          className="rounded-full border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 transition hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          Reject
                        </button>
                        {item.content_url ? (
                          <a
                            href={item.content_url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                          >
                            View original post
                          </a>
                        ) : null}
                        {item.product_id ? (
                          <Link
                            href={`/products/${item.product_id}`}
                            className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                          >
                            View product
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="rounded-[1.7rem] border border-white/8 bg-white/4 p-6 text-sm leading-7 text-slate-400">
                No responses are waiting for approval right now. Most autonomous activity can flow
                without manual intervention, and anything that does need a second look will appear here.
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
