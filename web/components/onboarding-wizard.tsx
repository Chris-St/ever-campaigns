"use client";

import Image from "next/image";
import { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Logo } from "@/components/logo";
import { VoiceNoteCapture } from "@/components/voice-note-capture";
import { apiRequest } from "@/lib/api";
import { setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  BillingCheckoutResponse,
  BrandContextProfile,
  BrandVoiceProfile,
  CampaignOverview,
  ContextItemRecord,
  ListenerStatus,
  StoreScanResponse,
  StructuredProduct,
} from "@/lib/types";

const stepLabels = ["Connect store", "Fund and launch"];

const aggressivenessProfiles = {
  conservative: { max_actions_per_day: 25, quality_threshold: 78 },
  balanced: { max_actions_per_day: 50, quality_threshold: 64 },
  aggressive: { max_actions_per_day: 100, quality_threshold: 52 },
} as const;

function defaultFocusedProducts(products: StructuredProduct[]) {
  return products.map((product, index) => ({
    ...product,
    status: index === 0 ? "active" : "paused",
  }));
}

export function OnboardingWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { token, loading, refreshUser } = useAuth();
  const [step, setStep] = useState(1);
  const [storeUrl, setStoreUrl] = useState("https://biaundies.com");
  const [scanResult, setScanResult] = useState<StoreScanResponse | null>(null);
  const [products, setProducts] = useState<StructuredProduct[]>([]);
  const [budget, setBudget] = useState(50);
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [brandVoice, setBrandVoice] = useState<BrandVoiceProfile | null>(null);
  const [brandContext, setBrandContext] = useState<BrandContextProfile | null>(null);
  const [contextItems, setContextItems] = useState<ContextItemRecord[]>([]);
  const [aggressiveness, setAggressiveness] =
    useState<ListenerStatus["config"]["aggressiveness"]>("balanced");
  const [competitionEnabled, setCompetitionEnabled] = useState(true);
  const [checkoutResponse, setCheckoutResponse] = useState<BillingCheckoutResponse | null>(null);
  const [chargeConfirmed, setChargeConfirmed] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [textNoteTitle, setTextNoteTitle] = useState("Founder brief");
  const [textNoteBody, setTextNoteBody] = useState("");
  const [socialUrls, setSocialUrls] = useState("");

  const activeProducts = useMemo(
    () => products.filter((product) => product.status !== "paused"),
    [products],
  );
  const estimatedInteractions = Math.round(budget / 3.6);
  const estimatedConversions = Math.max(Math.round(budget / 28), 1);
  const estimatedRoc = 0.85 + budget / 120;

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
    }
  }, [loading, router, token]);

  const loadCampaignExperience = useCallback(
    async (campaignId: string, resolvedToken: string) => {
      const [nextCampaign, nextListenerStatus, nextContextItems] = await Promise.all([
        apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, {
          method: "GET",
          token: resolvedToken,
        }),
        apiRequest<ListenerStatus>(`/campaigns/${campaignId}/listener/status`, {
          method: "GET",
          token: resolvedToken,
        }),
        apiRequest<ContextItemRecord[]>(`/campaigns/${campaignId}/context`, {
          method: "GET",
          token: resolvedToken,
        }),
      ]);
      setCampaign(nextCampaign);
      setActiveCampaignId(nextCampaign.id);
      setListenerStatus(nextListenerStatus);
      setBrandVoice(nextListenerStatus.brand_voice_profile);
      setBrandContext(nextListenerStatus.brand_context_profile);
      setAggressiveness(nextListenerStatus.config.aggressiveness);
      setCompetitionEnabled(nextListenerStatus.config.competition.enabled);
      setContextItems(nextContextItems);
      setBudget(nextCampaign.budget_monthly);
      setStep(2);
      await refreshUser(resolvedToken);
    },
    [refreshUser],
  );

  useEffect(() => {
    if (loading || !token) {
      return;
    }
    const checkoutState = searchParams.get("checkout");
    const campaignId = searchParams.get("campaign_id");
    if (!checkoutState || !campaignId) {
      return;
    }
    const resolvedCampaignId = campaignId;
    const resolvedToken = token;
    if (checkoutState === "cancel") {
      setError("Stripe checkout was canceled before the experiment was funded.");
      setStep(2);
      return;
    }

    let cancelled = false;
    async function finalizeCheckout() {
      setBusyLabel("Finalizing payment...");
      try {
        await loadCampaignExperience(resolvedCampaignId, resolvedToken);
      } catch {
        // Keep going even if the initial campaign reload lands before Stripe metadata settles.
      }
      for (let attempt = 0; attempt < 10; attempt += 1) {
        let nextCampaign = await apiRequest<CampaignOverview>(`/campaigns/${resolvedCampaignId}`, {
          method: "GET",
          token: resolvedToken,
        });
        if (cancelled) {
          return;
        }
        if (nextCampaign.status !== "active" && attempt >= 2) {
          try {
            const reconciliation = await apiRequest<BillingCheckoutResponse>("/billing/reconcile-checkout", {
              method: "POST",
              token: resolvedToken,
              body: { campaign_id: resolvedCampaignId },
            });
            if (reconciliation.activated) {
              nextCampaign = await apiRequest<CampaignOverview>(`/campaigns/${resolvedCampaignId}`, {
                method: "GET",
                token: resolvedToken,
              });
            }
          } catch {
            // If reconciliation fails, keep polling and let the webhook still resolve the state.
          }
        }
        if (nextCampaign.status === "active") {
          setCheckoutResponse({
            mode: nextCampaign.billing.mode,
            campaign_id: nextCampaign.id,
            activated: true,
            status: nextCampaign.status,
            message: "Stripe confirmed payment. Your budget is live.",
          });
          await loadCampaignExperience(resolvedCampaignId, resolvedToken);
          router.replace("/onboarding");
          setBusyLabel(null);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      if (!cancelled) {
        setBusyLabel(null);
        setError("Stripe completed, but Ever is still waiting on the webhook confirmation.");
        setStep(2);
      }
    }
    void finalizeCheckout();
    return () => {
      cancelled = true;
    };
  }, [loadCampaignExperience, loading, router, searchParams, token]);

  function updateProduct(productId: string | undefined, nextStatus: "active" | "paused") {
    setProducts((currentProducts) =>
      currentProducts.map((product) =>
        product.id === productId ? { ...product, status: nextStatus } : product,
      ),
    );
  }

  async function prepareExperiment(nextScanResult: StoreScanResponse, nextProducts: StructuredProduct[]) {
    if (!token) {
      return;
    }
    setBusyLabel("Preparing experiment...");
    setError(null);
    try {
      await apiRequest<StoreScanResponse>(`/stores/${nextScanResult.merchant_id}/products`, {
        method: "PUT",
        token,
        body: { products: nextProducts },
      });
      const nextCampaign = await apiRequest<CampaignOverview>("/campaigns/create", {
        method: "POST",
        token,
        body: {
          merchant_id: nextScanResult.merchant_id,
          budget_monthly: budget,
          auto_optimize: true,
        },
      });
      setCampaign(nextCampaign);
      setActiveCampaignId(nextCampaign.id);
      await loadCampaignExperience(nextCampaign.id, token);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to prepare the experiment.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleScanStore() {
    if (!token) {
      return;
    }
    setBusyLabel("Scanning store...");
    setError(null);
    try {
      const response = await apiRequest<StoreScanResponse>("/stores/scan", {
        method: "POST",
        token,
        body: { url: storeUrl },
      });
      const focusedProducts = defaultFocusedProducts(response.products);
      setScanResult(response);
      setProducts(focusedProducts);
      await prepareExperiment(response, focusedProducts);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to scan store.");
      setBusyLabel(null);
    }
  }

  async function persistExperimentSetup() {
    if (!token || !campaign || !listenerStatus || !brandVoice || !brandContext) {
      return;
    }
    if (!products.some((product) => product.status !== "paused")) {
      if (products.length > 0) {
        throw new Error("Choose at least one product for the experiment.");
      }
    }
    if (scanResult && products.length > 0) {
      await apiRequest<StoreScanResponse>(`/stores/${scanResult.merchant_id}/products`, {
        method: "PUT",
        token,
        body: { products },
      });
    }
    const nextCampaign = await apiRequest<CampaignOverview>(`/campaigns/${campaign.id}`, {
      method: "PUT",
      token,
      body: { budget_monthly: budget },
    });
    const profile = aggressivenessProfiles[aggressiveness];
    const nextListenerStatus = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
      method: "PUT",
      token,
      body: {
        brand_voice_profile: brandVoice,
        brand_context_profile: brandContext,
        config: {
          ...listenerStatus.config,
          listener_mode: "live",
          review_mode: "manual",
          aggressiveness,
          max_actions_per_day: profile.max_actions_per_day,
          quality_threshold: profile.quality_threshold,
          competition: {
            ...listenerStatus.config.competition,
            enabled: competitionEnabled,
            mode: competitionEnabled ? "best_of_n" : "single_lane",
          },
          safeguards: {
            ...listenerStatus.config.safeguards,
            max_actions_per_day: profile.max_actions_per_day,
          },
        },
      },
    });
    setCampaign(nextCampaign);
    setListenerStatus(nextListenerStatus);
  }

  async function handleActivateCampaign() {
    if (!token || !campaign) {
      return;
    }
    setBusyLabel("Opening Stripe Checkout...");
    setError(null);
    try {
      await persistExperimentSetup();
      const response = await apiRequest<BillingCheckoutResponse>("/billing/create-checkout", {
        method: "POST",
        token,
        body: { campaign_id: campaign.id },
      });
      setCheckoutResponse(response);
      if (!response.checkout_url) {
        throw new Error("Stripe did not return a checkout URL.");
      }
      window.location.href = response.checkout_url;
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to fund the experiment.");
      setBusyLabel(null);
    }
  }

  async function handleLaunchAgent() {
    if (!token || !campaign) {
      return;
    }
    setBusyLabel("Launching agent...");
    setError(null);
    try {
      await persistExperimentSetup();
      await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/start`, {
        method: "POST",
        token,
      });
      startTransition(() => router.push("/proposals"));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to launch the agent.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function refreshContextItems() {
    if (!token || !campaign) {
      return;
    }
    const nextContextItems = await apiRequest<ContextItemRecord[]>(`/campaigns/${campaign.id}/context`, {
      method: "GET",
      token,
    });
    setContextItems(nextContextItems);
  }

  async function handleAddContextNote(kind: "note" | "voice_note" | "brief", title: string, content: string) {
    if (!token || !campaign) {
      return;
    }
    const trimmedContent = content.trim();
    if (!trimmedContent) {
      return;
    }
    setBusyLabel(kind === "voice_note" ? "Saving voice note..." : "Saving context...");
    setError(null);
    try {
      await apiRequest<ContextItemRecord>(`/campaigns/${campaign.id}/context/notes`, {
        method: "POST",
        token,
        body: {
          title,
          content: trimmedContent,
          kind,
        },
      });
      await refreshContextItems();
      if (kind !== "voice_note") {
        setTextNoteBody("");
      }
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save context.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleUploadFiles(fileList: FileList | null) {
    if (!fileList || !token || !campaign) {
      return;
    }
    setBusyLabel("Uploading context...");
    setError(null);
    try {
      for (const file of Array.from(fileList)) {
        const formData = new FormData();
        formData.append("file", file);
        await apiRequest<ContextItemRecord>(`/campaigns/${campaign.id}/context/upload`, {
          method: "POST",
          token,
          body: formData,
        });
      }
      await refreshContextItems();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to upload context.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleImportContextUrls() {
    if (!token || !campaign) {
      return;
    }
    const urls = Array.from(
      new Set(
        socialUrls
          .split(/\n|,/)
          .map((value) => value.trim())
          .filter(Boolean),
      ),
    );
    if (!urls.length) {
      return;
    }
    setBusyLabel("Importing social context...");
    setError(null);
    try {
      for (const url of urls) {
        await apiRequest<ContextItemRecord>(`/campaigns/${campaign.id}/context/url`, {
          method: "POST",
          token,
          body: {
            url,
            kind: "social_profile",
          },
        });
      }
      setSocialUrls("");
      await refreshContextItems();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to import those social URLs.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleUploadVoiceNote(file: File) {
    if (!token || !campaign) {
      return;
    }
    setBusyLabel("Transcribing voice note...");
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await apiRequest<ContextItemRecord>(`/campaigns/${campaign.id}/context/voice`, {
        method: "POST",
        token,
        body: formData,
      });
      await refreshContextItems();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Unable to transcribe and save the voice note.";
      setError(message);
      throw caughtError instanceof Error ? caughtError : new Error(message);
    } finally {
      setBusyLabel(null);
    }
  }

  if (loading || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        Loading setup...
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between">
          <Logo />
          <div className="hidden gap-3 md:flex">
            {stepLabels.map((label, index) => {
              const isActive = step === index + 1;
              const isComplete = step > index + 1;
              return (
                <div
                  key={label}
                  className={`rounded-full px-4 py-2 text-xs uppercase tracking-[0.22em] ${
                    isActive
                      ? "bg-white text-slate-950"
                      : isComplete
                        ? "bg-emerald-500/12 text-emerald-100"
                        : "border border-white/10 bg-white/5 text-slate-400"
                  }`}
                >
                  {label}
                </div>
              );
            })}
          </div>
        </header>

        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        {step === 1 ? (
          <section className="panel grid gap-8 overflow-hidden p-6 sm:p-8 lg:grid-cols-[0.95fr_1.05fr]">
            <div className="space-y-6">
              <p className="eyebrow">Step 1</p>
              <h1 className="font-display text-4xl text-white sm:text-5xl">
                Scan the store. Let Ever set up the experiment.
              </h1>
              <p className="max-w-2xl text-base leading-8 text-slate-300">
                Paste the store URL. Ever will crawl the catalog, default to one hero product so the first
                experiment stays sharp, and prepare a paid propose-only agent that optimizes for RoC.
              </p>
              <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                <label className="block space-y-3">
                  <span className="text-sm text-slate-300">Store URL</span>
                  <input
                    value={storeUrl}
                    onChange={(event) => setStoreUrl(event.target.value)}
                    placeholder="https://biaundies.com"
                    className="w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-4 text-white outline-none"
                  />
                </label>
                <button
                  onClick={() => void handleScanStore()}
                  disabled={Boolean(busyLabel)}
                  className="mt-5 rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {busyLabel ?? "Scan store"}
                </button>
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(9,13,25,0.82))] p-6">
              <p className="eyebrow">Experiment shape</p>
              <div className="mt-5 space-y-4">
                {[
                  "One budget input. One payment step. One launch button.",
                  "Seed the agent with files, voice notes, and direct founder context.",
                  "Let the internet and the models figure out the tactic mix.",
                  "Keep every outbound action human-approved.",
                  "Judge the whole thing on sales versus compute cost.",
                ].map((item) => (
                  <div
                    key={item}
                    className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-slate-300"
                  >
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {step === 2 && campaign && listenerStatus && brandVoice && brandContext ? (
          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.04fr)_minmax(320px,0.96fr)]">
            <div className="min-w-0 space-y-6">
              <section className="panel p-6">
                <p className="eyebrow">Step 2</p>
                <h2 className="font-display text-3xl text-white">Brief, fund, and launch the experiment</h2>
                <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
                  Keep the first run tight. Start with the product you most want the agent to learn on, dump
                  every useful brand context file or voice note into the brief, and only then fund the budget.
                </p>
              </section>

              {products.length ? (
                <section className="panel p-6">
                  <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="eyebrow">Product focus</p>
                    <h3 className="font-display text-2xl text-white">
                      {formatNumber(activeProducts.length)} product{activeProducts.length === 1 ? "" : "s"} in scope
                    </h3>
                  </div>
                  <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-emerald-100">
                    Hero product first
                  </span>
                </div>
                <div className="mt-5 grid gap-4 2xl:grid-cols-2">
                  {products.map((product) => {
                    const active = product.status !== "paused";
                    return (
                      <article
                        key={product.id ?? product.name}
                        className={`overflow-hidden rounded-[1.5rem] border p-5 ${
                          active ? "border-emerald-400/20 bg-emerald-500/8" : "border-white/8 bg-white/4"
                        }`}
                      >
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                          <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-[1rem] border border-white/10 bg-slate-950/70">
                            <Image
                              src={fallbackImageSrc(product.images[0])}
                              alt={product.name}
                              fill
                              className="object-cover"
                              sizes="80px"
                            />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="max-w-[24rem] text-2xl font-medium leading-tight text-white">{product.name}</p>
                            <p className="mt-2 text-sm text-slate-400">
                              {formatCurrency(product.price, product.currency)} • {product.category ?? "uncategorized"}
                            </p>
                            <p className="mt-3 text-sm leading-7 text-slate-300">{product.description}</p>
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                            {active ? "Active in experiment" : "Paused"}
                          </p>
                          <button
                            type="button"
                            onClick={() => updateProduct(product.id, active ? "paused" : "active")}
                            className={`shrink-0 rounded-full px-4 py-2 text-xs uppercase tracking-[0.22em] ${
                              active
                                ? "bg-emerald-400 text-slate-950"
                                : "border border-white/10 bg-white/6 text-slate-200"
                            }`}
                          >
                            {active ? "Included" : "Include"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
                </section>
              ) : null}

              <section className="panel p-6">
                <p className="eyebrow">Agent brief</p>
                <h3 className="font-display text-2xl text-white">Give the agent more truth</h3>
                <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,0.98fr)_minmax(0,1.02fr)]">
                  <div className="space-y-5">
                    <label className="block space-y-3">
                      <span className="text-sm text-slate-300">Brand story</span>
                      <textarea
                        value={brandVoice.story}
                        onChange={(event) =>
                          setBrandVoice((current) => (current ? { ...current, story: event.target.value } : current))
                        }
                        className="min-h-[150px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                      />
                    </label>
                    <label className="block space-y-3">
                      <span className="text-sm text-slate-300">Direct operator brief</span>
                      <textarea
                        value={brandContext.additional_context}
                        onChange={(event) =>
                          setBrandContext((current) =>
                            current ? { ...current, additional_context: event.target.value } : current,
                          )
                        }
                        placeholder="What should the agent know about the brand, product truth, constraints, or ideal customer?"
                        className="min-h-[180px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                      />
                    </label>

                    <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                      <p className="text-sm font-medium text-white">Social and brand URLs</p>
                      <p className="mt-2 text-sm leading-7 text-slate-400">
                        Paste Instagram, TikTok, X, Reddit, YouTube, creator pages, founder posts, or any public brand URLs. Ever will pull the visible context into memory.
                      </p>
                      <textarea
                        value={socialUrls}
                        onChange={(event) => setSocialUrls(event.target.value)}
                        placeholder={"https://instagram.com/bia\nhttps://tiktok.com/@bia\nhttps://x.com/..." }
                        className="mt-3 min-h-[130px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => void handleImportContextUrls()}
                        disabled={!socialUrls.trim() || Boolean(busyLabel)}
                        className="mt-3 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Import social context
                      </button>
                    </div>
                  </div>

                  <div className="space-y-5">
                    <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                      <p className="text-sm font-medium text-white">Upload files</p>
                      <p className="mt-2 text-sm leading-7 text-slate-400">
                        Drag in founder notes, product docs, FAQs, or campaign briefs. Ever stores the extracted text and feeds it back into the planner.
                      </p>
                      <label className="mt-4 inline-flex cursor-pointer rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10">
                        Upload context files
                        <input
                          type="file"
                          multiple
                          className="hidden"
                          onChange={(event) => void handleUploadFiles(event.target.files)}
                        />
                      </label>
                    </div>

                    <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                      <p className="text-sm font-medium text-white">Quick note</p>
                      <input
                        value={textNoteTitle}
                        onChange={(event) => setTextNoteTitle(event.target.value)}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                      />
                      <textarea
                        value={textNoteBody}
                        onChange={(event) => setTextNoteBody(event.target.value)}
                        placeholder="Type any extra context you want the planner to internalize."
                        className="mt-3 min-h-[120px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => void handleAddContextNote("brief", textNoteTitle, textNoteBody)}
                        disabled={!textNoteBody.trim()}
                        className="mt-3 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Save note
                      </button>
                    </div>

                    <VoiceNoteCapture onComplete={handleUploadVoiceNote} disabled={Boolean(busyLabel)} />
                  </div>
                </div>

                <div className="mt-5 rounded-[1.4rem] border border-white/8 bg-slate-950/50 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="text-sm font-medium text-white">Seeded context</p>
                    <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
                      {formatNumber(contextItems.length)} items
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {contextItems.length ? (
                      contextItems.slice(0, 6).map((item) => (
                        <div key={item.id} className="rounded-[1rem] border border-white/8 bg-white/4 px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-medium text-white">{item.title}</p>
                            <span className="text-xs uppercase tracking-[0.22em] text-slate-500">{item.kind.replace("_", " ")}</span>
                          </div>
                          <p className="mt-2 text-sm leading-7 text-slate-400">{item.summary}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-500">No uploaded or recorded context yet.</p>
                    )}
                  </div>
                </div>
              </section>
            </div>

            <div className="min-w-0 space-y-6 xl:sticky xl:top-6 xl:self-start">
              <section className="panel p-6">
                <p className="eyebrow">Budget</p>
                <h3 className="font-display text-2xl text-white">Fund the objective, not the tactic</h3>
                <div className="mt-5 rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                  <input
                    type="range"
                    min="50"
                    max="10000"
                    step="50"
                    value={budget}
                    onChange={(event) => setBudget(Number(event.target.value))}
                    className="w-full accent-emerald-400"
                  />
                  <div className="mt-4 flex items-end justify-between gap-4">
                    <p className="font-display text-5xl text-white">{formatCurrency(budget)}</p>
                    <div className="text-right text-sm text-slate-400">
                      <p>~{formatNumber(estimatedInteractions)} candidate actions</p>
                      <p>~{formatNumber(estimatedConversions)} conversions</p>
                      <p>~{formatMultiplier(estimatedRoc)} target RoC</p>
                    </div>
                  </div>
                </div>
              </section>

              <section className="panel p-6">
                <p className="eyebrow">Models</p>
                <h3 className="font-display text-2xl text-white">Let models compete for RoC</h3>
                <div className="mt-5 rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                  <label className="flex items-start gap-3 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={competitionEnabled}
                      onChange={(event) => setCompetitionEnabled(event.target.checked)}
                      className="mt-1 h-4 w-4 rounded border-white/10 bg-slate-950/70 text-emerald-400"
                    />
                    <span>
                      Run model competition. Ever will let multiple planning lanes search and propose, then rank their ideas by expected Return on Compute.
                    </span>
                  </label>
                  <div className="mt-4 grid gap-3">
                    {listenerStatus.config.competition.lanes.map((lane) => (
                      <div key={lane.id} className="rounded-[1rem] border border-white/8 bg-slate-950/50 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-white">{lane.label}</p>
                          <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                            {lane.available ? lane.role : "Unavailable"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="panel p-6">
                <p className="eyebrow">Launch</p>
                <h3 className="font-display text-2xl text-white">Real-money experiment</h3>
                <div className="mt-5 rounded-[1.6rem] border border-amber-400/20 bg-amber-500/10 p-5 text-sm leading-7 text-amber-100">
                  <p>You are about to fund a real paid experiment.</p>
                  <p>Budget: {formatCurrency(budget)}</p>
                  <p>Objective: keep sales above compute cost.</p>
                  <p>All outbound actions stay human-approved and manually executed.</p>
                </div>
                <label className="mt-4 flex items-start gap-3 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={chargeConfirmed}
                    onChange={(event) => setChargeConfirmed(event.target.checked)}
                    className="mt-1 h-4 w-4 rounded border-white/10 bg-slate-950/70 text-emerald-400"
                  />
                  <span>I understand this launches a real paid experiment.</span>
                </label>

                <div className="mt-5 space-y-3">
                  {campaign.status !== "active" ? (
                    <button
                      onClick={() => void handleActivateCampaign()}
                      disabled={Boolean(busyLabel) || !chargeConfirmed}
                      className="w-full rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? `Pay and fund ${formatCurrency(budget)}`}
                    </button>
                  ) : (
                    <button
                      onClick={() => void handleLaunchAgent()}
                      disabled={Boolean(busyLabel)}
                      className="w-full rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? "Launch agent"}
                    </button>
                  )}
                  <p className="text-sm leading-7 text-slate-400">
                    Status: <span className="text-slate-200">{campaign.status.replaceAll("_", " ")}</span>
                  </p>
                  {checkoutResponse ? (
                    <p className="text-sm leading-7 text-emerald-200">{checkoutResponse.message}</p>
                  ) : null}
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
