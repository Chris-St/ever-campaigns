"use client";

import { startTransition, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { Logo } from "@/components/logo";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  BillingCheckoutResponse,
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
  const { token, loading, refreshUser } = useAuth();
  const [step, setStep] = useState(1);
  const [storeUrl, setStoreUrl] = useState("https://biaundies.com");
  const [scanResult, setScanResult] = useState<StoreScanResponse | null>(null);
  const [products, setProducts] = useState<StructuredProduct[]>([]);
  const [budget, setBudget] = useState(500);
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [checkoutResponse, setCheckoutResponse] = useState<BillingCheckoutResponse | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [brandVoice, setBrandVoice] = useState<BrandVoiceProfile | null>(null);
  const [aggressiveness, setAggressiveness] =
    useState<ListenerStatus["config"]["aggressiveness"]>("balanced");
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
      const liveCampaign = await apiRequest<CampaignOverview>(`/campaigns/${campaign.id}`, {
        method: "GET",
        token,
      });
      const nextListenerStatus = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/status`, {
        method: "GET",
        token,
      });
      setCheckoutResponse(response);
      setCampaign(liveCampaign);
      setListenerStatus(nextListenerStatus);
      setBrandVoice(nextListenerStatus.brand_voice_profile);
      setAggressiveness(nextListenerStatus.config.aggressiveness);
      await refreshUser(token);
      setStep(5);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to activate campaign.");
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleLaunchAgent() {
    if (!token || !campaign || !listenerStatus || !brandVoice) {
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
          config: {
            ...listenerStatus.config,
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
  const currentProfile = aggressivenessProfiles[aggressiveness];

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
                    "Every action is reported back into the dashboard.",
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
                  Billing is demo-mode locally, but this step keeps the launch flow true to the product.
                </p>
                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-sm text-slate-300">Monthly compute budget</p>
                  <p className="mt-3 font-display text-5xl text-white">{formatCurrency(budget)}</p>
                </div>
                <button
                  onClick={() => void handleActivateCampaign()}
                  disabled={Boolean(busyLabel)}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {busyLabel ?? "Activate campaign"}
                </button>
              </div>

              <div className="rounded-[2rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(9,13,25,0.82))] p-6">
                <p className="eyebrow">What happens next</p>
                <div className="mt-5 space-y-4">
                  {[
                    "Ever generates the autonomous agent runtime config.",
                    "You review the brand identity and action posture once.",
                    "The agent launches and starts reporting every action back into the dashboard.",
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

          {step === 5 && brandVoice ? (
            <div className="space-y-6">
              <div className="space-y-2">
                <p className="eyebrow">Step 5</p>
                <h2 className="font-display text-3xl text-white">Review your agent</h2>
                <p className="max-w-3xl text-sm leading-7 text-slate-400">
                  The agent now has a catalog, a compute budget, and a brand identity. It will decide which channels and tactics are most efficient.
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
                          {listenerStatus?.config.listener_mode ?? "simulation"}
                        </p>
                      </div>
                      <div className="rounded-[1.2rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Daily cap</p>
                        <p className="mt-2 font-display text-3xl text-white">
                          {formatNumber(currentProfile.max_actions_per_day)}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5">
                    <p className="text-sm leading-7 text-slate-300">
                      Your autonomous agent will use this identity and these products to find and convert customers. It will decide which channels and tactics work best, then report every action back into Ever.
                    </p>
                    <button
                      onClick={() => void handleLaunchAgent()}
                      disabled={Boolean(busyLabel)}
                      className="mt-5 rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {busyLabel ?? "Launch agent"}
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
