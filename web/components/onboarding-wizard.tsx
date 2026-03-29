"use client";

import { startTransition, useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";

import { Logo } from "@/components/logo";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { linesToList, listToLines } from "@/lib/agent-brain";
import { setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  BillingCheckoutResponse,
  BrandContextProfile,
  BrandVoiceProfile,
  CampaignOverview,
  ListenerStatus,
  StoreScanResponse,
  StructuredProduct,
} from "@/lib/types";

const stepLabels = [
  "Connect store",
  "Review products",
  "Set budget",
  "Add payment",
  "Review agent",
];

const aggressivenessProfiles = {
  conservative: { max_actions_per_day: 25, quality_threshold: 78 },
  balanced: { max_actions_per_day: 50, quality_threshold: 64 },
  aggressive: { max_actions_per_day: 100, quality_threshold: 52 },
} as const;

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
  const [checkoutResponse, setCheckoutResponse] = useState<BillingCheckoutResponse | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [brandVoice, setBrandVoice] = useState<BrandVoiceProfile | null>(null);
  const [brandContext, setBrandContext] = useState<BrandContextProfile | null>(null);
  const [aggressiveness, setAggressiveness] =
    useState<ListenerStatus["config"]["aggressiveness"]>("balanced");
  const [chargeConfirmed, setChargeConfirmed] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
    }
  }, [loading, router, token]);

  function updateProduct(productId: string | undefined, nextProduct: Partial<StructuredProduct>) {
    setProducts((currentProducts) =>
      currentProducts.map((product) =>
        product.id === productId ? { ...product, ...nextProduct } : product,
      ),
    );
  }

  function updateProductAttribute(productId: string | undefined, key: string, value: unknown) {
    setProducts((currentProducts) =>
      currentProducts.map((product) =>
        product.id === productId
          ? {
              ...product,
              attributes: {
                ...product.attributes,
                [key]: value,
              },
            }
          : product,
      ),
    );
  }

  function updateBrandVoiceField<K extends keyof BrandVoiceProfile>(
    key: K,
    value: BrandVoiceProfile[K],
  ) {
    setBrandVoice((current) => (current ? { ...current, [key]: value } : current));
  }

  function updateBrandContextField<K extends keyof BrandContextProfile>(
    key: K,
    value: BrandContextProfile[K],
  ) {
    setBrandContext((current) => (current ? { ...current, [key]: value } : current));
  }

  const hydrateActivatedCampaign = useCallback(
    async (activeCampaignId: string, resolvedToken: string) => {
      const liveCampaign = await apiRequest<CampaignOverview>(`/campaigns/${activeCampaignId}`, {
        method: "GET",
        token: resolvedToken,
      });
      const nextListenerStatus = await apiRequest<ListenerStatus>(`/campaigns/${activeCampaignId}/listener/status`, {
        method: "GET",
        token: resolvedToken,
      });
      setCampaign(liveCampaign);
      setActiveCampaignId(liveCampaign.id);
      setListenerStatus(nextListenerStatus);
      setBrandVoice(nextListenerStatus.brand_voice_profile);
      setBrandContext(nextListenerStatus.brand_context_profile);
      setAggressiveness(nextListenerStatus.config.aggressiveness);
      await refreshUser(resolvedToken);
      setStep(5);
    },
    [refreshUser],
  );

  useEffect(() => {
    if (loading || !token) {
      return;
    }
    const checkoutState = searchParams.get("checkout");
    const returnCampaignId = searchParams.get("campaign_id");
    if (!checkoutState || !returnCampaignId) {
      return;
    }
    const campaignId = returnCampaignId as string;
    const authToken = token as string;
    if (checkoutState === "cancel") {
      setStep(4);
      setError("Stripe checkout was canceled before the experiment was funded.");
      return;
    }

    let cancelled = false;
    async function finalizeCheckout() {
      setBusyLabel("Finalizing payment...");
      setError(null);
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const liveCampaign = await apiRequest<CampaignOverview>(`/campaigns/${campaignId}`, {
          method: "GET",
          token: authToken,
        });
        if (cancelled) {
          return;
        }
        if (liveCampaign.status === "active") {
          setCheckoutResponse({
            mode: liveCampaign.billing.mode,
            campaign_id: liveCampaign.id,
            activated: true,
            status: liveCampaign.status,
            message: "Stripe confirmed payment. Your paid experiment is ready to launch.",
          });
          await hydrateActivatedCampaign(campaignId, authToken);
          router.replace("/onboarding");
          setBusyLabel(null);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      if (!cancelled) {
        setStep(4);
        setBusyLabel(null);
        setError(
          "Stripe checkout completed, but Ever is still waiting on webhook confirmation. Keep Stripe CLI forwarding webhooks to localhost and refresh once.",
        );
      }
    }

    void finalizeCheckout();
    return () => {
      cancelled = true;
    };
  }, [hydrateActivatedCampaign, loading, router, searchParams, token]);

  async function handleScanStore() {
    if (!token) {
      return;
    }
    setBusyLabel("Scanning your store...");
    setError(null);
    try {
      const response = await apiRequest<StoreScanResponse>("/stores/scan", {
        method: "POST",
        token,
        body: { url: storeUrl },
      });
      setScanResult(response);
      setProducts(response.products);
      setStep(2);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to scan store.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleConfirmProducts() {
    if (!token || !scanResult) {
      return;
    }
    setBusyLabel("Saving product data...");
    setError(null);
    try {
      const response = await apiRequest<StoreScanResponse>(`/stores/${scanResult.merchant_id}/products`, {
        method: "PUT",
        token,
        body: { products },
      });
      setScanResult(response);
      setProducts(response.products);
      setStep(3);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save product data.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleCreateCampaign() {
    if (!token || !scanResult) {
      return;
    }
    setBusyLabel("Allocating compute budget...");
    setError(null);
    try {
      const response = await apiRequest<CampaignOverview>("/campaigns/create", {
        method: "POST",
        token,
        body: {
          merchant_id: scanResult.merchant_id,
          budget_monthly: budget,
          auto_optimize: true,
        },
      });
      setCampaign(response);
      setActiveCampaignId(response.id);
      setStep(4);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to create campaign.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleActivateCampaign() {
    if (!token || !campaign) {
      return;
    }
    setBusyLabel("Activating campaign...");
    setError(null);
    try {
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
      setError(caughtError instanceof Error ? caughtError.message : "Unable to activate campaign.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleLaunchAgent() {
    if (!token || !campaign || !listenerStatus || !brandVoice || !brandContext) {
      return;
    }
    setBusyLabel("Launching autonomous agent...");
    setError(null);
    try {
      const profile = aggressivenessProfiles[aggressiveness];
      await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
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
            safeguards: {
              ...listenerStatus.config.safeguards,
              max_actions_per_day: profile.max_actions_per_day,
            },
          },
        },
      });
      await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/start`, {
        method: "POST",
        token,
      });
      startTransition(() => router.push("/dashboard"));
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to launch autonomous agent.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  if (loading || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        Loading onboarding...
      </div>
    );
  }

  const estimatedInteractions = Math.round(budget / 3.5);
  const estimatedConversions = Math.max(Math.round(budget / 22), 3);
  const estimatedRoc = 1.8 + budget / 450;
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

        <section className="panel overflow-hidden p-6 sm:p-8">
          {step === 1 ? (
            <div className="grid gap-8 lg:grid-cols-[0.95fr_1.05fr]">
              <div className="space-y-6">
                <p className="eyebrow">Step 1</p>
                <h1 className="font-display text-4xl text-white sm:text-5xl">
                  Connect the store. Give the agent room to sell.
                </h1>
                <p className="max-w-2xl text-base leading-8 text-slate-300">
                  Ever crawls the catalog, structures the products, and prepares an autonomous
                  sales agent that maximizes Return on Compute without you handpicking tactics,
                  channels, or playbooks.
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
                <p className="eyebrow">Operating model</p>
                <div className="mt-5 space-y-4">
                  {[
                    "You set products, brand voice, and compute budget.",
                    "The agent decides channels, tactics, timing, and copy.",
                    "It drafts proposals instead of posting directly.",
                    "You approve and execute the best ones manually.",
                    "RoC is the single scorecard.",
                  ].map((item) => (
                    <div key={item} className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-slate-300">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="space-y-6">
              <div className="flex flex-col gap-2">
                <p className="eyebrow">Step 2</p>
                <h2 className="font-display text-3xl text-white">
                  We found {formatNumber(products.length)} products. Confirm the catalog.
                </h2>
                <p className="text-sm leading-7 text-slate-400">
                  The agent will use this product truth directly, so it is worth tightening the key attributes now.
                </p>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                {products.map((product) => {
                  const isEditing = editingProductId === product.id;
                  return (
                    <article key={product.id ?? product.name} className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                      <div className="flex items-start gap-4">
                        <div className="relative h-24 w-24 overflow-hidden rounded-[1.2rem] border border-white/8 bg-slate-950/70">
                          <Image
                            src={fallbackImageSrc(product.images[0])}
                            alt={product.name}
                            fill
                            className="object-cover"
                            sizes="96px"
                          />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium text-white">{product.name}</p>
                              <p className="mt-1 text-sm text-slate-400">
                                {formatCurrency(product.price, product.currency)} • {product.category ?? "uncategorized"}
                              </p>
                            </div>
                            <button
                              onClick={() =>
                                setEditingProductId((current) => (current === product.id ? null : product.id ?? null))
                              }
                              className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-xs uppercase tracking-[0.22em] text-slate-200 transition hover:bg-white/10"
                            >
                              {isEditing ? "Done" : "Edit"}
                            </button>
                          </div>
                          <p className="mt-3 text-sm leading-7 text-slate-300">
                            {product.description}
                          </p>
                        </div>
                      </div>

                      {isEditing ? (
                        <div className="mt-5 grid gap-4 md:grid-cols-2">
                          <label className="block">
                            <span className="text-sm text-slate-300">Category</span>
                            <input
                              value={product.category ?? ""}
                              onChange={(event) =>
                                updateProduct(product.id, { category: event.target.value || null })
                              }
                              className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                            />
                          </label>
                          <label className="block">
                            <span className="text-sm text-slate-300">Material</span>
                            <input
                              value={String(product.attributes.material ?? "")}
                              onChange={(event) =>
                                updateProductAttribute(product.id, "material", event.target.value)
                              }
                              className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                            />
                          </label>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>

              <button
                onClick={() => void handleConfirmProducts()}
                disabled={Boolean(busyLabel)}
                className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {busyLabel ?? "Looks good, continue"}
              </button>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="space-y-6">
                <p className="eyebrow">Step 3</p>
                <h2 className="font-display text-3xl text-white">Set your compute budget</h2>
                <p className="text-sm leading-7 text-slate-400">
                  The agent will allocate compute to whatever actions it believes can drive the highest return.
                </p>
                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <input
                    type="range"
                    min="50"
                    max="10000"
                    step="50"
                    value={budget}
                    onChange={(event) => setBudget(Number(event.target.value))}
                    className="w-full accent-emerald-400"
                  />
                  <p className="mt-4 font-display text-5xl text-white">{formatCurrency(budget)}</p>
                </div>
                <button
                  onClick={() => void handleCreateCampaign()}
                  disabled={Boolean(busyLabel)}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {busyLabel ?? "Continue to payment"}
                </button>
              </div>

              <div className="rounded-[2rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(9,13,25,0.82))] p-6">
                <p className="eyebrow">Estimated first month</p>
                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  {[
                    {
                      label: "Estimated actions",
                      value: `~${formatNumber(estimatedInteractions)}`,
                    },
                    {
                      label: "Estimated conversions",
                      value: `~${formatNumber(estimatedConversions)}`,
                    },
                    {
                      label: "Estimated RoC",
                      value: formatMultiplier(estimatedRoc),
                    },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{metric.label}</p>
                      <p className="mt-3 font-display text-3xl text-white">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-5 text-sm leading-7 text-slate-400">
                  These are directional estimates only. The point of the product is discovering what the agent actually chooses to do once it has room to operate.
                </p>
              </div>
            </div>
          ) : null}

          {step === 4 ? (
            <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="space-y-5">
                <p className="eyebrow">Step 4</p>
                <h2 className="font-display text-3xl text-white">Activate the compute budget</h2>
                <p className="text-sm leading-7 text-slate-400">
                  This starts a real paid experiment in Stripe test mode first, then live mode when you are ready.
                </p>
                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-sm text-slate-300">Monthly compute budget</p>
                  <p className="mt-3 font-display text-5xl text-white">{formatCurrency(budget)}</p>
                  <div className="mt-5 space-y-3 rounded-[1.3rem] border border-amber-400/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                    <p>You are about to start a real paid experiment.</p>
                    <p>Budget: {formatCurrency(budget)}</p>
                    <p>All agent actions require your approval before execution.</p>
                    <p>You can pause or cancel at any time.</p>
                  </div>
                  <label className="mt-5 flex items-start gap-3 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={chargeConfirmed}
                      onChange={(event) => setChargeConfirmed(event.target.checked)}
                      className="mt-1 h-4 w-4 rounded border-white/10 bg-slate-950/70 text-emerald-400"
                    />
                    <span>I understand this is a real charge.</span>
                  </label>
                </div>
                <button
                  onClick={() => void handleActivateCampaign()}
                  disabled={Boolean(busyLabel) || !chargeConfirmed}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {busyLabel ?? `Start Experiment — ${formatCurrency(budget)}`}
                </button>
              </div>

              <div className="rounded-[2rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(9,13,25,0.82))] p-6">
                <p className="eyebrow">What happens next</p>
                <div className="mt-5 space-y-4">
                  {[
                    "Ever creates a Stripe Checkout session for this budget.",
                    "After payment confirmation, the campaign becomes active.",
                    "You review the agent brain and launch a propose-only operator workflow.",
                  ].map((item) => (
                    <div key={item} className="rounded-[1.3rem] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-slate-300">
                      {item}
                    </div>
                  ))}
                </div>
                {checkoutResponse ? (
                  <p className="mt-5 text-sm leading-7 text-emerald-200">{checkoutResponse.message}</p>
                ) : null}
              </div>
            </div>
          ) : null}

          {step === 5 && brandVoice && brandContext ? (
            <div className="space-y-6">
              <div className="space-y-2">
                <p className="eyebrow">Step 5</p>
                <h2 className="font-display text-3xl text-white">Review your agent</h2>
                <p className="max-w-3xl text-sm leading-7 text-slate-400">
                  The agent now has a catalog, a compute budget, a brand identity, and an agent
                  brain. Dump as much useful context here as you want before the first paid experiment.
                </p>
              </div>

              <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
                <div className="space-y-4">
                  <div className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Brand voice</p>
                    <input
                      value={brandVoice.tone}
                      onChange={(event) => updateBrandVoiceField("tone", event.target.value)}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                    <textarea
                      value={brandVoice.story}
                      onChange={(event) => updateBrandVoiceField("story", event.target.value)}
                      rows={5}
                      className="mt-4 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </div>

                  <div className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Agent brain</p>
                        <p className="mt-2 text-sm leading-7 text-slate-400">
                          This is where you teach the agent the brand beyond tone: positioning,
                          proof points, objections, and hard boundaries.
                        </p>
                      </div>
                      <span className="rounded-full border border-white/10 bg-white/6 px-3 py-2 text-[10px] uppercase tracking-[0.22em] text-slate-300">
                        Paste-friendly
                      </span>
                    </div>

                    <div className="mt-5 space-y-4">
                      <label className="block">
                        <span className="text-sm text-slate-300">Positioning</span>
                        <textarea
                          value={brandContext.positioning}
                          onChange={(event) =>
                            updateBrandContextField("positioning", event.target.value)
                          }
                          rows={3}
                          className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </label>

                      <label className="block">
                        <span className="text-sm text-slate-300">Ideal customer</span>
                        <textarea
                          value={brandContext.ideal_customer}
                          onChange={(event) =>
                            updateBrandContextField("ideal_customer", event.target.value)
                          }
                          rows={3}
                          className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </label>

                      <label className="block">
                        <span className="text-sm text-slate-300">Key messages</span>
                        <textarea
                          value={listToLines(brandContext.key_messages)}
                          onChange={(event) =>
                            updateBrandContextField("key_messages", linesToList(event.target.value))
                          }
                          rows={4}
                          placeholder="One message per line"
                          className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </label>

                      <div className="grid gap-4 md:grid-cols-2">
                        <label className="block">
                          <span className="text-sm text-slate-300">Proof points</span>
                          <textarea
                            value={listToLines(brandContext.proof_points)}
                            onChange={(event) =>
                              updateBrandContextField("proof_points", linesToList(event.target.value))
                            }
                            rows={4}
                            placeholder="One proof point per line"
                            className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                          />
                        </label>

                        <label className="block">
                          <span className="text-sm text-slate-300">Objection handling</span>
                          <textarea
                            value={listToLines(brandContext.objection_handling)}
                            onChange={(event) =>
                              updateBrandContextField(
                                "objection_handling",
                                linesToList(event.target.value),
                              )
                            }
                            rows={4}
                            placeholder="How the agent should respond to hesitations"
                            className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                          />
                        </label>
                      </div>

                      <label className="block">
                        <span className="text-sm text-slate-300">Prohibited claims or topics</span>
                        <textarea
                          value={listToLines(brandContext.prohibited_claims)}
                          onChange={(event) =>
                            updateBrandContextField(
                              "prohibited_claims",
                              linesToList(event.target.value),
                            )
                          }
                          rows={4}
                          placeholder="One hard boundary per line"
                          className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </label>

                      <label className="block">
                        <span className="text-sm text-slate-300">Additional context</span>
                        <textarea
                          value={brandContext.additional_context}
                          onChange={(event) =>
                            updateBrandContextField("additional_context", event.target.value)
                          }
                          rows={6}
                          placeholder="Paste FAQs, sizing notes, founder story, campaign notes, competitor context, channel do's and don'ts, or anything else the agent should know."
                          className="mt-2 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                        />
                      </label>
                    </div>
                  </div>

                  <div className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Operating posture</p>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      {(["conservative", "balanced", "aggressive"] as const).map((option) => (
                        <button
                          key={option}
                          onClick={() => setAggressiveness(option)}
                          className={`rounded-[1.3rem] border px-4 py-4 text-left transition ${
                            aggressiveness === option
                              ? "border-emerald-400/30 bg-emerald-500/10 text-white"
                              : "border-white/10 bg-slate-950/45 text-slate-300"
                          }`}
                        >
                          <p className="text-sm font-medium capitalize">{option}</p>
                          <p className="mt-2 text-xs uppercase tracking-[0.22em] text-slate-500">
                            {aggressivenessProfiles[option].max_actions_per_day} actions/day
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(9,13,25,0.82))] p-5">
                    <p className="eyebrow">Launch summary</p>
                    <div className="mt-4 grid gap-4 sm:grid-cols-2">
                      <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Products</p>
                        <p className="mt-2 font-display text-3xl text-white">{formatNumber(products.length)}</p>
                      </div>
                      <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Budget</p>
                        <p className="mt-2 font-display text-3xl text-white">{formatCurrency(budget)}</p>
                      </div>
                      <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Mode</p>
                        <p className="mt-2 font-display text-3xl text-white">
                          propose-only
                        </p>
                      </div>
                      <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Approval</p>
                        <p className="mt-2 font-display text-3xl text-white">
                          manual
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                    <p className="text-sm leading-7 text-slate-300">
                      Your agent will use this identity and these products to find and draft opportunities. It will decide which channels and tactics look strongest, but every outward action will wait for your approval and manual execution.
                    </p>
                    <button
                      onClick={() => void handleLaunchAgent()}
                      disabled={Boolean(busyLabel)}
                      className="mt-5 rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? "Launch propose-only agent"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
