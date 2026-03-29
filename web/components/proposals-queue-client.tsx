"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { getActiveCampaignId, setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber, formatPercent } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type { CampaignOverview, ListenerStatus, ProposalRecord } from "@/lib/types";

type ProposalFilter =
  | "all"
  | "proposed"
  | "approved"
  | "executed_manually"
  | "outcome_recorded"
  | "rejected";
type ProposalSort = "newest" | "intent" | "product";

function intentTone(score: number) {
  if (score >= 70) {
    return "border-emerald-400/20 bg-emerald-500/10 text-emerald-100";
  }
  if (score >= 50) {
    return "border-amber-400/20 bg-amber-500/10 text-amber-100";
  }
  return "border-rose-400/20 bg-rose-500/10 text-rose-100";
}

function confidenceTone(confidence: ProposalRecord["attribution_confidence"]) {
  if (confidence === "confirmed") {
    return "border-emerald-400/20 bg-emerald-500/10 text-emerald-100";
  }
  if (confidence === "estimated") {
    return "border-amber-400/20 bg-amber-500/10 text-amber-100";
  }
  return "border-white/10 bg-white/6 text-slate-300";
}

export function ProposalsQueueClient() {
  const router = useRouter();
  const { token, user, loading } = useAuth();
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [proposals, setProposals] = useState<ProposalRecord[]>([]);
  const [filter, setFilter] = useState<ProposalFilter>("all");
  const [sort, setSort] = useState<ProposalSort>("newest");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({});
  const [executionNotes, setExecutionNotes] = useState<Record<string, string>>({});
  const [outcomes, setOutcomes] = useState<Record<string, string>>({});
  const [outcomeNotes, setOutcomeNotes] = useState<Record<string, string>>({});
  const storedCampaignId = user ? getActiveCampaignId() : null;
  const campaignId = user
    ? user.campaigns.find((campaignItem) => campaignItem.id === storedCampaignId)?.id ??
      user.campaigns[0]?.id ??
      null
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
        const [nextCampaign, nextStatus, nextProposals] = await Promise.all([
          apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, { method: "GET", token }),
          apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, { method: "GET", token }),
          apiRequest<ProposalRecord[]>(
            `/campaigns/${campaignId}/proposals?status=${filter}&sort=${sort}`,
            { method: "GET", token },
          ),
        ]);
        if (cancelled) {
          return;
        }
        setCampaign(nextCampaign);
        setListenerStatus(nextStatus);
        setProposals(nextProposals);
        setDrafts((current) => {
          const merged = { ...current };
          for (const proposal of nextProposals) {
            merged[proposal.id] = merged[proposal.id] ?? proposal.proposed_response;
          }
          return merged;
        });
        setOutcomes((current) => {
          const merged = { ...current };
          for (const proposal of nextProposals) {
            merged[proposal.id] = merged[proposal.id] ?? proposal.outcome ?? "clicked";
          }
          return merged;
        });
        setError(null);
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            caughtError instanceof Error ? caughtError.message : "Unable to load proposals.",
          );
        }
      }
    }

    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [campaignId, filter, sort, token]);

  async function refresh() {
    if (!token || !campaignId) {
      return;
    }
    const [nextCampaign, nextStatus, nextProposals] = await Promise.all([
      apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, { method: "GET", token }),
      apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, { method: "GET", token }),
      apiRequest<ProposalRecord[]>(
        `/campaigns/${campaignId}/proposals?status=${filter}&sort=${sort}`,
        { method: "GET", token },
      ),
    ]);
    setCampaign(nextCampaign);
    setListenerStatus(nextStatus);
    setProposals(nextProposals);
  }

  async function handleApprove(proposalId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(proposalId);
    try {
      await apiRequest<ProposalRecord>(`/campaigns/${campaignId}/proposals/${proposalId}/approve`, {
        method: "POST",
        token,
      });
      await refresh();
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to approve proposal.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(proposalId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(proposalId);
    try {
      await apiRequest<ProposalRecord>(`/campaigns/${campaignId}/proposals/${proposalId}/reject`, {
        method: "POST",
        token,
        body: { reason: rejectionReasons[proposalId] ?? "" },
      });
      await refresh();
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to reject proposal.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleEdit(proposalId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(proposalId);
    try {
      await apiRequest<ProposalRecord>(`/campaigns/${campaignId}/proposals/${proposalId}/edit`, {
        method: "PUT",
        token,
        body: { proposed_response: drafts[proposalId] ?? "" },
      });
      await refresh();
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save proposal edit.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleExecuted(proposalId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(proposalId);
    try {
      await apiRequest<ProposalRecord>(`/campaigns/${campaignId}/proposals/${proposalId}/executed`, {
        method: "POST",
        token,
        body: { notes: executionNotes[proposalId] ?? "" },
      });
      await refresh();
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to mark proposal executed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleOutcome(proposalId: string) {
    if (!token || !campaignId) {
      return;
    }
    setBusyId(proposalId);
    try {
      await apiRequest<ProposalRecord>(`/campaigns/${campaignId}/proposals/${proposalId}/outcome`, {
        method: "POST",
        token,
        body: {
          outcome: outcomes[proposalId] ?? "clicked",
          notes: outcomeNotes[proposalId] ?? "",
        },
      });
      await refresh();
      setError(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to record proposal outcome.");
    } finally {
      setBusyId(null);
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

  if (loading || !token || !campaignId || !campaign || !listenerStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        Loading proposals...
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AppHeader
        title="Proposals"
        subtitle="Approve every outbound action, execute it manually, and record what happened so Ever can measure real Return on Compute."
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-4">
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Pending proposals</p>
            <p className="mt-3 font-display text-3xl text-white">{formatNumber(campaign.proposals.pending)}</p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Approved</p>
            <p className="mt-3 font-display text-3xl text-white">{formatNumber(campaign.proposals.approved)}</p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Executed</p>
            <p className="mt-3 font-display text-3xl text-white">{formatNumber(campaign.proposals.executed)}</p>
          </div>
          <div className="panel p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">RoC</p>
            <p className="mt-3 font-display text-3xl text-white">{formatMultiplier(campaign.return_on_compute)}</p>
          </div>
        </div>

        <section className="panel p-6">
          <div className="flex flex-col gap-4 border-b border-white/8 pb-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="eyebrow">Operator queue</p>
              <h2 className="font-display text-2xl text-white">
                {formatNumber(campaign.proposals.pending)} proposals pending approval
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
                The live agent is running in <span className="text-slate-200">{listenerStatus.operating_mode}</span> mode.
                Every outbound action stays human-gated.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <select
                value={filter}
                onChange={(event) => setFilter(event.target.value as ProposalFilter)}
                className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none"
              >
                <option value="all">All</option>
                <option value="proposed">Pending</option>
                <option value="approved">Approved</option>
                <option value="executed_manually">Executed</option>
                <option value="outcome_recorded">Outcome recorded</option>
                <option value="rejected">Rejected</option>
              </select>
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value as ProposalSort)}
                className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none"
              >
                <option value="newest">Newest</option>
                <option value="intent">Highest intent</option>
                <option value="product">By product</option>
              </select>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            {proposals.length ? (
              proposals.map((proposal) => {
                const composite = Number(proposal.intent_score.composite ?? 0);
                const isBusy = busyId === proposal.id;
                return (
                  <article
                    key={proposal.id}
                    className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.2em] ${intentTone(composite)}`}>
                        Intent {Math.round(composite)}
                      </span>
                      <span className="rounded-full border border-white/10 bg-slate-950/60 px-3 py-2 text-xs uppercase tracking-[0.2em] text-slate-300">
                        {proposal.surface ?? "other"}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-xs uppercase tracking-[0.2em] text-slate-300">
                        {proposal.action_type}
                      </span>
                      {proposal.model_provider ? (
                        <span className="rounded-full border border-fuchsia-400/20 bg-fuchsia-500/10 px-3 py-2 text-xs uppercase tracking-[0.2em] text-fuchsia-100">
                          {proposal.model_provider} {proposal.model_name ?? ""}
                        </span>
                      ) : null}
                      {proposal.competition_score ? (
                        <span className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-xs uppercase tracking-[0.2em] text-blue-100">
                          Score {Math.round(proposal.competition_score)}
                        </span>
                      ) : null}
                      <span className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.2em] ${confidenceTone(proposal.attribution_confidence)}`}>
                        {proposal.attribution_confidence}
                      </span>
                      <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                        {proposal.relative_time}
                      </span>
                    </div>

                    <div className="mt-4 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
                      <div className="space-y-4">
                        <div>
                          <p className="text-sm font-medium text-white">Source</p>
                          <p className="mt-2 text-sm leading-7 text-slate-300">
                            {proposal.source_content ?? "No source content provided."}
                          </p>
                          {proposal.source_context ? (
                            <p className="mt-2 text-sm leading-7 text-slate-400">{proposal.source_context}</p>
                          ) : null}
                          {proposal.source_url ? (
                            <a
                              href={proposal.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-3 inline-flex text-sm text-emerald-200 hover:text-emerald-100"
                            >
                              Open source
                            </a>
                          ) : null}
                        </div>

                        <div>
                          <p className="text-sm font-medium text-white">Proposed response</p>
                          <textarea
                            value={drafts[proposal.id] ?? proposal.proposed_response}
                            onChange={(event) =>
                              setDrafts((current) => ({ ...current, [proposal.id]: event.target.value }))
                            }
                            disabled={proposal.status !== "proposed"}
                            rows={6}
                            className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm leading-7 text-white outline-none disabled:opacity-75"
                          />
                        </div>

                        {proposal.rationale ? (
                          <div>
                            <p className="text-sm font-medium text-white">Rationale</p>
                            <p className="mt-2 text-sm leading-7 text-slate-400">{proposal.rationale}</p>
                          </div>
                        ) : null}
                      </div>

                      <div className="space-y-4">
                        <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/55 p-4">
                          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Product</p>
                          <div className="mt-3 flex items-center gap-4">
                            <div className="relative h-16 w-16 overflow-hidden rounded-[1rem] border border-white/10 bg-white/5">
                              <Image
                                src={fallbackImageSrc(proposal.product_image)}
                                alt={proposal.product_name ?? "Product"}
                                fill
                                className="object-cover"
                                sizes="64px"
                              />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-white">{proposal.product_name ?? "Unlinked product"}</p>
                              {proposal.product_price != null ? (
                                <p className="mt-1 text-sm text-slate-400">
                                  {formatCurrency(proposal.product_price, proposal.product_currency ?? "USD")}
                                </p>
                              ) : null}
                            </div>
                          </div>
                        </div>

                        <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/55 p-4">
                          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Tracked link</p>
                          <p className="mt-3 break-all text-sm text-slate-300">{proposal.referral_url ?? "No tracked link yet"}</p>
                          <div className="mt-4 flex flex-wrap gap-2">
                            <button
                              onClick={() => void handleCopy(`response-${proposal.id}`, drafts[proposal.id] ?? proposal.proposed_response)}
                              className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white"
                            >
                              {copiedField === `response-${proposal.id}` ? "Copied" : "Copy response"}
                            </button>
                            <button
                              onClick={() => void handleCopy(`link-${proposal.id}`, proposal.referral_url)}
                              className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white"
                            >
                              {copiedField === `link-${proposal.id}` ? "Copied" : "Copy link"}
                            </button>
                          </div>
                        </div>

                        <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/55 p-4">
                          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Proposal stats</p>
                          <p className="mt-3 text-sm text-slate-300">
                            {formatNumber(proposal.clicks)} clicks • {formatNumber(proposal.conversions)} conversions • {formatCurrency(proposal.revenue)}
                          </p>
                          <p className="mt-2 text-sm text-slate-400">
                            Compute cost {formatCurrency(proposal.compute_cost_usd)}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 border-t border-white/8 pt-5">
                      {proposal.status === "proposed" ? (
                        <div className="space-y-4">
                          <label className="block">
                            <span className="text-sm text-slate-300">Optional rejection reason</span>
                            <input
                              value={rejectionReasons[proposal.id] ?? ""}
                              onChange={(event) =>
                                setRejectionReasons((current) => ({ ...current, [proposal.id]: event.target.value }))
                              }
                              className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                            />
                          </label>
                          <div className="flex flex-wrap gap-3">
                            <button
                              onClick={() => void handleEdit(proposal.id)}
                              disabled={isBusy}
                              className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200"
                            >
                              Save edit
                            </button>
                            <button
                              onClick={() => void handleApprove(proposal.id)}
                              disabled={isBusy}
                              className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => void handleReject(proposal.id)}
                              disabled={isBusy}
                              className="rounded-full border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
                            >
                              Reject
                            </button>
                          </div>
                        </div>
                      ) : null}

                      {proposal.status === "approved" ? (
                        <div className="space-y-4">
                          <div className="rounded-[1.3rem] border border-white/8 bg-slate-950/55 p-4">
                            <p className="text-sm font-medium text-white">Execution instructions</p>
                            <p className="mt-3 text-sm leading-7 text-slate-300">
                              {proposal.execution_instructions ?? "Open the source, post the response, and use the tracked link."}
                            </p>
                          </div>
                          <label className="block">
                            <span className="text-sm text-slate-300">Execution notes</span>
                            <textarea
                              value={executionNotes[proposal.id] ?? ""}
                              onChange={(event) =>
                                setExecutionNotes((current) => ({ ...current, [proposal.id]: event.target.value }))
                              }
                              rows={3}
                              className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                            />
                          </label>
                          <button
                            onClick={() => void handleExecuted(proposal.id)}
                            disabled={isBusy}
                            className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950"
                          >
                            Mark as executed
                          </button>
                        </div>
                      ) : null}

                      {proposal.status === "executed_manually" ? (
                        <div className="space-y-4">
                          <div className="grid gap-4 md:grid-cols-2">
                            <label className="block">
                              <span className="text-sm text-slate-300">Outcome</span>
                              <select
                                value={outcomes[proposal.id] ?? "clicked"}
                                onChange={(event) =>
                                  setOutcomes((current) => ({ ...current, [proposal.id]: event.target.value }))
                                }
                                className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                              >
                                <option value="clicked">Clicked</option>
                                <option value="converted">Converted</option>
                                <option value="no_response">No response</option>
                                <option value="negative_response">Negative response</option>
                                <option value="other">Other</option>
                              </select>
                            </label>
                            <label className="block">
                              <span className="text-sm text-slate-300">Outcome notes</span>
                              <textarea
                                value={outcomeNotes[proposal.id] ?? ""}
                                onChange={(event) =>
                                  setOutcomeNotes((current) => ({ ...current, [proposal.id]: event.target.value }))
                                }
                                rows={3}
                                className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                              />
                            </label>
                          </div>
                          <button
                            onClick={() => void handleOutcome(proposal.id)}
                            disabled={isBusy}
                            className="rounded-full bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950"
                          >
                            Save outcome
                          </button>
                        </div>
                      ) : null}

                      {proposal.status === "rejected" && proposal.rejection_reason ? (
                        <p className="text-sm leading-7 text-slate-400">
                          Rejection reason: {proposal.rejection_reason}
                        </p>
                      ) : null}

                      {proposal.status === "outcome_recorded" ? (
                        <div className="rounded-[1.3rem] border border-emerald-400/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
                          Outcome recorded: {proposal.outcome ?? "unknown"}.
                          {proposal.outcome_notes ? ` ${proposal.outcome_notes}` : ""}
                        </div>
                      ) : null}
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-5 text-sm leading-7 text-slate-400">
                No proposals match this filter yet. If the live agent is running, refresh in a few seconds.
              </div>
            )}
          </div>
        </section>

        <section className="panel p-6">
          <p className="eyebrow">Attribution confidence</p>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            {[
              ["Confirmed", campaign.attribution_confidence.confirmed],
              ["Estimated", campaign.attribution_confidence.estimated],
              ["Unattributed", campaign.attribution_confidence.unattributed],
            ].map(([label, value]) => (
              <div key={label} className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
                <p className="mt-3 font-display text-3xl text-white">{formatNumber(Number(value))}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm leading-7 text-slate-400">
            Approval rate: {formatPercent(campaign.proposals.total ? campaign.proposals.approved / campaign.proposals.total : 0)}.
            Execution rate: {formatPercent(campaign.proposals.approved ? campaign.proposals.executed / campaign.proposals.approved : 0)}.
          </p>
        </section>
      </main>
    </div>
  );
}
