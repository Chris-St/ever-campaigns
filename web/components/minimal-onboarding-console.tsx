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

export function MinimalOnboardingConsole() {
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
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [socialUrls, setSocialUrls] = useState("");

  const activeProducts = useMemo(
    () => products.filter((product) => product.status !== "paused"),
    [products],
  );
  const estimatedInteractions = Math.round(budget / 3.6);
  const estimatedConversions = Math.max(Math.round(budget / 28), 1);
  const estimatedRoc = 0.85 + budget / 120;
  const billingMode = checkoutResponse?.mode ?? campaign?.billing.mode ?? "self_funded";
  const selfFundedMode = billingMode === "self_funded";

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
    if (checkoutState === "cancel") {
      setError("Stripe checkout was canceled before the experiment was funded.");
      setStep(2);
      return;
    }
    const resolvedToken = token;
    const resolvedCampaignId = campaignId;

    let cancelled = false;
    async function finalizeCheckout() {
      setBusyLabel("Finalizing payment...");
      try {
        await loadCampaignExperience(resolvedCampaignId, resolvedToken);
      } catch {
        // keep polling
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
            // keep polling
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
    if (!products.some((product) => product.status !== "paused") && products.length > 0) {
      throw new Error("Choose at least one product for the experiment.");
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
    setBusyLabel(selfFundedMode ? "Starting experiment..." : "Opening Stripe Checkout...");
    setError(null);
    try {
      await persistExperimentSetup();
      const response = await apiRequest<BillingCheckoutResponse>("/billing/create-checkout", {
        method: "POST",
        token,
        body: { campaign_id: campaign.id },
      });
      setCheckoutResponse(response);
      if (response.activated && !response.checkout_url) {
        await loadCampaignExperience(campaign.id, token);
        await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/start`, {
          method: "POST",
          token,
        });
        startTransition(() => router.push("/dashboard"));
        return;
      }
      if (!response.checkout_url) {
        throw new Error("Unable to start the experiment.");
      }
      window.location.href = response.checkout_url;
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to start the experiment.");
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
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between">
          <Logo />
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
            {step === 1 ? "Connect store" : selfFundedMode ? "Launch" : "Fund and launch"}
          </p>
        </header>

        {error ? (
          <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        {step === 1 ? (
          <section className="panel p-6 sm:p-8">
            <p className="eyebrow">Start</p>
            <h1 className="font-display text-4xl text-white sm:text-5xl">Start one experiment.</h1>
            <p className="mt-3 max-w-2xl text-base leading-8 text-slate-300">
              Paste a store URL. Ever will scan the catalog and set up a live RoC experiment.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <input
                value={storeUrl}
                onChange={(event) => setStoreUrl(event.target.value)}
                placeholder="https://biaundies.com"
                className="min-w-0 flex-1 rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-4 text-white outline-none"
              />
              <button
                onClick={() => void handleScanStore()}
                disabled={Boolean(busyLabel)}
                className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {busyLabel ?? "Scan store"}
              </button>
            </div>
          </section>
        ) : null}

        {step === 2 && campaign && listenerStatus && brandVoice && brandContext ? (
          <section className="space-y-6">
            <section className="panel p-6">
              <p className="eyebrow">Experiment</p>
              <h2 className="font-display text-3xl text-white">One objective. One budget. One agent.</h2>
              <p className="mt-3 text-sm leading-7 text-slate-400">
                Pick the product set, dump useful context, set the compute cap, and launch.
              </p>
            </section>

            {products.length ? (
              <section className="panel p-6">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="eyebrow">Products</p>
                    <h3 className="text-xl text-white">{formatNumber(activeProducts.length)} in scope</h3>
                  </div>
                  <p className="text-sm text-slate-500">Start narrow.</p>
                </div>
                <div className="mt-4 space-y-3">
                  {products.map((product) => {
                    const active = product.status !== "paused";
                    return (
                      <article
                        key={product.id ?? product.name}
                        className={`rounded-[1.3rem] border p-4 ${
                          active ? "border-emerald-400/20 bg-emerald-500/8" : "border-white/8 bg-white/4"
                        }`}
                      >
                        <div className="flex items-center gap-4">
                          <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-[1rem] border border-white/10 bg-slate-950/70">
                            <Image
                              src={fallbackImageSrc(product.images[0])}
                              alt={product.name}
                              fill
                              className="object-cover"
                              sizes="64px"
                            />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-lg font-medium text-white">{product.name}</p>
                            <p className="text-sm text-slate-400">
                              {formatCurrency(product.price, product.currency)} • {product.category ?? "uncategorized"}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => updateProduct(product.id, active ? "paused" : "active")}
                            className={`rounded-full px-4 py-2 text-xs uppercase tracking-[0.22em] ${
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
              <p className="eyebrow">Context</p>
              <h3 className="text-xl text-white">Give the agent truth.</h3>
              <textarea
                value={brandContext.additional_context}
                onChange={(event) =>
                  setBrandContext((current) =>
                    current ? { ...current, additional_context: event.target.value } : current,
                  )
                }
                placeholder="Brand truth, positioning, offers, ideas, founder notes, things to try..."
                className="mt-4 min-h-[180px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-4 text-sm text-white outline-none"
              />
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                  <p className="text-sm font-medium text-white">Social URLs</p>
                  <textarea
                    value={socialUrls}
                    onChange={(event) => setSocialUrls(event.target.value)}
                    placeholder={"https://instagram.com/bia\nhttps://x.com/...\nhttps://tiktok.com/@..."}
                    className="mt-3 min-h-[120px] w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => void handleImportContextUrls()}
                    disabled={!socialUrls.trim() || Boolean(busyLabel)}
                    className="mt-3 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Import URLs
                  </button>
                </div>
                <div className="space-y-4">
                  <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                    <p className="text-sm font-medium text-white">Files</p>
                    <label className="mt-3 inline-flex cursor-pointer rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-white transition hover:bg-white/10">
                      Upload files
                      <input
                        type="file"
                        multiple
                        className="hidden"
                        onChange={(event) => void handleUploadFiles(event.target.files)}
                      />
                    </label>
                  </div>
                  <VoiceNoteCapture onComplete={handleUploadVoiceNote} disabled={Boolean(busyLabel)} />
                </div>
              </div>
              <div className="mt-4 rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-white">Context memory</p>
                  <span className="text-xs uppercase tracking-[0.22em] text-slate-500">
                    {formatNumber(contextItems.length)} items
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {contextItems.length ? (
                    contextItems.slice(0, 4).map((item) => (
                      <div key={item.id} className="rounded-[1rem] border border-white/8 bg-slate-950/50 px-4 py-3">
                        <p className="text-sm font-medium text-white">{item.title}</p>
                        <p className="mt-1 text-sm leading-6 text-slate-400">{item.summary}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500">No context yet.</p>
                  )}
                </div>
              </div>
            </section>

            <section className="panel p-6">
              <p className="eyebrow">Budget</p>
              <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="font-display text-5xl text-white">{formatCurrency(budget)}</p>
                  <p className="mt-2 text-sm text-slate-400">
                    ~{formatNumber(estimatedInteractions)} actions • ~{formatNumber(estimatedConversions)} conversions • ~{formatMultiplier(estimatedRoc)} target RoC
                  </p>
                </div>
                <label className="flex items-center gap-3 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={competitionEnabled}
                    onChange={(event) => setCompetitionEnabled(event.target.checked)}
                    className="h-4 w-4 rounded border-white/10 bg-slate-950/70 text-emerald-400"
                  />
                  Model competition
                </label>
              </div>
              <input
                type="range"
                min="50"
                max="10000"
                step="50"
                value={budget}
                onChange={(event) => setBudget(Number(event.target.value))}
                className="mt-4 w-full accent-emerald-400"
              />
              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-2">
                  <p className="text-sm text-slate-400">
                    Status: <span className="text-slate-200">{campaign.status.replaceAll("_", " ")}</span>
                  </p>
                  {checkoutResponse ? (
                    <p className="text-sm text-emerald-200">{checkoutResponse.message}</p>
                  ) : null}
                </div>
                <div className="flex flex-col gap-3 sm:items-end">
                  {campaign.status !== "active" ? (
                    <button
                      onClick={() => void handleActivateCampaign()}
                      disabled={Boolean(busyLabel)}
                      className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? (selfFundedMode ? `Start ${formatCurrency(budget)} experiment` : `Fund ${formatCurrency(budget)}`)}
                    </button>
                  ) : (
                    <button
                      onClick={() => void handleLaunchAgent()}
                      disabled={Boolean(busyLabel)}
                      className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? "Launch agent"}
                    </button>
                  )}
                </div>
              </div>
            </section>
          </section>
        ) : null}
      </div>
    </div>
  );
}
