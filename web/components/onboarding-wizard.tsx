"use client";

import { startTransition, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Logo } from "@/components/logo";
import { apiRequest } from "@/lib/api";
import { setActiveCampaignId } from "@/lib/auth";
import { formatCurrency, formatMultiplier, formatNumber } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type {
  BrandVoiceProfile,
  BillingCheckoutResponse,
  CampaignOverview,
  ListenerConfig,
  ListenerStatus,
  StoreScanResponse,
  StructuredProduct,
} from "@/lib/types";

const stepLabels = [
  "Connect store",
  "Review products",
  "Set budget",
  "Add payment",
  "Agent endpoints",
  "Brand voice",
  "Surfaces",
  "Review mode",
];

export function OnboardingWizard() {
  const router = useRouter();
  const { token, loading, refreshUser } = useAuth();
  const [step, setStep] = useState(1);
  const [storeUrl, setStoreUrl] = useState("https://biaundies.com");
  const [scanResult, setScanResult] = useState<StoreScanResponse | null>(null);
  const [products, setProducts] = useState<StructuredProduct[]>([]);
  const [budget, setBudget] = useState(2400);
  const [autoOptimize, setAutoOptimize] = useState(true);
  const [campaign, setCampaign] = useState<CampaignOverview | null>(null);
  const [checkoutResponse, setCheckoutResponse] = useState<BillingCheckoutResponse | null>(
    null,
  );
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [listenerStatus, setListenerStatus] = useState<ListenerStatus | null>(null);
  const [listenerConfig, setListenerConfig] = useState<ListenerConfig | null>(null);
  const [brandVoice, setBrandVoice] = useState<BrandVoiceProfile | null>(null);

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
    }
  }, [loading, router, token]);

  const estimatedInteractions = Math.round(budget * 42);
  const estimatedConversions = Math.max(Math.round(budget / 18), 8);
  const estimatedRoc = 2.6 + budget / 2800;
  const redditSurface = listenerConfig?.surfaces.find((surface) => surface.type === "reddit");
  const twitterSurface = listenerConfig?.surfaces.find((surface) => surface.type === "twitter");

  function updateProduct(
    productId: string | undefined,
    nextProduct: Partial<StructuredProduct>,
  ) {
    setProducts((currentProducts) =>
      currentProducts.map((product) =>
        product.id === productId ? { ...product, ...nextProduct } : product,
      ),
    );
  }

  function updateProductAttribute(
    productId: string | undefined,
    key: string,
    value: unknown,
  ) {
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

  async function handleScanStore() {
    if (!token) {
      return;
    }
    setError(null);
    setBusyLabel("Scanning products...");
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
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to scan that store right now.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleConfirmProducts() {
    if (!token || !scanResult) {
      return;
    }
    setError(null);
    setBusyLabel("Saving structured product data...");
    try {
      const response = await apiRequest<StoreScanResponse>(
        `/stores/${scanResult.merchant_id}/products`,
        {
          method: "PUT",
          token,
          body: { products },
        },
      );
      setScanResult(response);
      setProducts(response.products);
      setStep(3);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to save product updates.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleCreateCampaign() {
    if (!token || !scanResult) {
      return;
    }
    setError(null);
    setBusyLabel("Allocating your compute budget...");
    try {
      const response = await apiRequest<CampaignOverview>("/campaigns/create", {
        method: "POST",
        token,
        body: {
          merchant_id: scanResult.merchant_id,
          budget_monthly: budget,
          auto_optimize: autoOptimize,
        },
      });
      setCampaign(response);
      setActiveCampaignId(response.id);
      setStep(4);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to create the campaign.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleActivateCampaign() {
    if (!token || !campaign) {
      return;
    }
    setError(null);
    setBusyLabel("Confirming billing and activating your campaign...");
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
      const nextListenerStatus = await apiRequest<ListenerStatus>(
        `/campaigns/${campaign.id}/listener/status`,
        {
          method: "GET",
          token,
        },
      );
      const retainedOpenclawKey = campaign.agent_endpoints.openclaw.api_key ?? null;
      setCheckoutResponse(response);
      setCampaign({
        ...liveCampaign,
        agent_endpoints: {
          ...liveCampaign.agent_endpoints,
          openclaw: {
            ...liveCampaign.agent_endpoints.openclaw,
            api_key: retainedOpenclawKey,
            api_key_preview:
              liveCampaign.agent_endpoints.openclaw.api_key_preview ??
              campaign.agent_endpoints.openclaw.api_key_preview,
          },
        },
      });
      setListenerStatus(nextListenerStatus);
      setListenerConfig(nextListenerStatus.config);
      setBrandVoice(nextListenerStatus.brand_voice_profile);
      await refreshUser(token);
      setStep(5);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to activate billing.",
      );
    } finally {
      setBusyLabel(null);
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
    }, 1600);
  }

  function updateBrandVoiceField<K extends keyof BrandVoiceProfile>(
    key: K,
    value: BrandVoiceProfile[K],
  ) {
    setBrandVoice((current) => (current ? { ...current, [key]: value } : current));
  }

  function updateBrandVoiceListField(
    key: "values" | "dos" | "donts",
    value: string,
  ) {
    updateBrandVoiceField(
      key,
      value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    );
  }

  function updateSampleResponse(key: string, value: string) {
    setBrandVoice((current) =>
      current
        ? {
            ...current,
            sample_responses: {
              ...current.sample_responses,
              [key]: value,
            },
          }
        : current,
    );
  }

  function updateSurface(
    surfaceType: "reddit" | "twitter",
    updater: (surface: ListenerConfig["surfaces"][number]) => ListenerConfig["surfaces"][number],
  ) {
    setListenerConfig((current) =>
      current
        ? {
            ...current,
            surfaces: current.surfaces.map((surface) =>
              surface.type === surfaceType ? updater(surface) : surface,
            ),
          }
        : current,
    );
  }

  async function saveListenerConfig(nextStep?: number) {
    if (!token || !campaign || !listenerConfig || !brandVoice) {
      return;
    }
    setError(null);
    setBusyLabel("Saving intent listener configuration...");
    try {
      const response = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
        method: "PUT",
        token,
        body: {
          brand_voice_profile: brandVoice,
          config: listenerConfig,
        },
      });
      setListenerStatus(response);
      setListenerConfig(response.config);
      setBrandVoice(response.brand_voice_profile);
      if (nextStep) {
        setStep(nextStep);
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to save the intent listener configuration.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  async function handleStartListener() {
    if (!token || !campaign || !listenerConfig || !brandVoice) {
      return;
    }
    setError(null);
    setBusyLabel("Starting the intent listener...");
    try {
      await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/config`, {
        method: "PUT",
        token,
        body: {
          brand_voice_profile: brandVoice,
          config: listenerConfig,
        },
      });
      const response = await apiRequest<ListenerStatus>(`/campaigns/${campaign.id}/listener/start`, {
        method: "POST",
        token,
      });
      setListenerStatus(response);
      setListenerConfig(response.config);
      setBrandVoice(response.brand_voice_profile);
      startTransition(() => router.push("/dashboard"));
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to start the intent listener.",
      );
    } finally {
      setBusyLabel(null);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.16),transparent_24%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.16),transparent_28%)]" />
      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-5 py-8 sm:px-8 lg:px-10">
        <div className="flex items-center justify-between">
          <Logo />
          <Link
            href="/dashboard"
            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10"
          >
            Skip to Dashboard
          </Link>
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.82fr_1.18fr]">
          <aside className="panel flex flex-col gap-8 p-7 sm:p-8">
            <div className="space-y-4">
              <p className="eyebrow">Campaign launch</p>
              <h1 className="font-display text-4xl tracking-tight text-white sm:text-5xl">
                Crawl first. Confirm once. Launch with compute.
              </h1>
              <p className="text-base leading-8 text-slate-300">
                Ever structures your catalog for agents, allocates budget automatically,
                and turns campaign setup into a five-step flow that finishes in minutes.
              </p>
            </div>

            <div className="space-y-3">
              {stepLabels.map((label, index) => {
                const isActive = step === index + 1;
                const isComplete = step > index + 1;
                return (
                  <div
                    key={label}
                    className={`flex items-center gap-4 rounded-[1.5rem] border px-4 py-3 transition ${
                      isActive
                        ? "border-emerald-400/40 bg-emerald-400/12"
                        : isComplete
                          ? "border-blue-400/30 bg-blue-400/10"
                          : "border-white/8 bg-white/4"
                    }`}
                  >
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold ${
                        isActive
                          ? "bg-emerald-300 text-slate-950"
                          : isComplete
                            ? "bg-blue-400 text-slate-950"
                            : "bg-white/10 text-slate-300"
                      }`}
                    >
                      {index + 1}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{label}</p>
                      <p className="text-xs text-slate-400">
                        {isComplete
                          ? "Completed"
                          : isActive
                            ? "In progress"
                            : "Pending"}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
              <p className="text-xs font-medium uppercase tracking-[0.26em] text-slate-400">
                North star metric
              </p>
              <p className="mt-3 font-display text-4xl text-white">
                {formatMultiplier(estimatedRoc)}
              </p>
              <p className="mt-2 text-sm leading-7 text-slate-400">
                Return on Compute is the default operating lens across onboarding, spend
                controls, and the live dashboard.
              </p>
            </div>
          </aside>

          <section className="panel flex flex-col gap-6 p-7 sm:p-8">
            {error ? (
              <div className="rounded-[1.4rem] border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {error}
              </div>
            ) : null}

            {busyLabel ? (
              <div className="rounded-[1.4rem] border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">
                <div className="flex items-center gap-3">
                  <div className="h-2.5 w-2.5 rounded-full bg-blue-300 animate-pulse" />
                  {busyLabel}
                </div>
              </div>
            ) : null}

            {step === 1 ? (
              <div className="space-y-6">
                <div className="space-y-3">
                  <p className="eyebrow">Step 1</p>
                  <h2 className="font-display text-3xl text-white">Connect your store</h2>
                  <p className="text-sm leading-7 text-slate-400">
                    Paste a Shopify URL and Ever will crawl the catalog, structure the
                    products, and hand the results back for review.
                  </p>
                </div>

                <label className="block space-y-2">
                  <span className="text-sm text-slate-300">Store URL</span>
                  <input
                    value={storeUrl}
                    onChange={(event) => setStoreUrl(event.target.value)}
                    placeholder="https://biaundies.com"
                    className="w-full rounded-[1.5rem] border border-white/12 bg-slate-950/70 px-5 py-4 text-white outline-none transition focus:border-emerald-400/50"
                  />
                </label>

                <div className="grid gap-4 rounded-[1.8rem] border border-white/8 bg-white/4 p-5 sm:grid-cols-3">
                  {[
                    "Shopify products.json first",
                    "HTML fallback if catalog is locked down",
                    "Structured attributes extracted for agents",
                  ].map((item) => (
                    <div key={item} className="rounded-[1.4rem] border border-white/8 bg-slate-950/40 p-4 text-sm text-slate-300">
                      {item}
                    </div>
                  ))}
                </div>

                <button
                  onClick={handleScanStore}
                  disabled={Boolean(busyLabel)}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  Scan Store
                </button>
              </div>
            ) : null}

            {step === 2 ? (
              <div className="space-y-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                  <div className="space-y-3">
                    <p className="eyebrow">Step 2</p>
                    <h2 className="font-display text-3xl text-white">Review your products</h2>
                    <p className="text-sm leading-7 text-slate-400">
                      We found {products.length} products on {scanResult?.name}. Review the
                      structured fields, edit any mismatches, then continue.
                    </p>
                  </div>
                  <button
                    onClick={handleConfirmProducts}
                    className="rounded-full border border-white/10 bg-white/8 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/12"
                  >
                    Looks good, continue
                  </button>
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                  {products.map((product) => {
                    const activities = Array.isArray(product.attributes.activities)
                      ? (product.attributes.activities as string[]).join(", ")
                      : "";
                    const keyFeatures = Array.isArray(product.attributes.key_features)
                      ? (product.attributes.key_features as string[]).join(", ")
                      : "";

                    return (
                      <article
                        key={product.id ?? product.name}
                        className="rounded-[2rem] border border-white/8 bg-white/4 p-5"
                      >
                        <div className="flex gap-4">
                          <Image
                            src={product.images[0] ?? fallbackImageSrc}
                            alt={product.name}
                            width={160}
                            height={220}
                            unoptimized
                            className="h-28 w-24 rounded-[1.3rem] object-cover"
                          />
                          <div className="flex-1 space-y-2">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <h3 className="font-display text-xl text-white">{product.name}</h3>
                                <p className="text-sm text-slate-400">
                                  {formatCurrency(product.price, product.currency)} ·{" "}
                                  {product.category?.replaceAll("_", " ") ?? "category pending"}
                                </p>
                              </div>
                              <button
                                onClick={() =>
                                  setEditingProductId((current) =>
                                    current === product.id ? null : (product.id ?? product.name),
                                  )
                                }
                                className="rounded-full border border-white/10 bg-white/7 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-slate-200"
                              >
                                {editingProductId === (product.id ?? product.name) ? "Close" : "Edit"}
                              </button>
                            </div>
                            <p className="line-clamp-3 text-sm leading-7 text-slate-300">
                              {product.description}
                            </p>
                          </div>
                        </div>

                        {editingProductId === (product.id ?? product.name) ? (
                          <div className="mt-5 grid gap-4 md:grid-cols-2">
                            <label className="space-y-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Name
                              </span>
                              <input
                                value={product.name}
                                onChange={(event) =>
                                  updateProduct(product.id, { name: event.target.value })
                                }
                                className="w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                            <label className="space-y-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Price
                              </span>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={product.price}
                                onChange={(event) =>
                                  updateProduct(product.id, {
                                    price: Number(event.target.value),
                                  })
                                }
                                className="w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                            <label className="space-y-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Category
                              </span>
                              <input
                                value={product.category ?? ""}
                                onChange={(event) =>
                                  updateProduct(product.id, {
                                    category: event.target.value,
                                  })
                                }
                                className="w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                            <label className="space-y-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Subcategory
                              </span>
                              <input
                                value={product.subcategory ?? ""}
                                onChange={(event) =>
                                  updateProduct(product.id, {
                                    subcategory: event.target.value,
                                  })
                                }
                                className="w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                            <label className="space-y-2 md:col-span-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Activities
                              </span>
                              <input
                                value={activities}
                                onChange={(event) =>
                                  updateProductAttribute(
                                    product.id,
                                    "activities",
                                    event.target.value
                                      .split(",")
                                      .map((value) => value.trim())
                                      .filter(Boolean),
                                  )
                                }
                                className="w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                            <label className="space-y-2 md:col-span-2">
                              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">
                                Key features
                              </span>
                              <textarea
                                value={keyFeatures}
                                onChange={(event) =>
                                  updateProductAttribute(
                                    product.id,
                                    "key_features",
                                    event.target.value
                                      .split(",")
                                      .map((value) => value.trim())
                                      .filter(Boolean),
                                  )
                                }
                                className="min-h-28 w-full rounded-[1.1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none"
                              />
                            </label>
                          </div>
                        ) : (
                          <div className="mt-5 flex flex-wrap gap-2">
                            {[
                              product.subcategory,
                              ...(Array.isArray(product.attributes.activities)
                                ? (product.attributes.activities as string[])
                                : []),
                            ]
                              .filter(Boolean)
                              .slice(0, 6)
                              .map((chip) => (
                                <span
                                  key={chip}
                                  className="rounded-full border border-white/10 bg-white/7 px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-300"
                                >
                                  {String(chip).replaceAll("_", " ")}
                                </span>
                              ))}
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {step === 3 ? (
              <div className="space-y-8">
                <div className="space-y-3">
                  <p className="eyebrow">Step 3</p>
                  <h2 className="font-display text-3xl text-white">Set your compute budget</h2>
                  <p className="text-sm leading-7 text-slate-400">
                    Choose a monthly compute allocation and Ever will automatically tilt spend
                    toward the products converting best across AI surfaces.
                  </p>
                </div>

                <div className="rounded-[2rem] border border-white/8 bg-white/4 p-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-sm uppercase tracking-[0.26em] text-slate-400">
                        Monthly budget
                      </p>
                      <p className="font-display text-5xl text-white">{formatCurrency(budget)}</p>
                    </div>
                    <label className="inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200">
                      <input
                        type="checkbox"
                        checked={autoOptimize}
                        onChange={(event) => setAutoOptimize(event.target.checked)}
                        className="h-4 w-4 accent-emerald-400"
                      />
                      Auto-optimize
                    </label>
                  </div>

                  <input
                    type="range"
                    min="100"
                    max="10000"
                    step="100"
                    value={budget}
                    onChange={(event) => setBudget(Number(event.target.value))}
                    className="mt-8 w-full accent-emerald-400"
                  />

                  <div className="mt-8 grid gap-4 sm:grid-cols-3">
                    <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                        Estimated interactions
                      </p>
                      <p className="mt-2 font-display text-3xl text-white">
                        ~{formatNumber(estimatedInteractions)}
                      </p>
                    </div>
                    <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                        Estimated conversions
                      </p>
                      <p className="mt-2 font-display text-3xl text-white">
                        ~{formatNumber(estimatedConversions)}
                      </p>
                    </div>
                    <div className="rounded-[1.4rem] border border-white/8 bg-slate-950/40 p-4">
                      <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                        Estimated RoC
                      </p>
                      <p className="mt-2 font-display text-3xl text-emerald-300">
                        ~{formatMultiplier(estimatedRoc)}
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleCreateCampaign}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                >
                  Launch Campaign
                </button>
              </div>
            ) : null}

            {step === 4 ? (
              <div className="space-y-7">
                <div className="space-y-3">
                  <p className="eyebrow">Step 4</p>
                  <h2 className="font-display text-3xl text-white">Add payment</h2>
                  <p className="text-sm leading-7 text-slate-400">
                    Billing is wired in demo mode for local development, with the endpoint
                    shaped to swap into Stripe Checkout when you add credentials.
                  </p>
                </div>

                <div className="grid gap-4 rounded-[2rem] border border-white/8 bg-white/4 p-6 sm:grid-cols-2">
                  <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/50 p-5">
                    <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                      Campaign
                    </p>
                    <p className="mt-3 font-display text-3xl text-white">
                      {scanResult?.name ?? "Store"}
                    </p>
                    <p className="mt-2 text-sm text-slate-400">{scanResult?.domain}</p>
                  </div>
                  <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/50 p-5">
                    <p className="text-xs uppercase tracking-[0.26em] text-slate-400">
                      Billing summary
                    </p>
                    <p className="mt-3 font-display text-3xl text-white">
                      {formatCurrency(budget)}
                    </p>
                    <p className="mt-2 text-sm text-slate-400">
                      Charged monthly against your compute budget.
                    </p>
                  </div>
                </div>

                <button
                  onClick={handleActivateCampaign}
                  className="rounded-full bg-white px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-slate-100"
                >
                  Start Campaign
                </button>
              </div>
            ) : null}

            {step === 5 ? (
              <div className="space-y-7">
                <div className="space-y-3">
                  <p className="eyebrow">Step 5</p>
                  <h2 className="font-display text-3xl text-white">Your agent endpoints</h2>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300">
                    Your campaign is live. Here are the URLs and feed surfaces that make
                    your products agent-discoverable today, with ACP and UCP ready for the
                    moment those submissions turn on.
                  </p>
                </div>

                <div className="rounded-[2rem] border border-emerald-400/20 bg-emerald-500/10 p-6">
                  <p className="text-sm text-emerald-100">
                    {checkoutResponse?.message ??
                      "Campaign activated. Demo billing mode completed successfully."}
                  </p>
                </div>

                {campaign?.agent_endpoints ? (
                  <div className="space-y-5">
                    <div className="rounded-[2rem] border border-white/8 bg-white/4 p-6">
                      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                        <div className="space-y-3">
                          <p className="eyebrow">MCP server URL</p>
                          <h3 className="font-display break-all text-2xl text-white">
                            {campaign.agent_endpoints.mcp.public_url}
                          </h3>
                          <p className="max-w-2xl text-sm leading-7 text-slate-400">
                            {campaign.agent_endpoints.mcp.description}
                          </p>
                        </div>
                        <button
                          onClick={() =>
                            handleCopy("mcp", campaign.agent_endpoints.mcp.public_url)
                          }
                          className="rounded-full border border-white/10 bg-white/7 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/12"
                        >
                          {copiedField === "mcp" ? "Copied" : "Copy URL"}
                        </button>
                      </div>

                      <div className="mt-5 grid gap-4 lg:grid-cols-2">
                        <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                            Quick test
                          </p>
                          <p className="mt-2 text-sm leading-7 text-slate-200">
                            {campaign.agent_endpoints.mcp.quick_test_prompt}
                          </p>
                        </div>
                        <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                            Connected surfaces
                          </p>
                          <p className="mt-2 text-sm leading-7 text-slate-200">
                            {campaign.agent_endpoints.connected_surfaces}
                          </p>
                        </div>
                      </div>

                      <div className="mt-5 flex flex-wrap gap-3">
                        <a
                          href={campaign.agent_endpoints.mcp.preview_url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100 transition hover:bg-blue-500/15"
                        >
                          Preview local MCP route
                        </a>
                        <a
                          href={campaign.agent_endpoints.mcp.global_preview_url ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                        >
                          View global MCP server
                        </a>
                      </div>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5 lg:col-span-2">
                        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                          <div>
                            <p className="eyebrow">OpenClaw runtime</p>
                            <h3 className="font-display text-2xl text-white">
                              Listener engine access
                            </h3>
                            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
                              Use this config endpoint, events endpoint, and campaign API key to run
                              the local OpenClaw-compatible listener and report intent, replies, and
                              compute back into Ever.
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-3">
                            <button
                              onClick={() =>
                                handleCopy(
                                  "openclaw-key",
                                  campaign.agent_endpoints.openclaw.api_key,
                                )
                              }
                              className="rounded-full border border-white/10 bg-white/7 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/12"
                            >
                              {copiedField === "openclaw-key" ? "Copied" : "Copy API key"}
                            </button>
                            <button
                              onClick={() =>
                                handleCopy(
                                  "openclaw-command",
                                  campaign.agent_endpoints.openclaw.launch_command,
                                )
                              }
                              className="rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm font-semibold text-blue-100 transition hover:bg-blue-500/15"
                            >
                              {copiedField === "openclaw-command" ? "Copied" : "Copy launch command"}
                            </button>
                          </div>
                        </div>

                        <div className="mt-5 grid gap-4 lg:grid-cols-2">
                          <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                              Campaign API key
                            </p>
                            <p className="mt-3 break-all font-mono text-sm text-white">
                              {campaign.agent_endpoints.openclaw.api_key ??
                                campaign.agent_endpoints.openclaw.api_key_preview ??
                                "Generate from the dashboard if you need a fresh key."}
                            </p>
                          </div>
                          <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                              Local launch command
                            </p>
                            <p className="mt-3 break-all font-mono text-sm leading-7 text-slate-200">
                              {campaign.agent_endpoints.openclaw.launch_command}
                            </p>
                          </div>
                        </div>

                        <div className="mt-5 grid gap-4 lg:grid-cols-2">
                          <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                              Config endpoint
                            </p>
                            <p className="mt-3 break-all text-sm leading-7 text-slate-200">
                              {campaign.agent_endpoints.openclaw.config_url}
                            </p>
                          </div>
                          <div className="rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-5">
                            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                              Events endpoint
                            </p>
                            <p className="mt-3 break-all text-sm leading-7 text-slate-200">
                              {campaign.agent_endpoints.openclaw.events_url}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="eyebrow">ACP status</p>
                            <h3 className="font-display text-2xl text-white">
                              {campaign.agent_endpoints.acp.label}
                            </h3>
                          </div>
                          <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-amber-100">
                            {campaign.agent_endpoints.acp.badge}
                          </span>
                        </div>
                        <p className="mt-3 text-sm leading-7 text-slate-400">
                          {campaign.agent_endpoints.acp.description}
                        </p>
                        <div className="mt-4 flex flex-wrap gap-3">
                          <a
                            href={campaign.agent_endpoints.acp.preview_url ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                          >
                            Preview ACP feed
                          </a>
                        </div>
                      </div>

                      <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="eyebrow">UCP status</p>
                            <h3 className="font-display text-2xl text-white">
                              {campaign.agent_endpoints.ucp.label}
                            </h3>
                          </div>
                          <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-amber-100">
                            {campaign.agent_endpoints.ucp.badge}
                          </span>
                        </div>
                        <p className="mt-3 text-sm leading-7 text-slate-400">
                          {campaign.agent_endpoints.ucp.description}
                        </p>
                        <div className="mt-4 flex flex-wrap gap-3">
                          <a
                            href={campaign.agent_endpoints.ucp.preview_url ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full border border-white/10 bg-white/6 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
                          >
                            Preview UCP feed
                          </a>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-[1.8rem] border border-white/8 bg-slate-950/35 p-5">
                      <p className="text-sm leading-8 text-slate-300">
                        {campaign.agent_endpoints.summary}
                      </p>
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => setStep(6)}
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Configure intent listener
                  </button>
                  <button
                    onClick={() => startTransition(() => router.push("/dashboard"))}
                    className="rounded-full border border-white/10 bg-white/6 px-6 py-4 text-sm font-semibold text-white transition hover:bg-white/10"
                  >
                    Skip for now
                  </button>
                </div>
              </div>
            ) : null}

            {step === 6 && brandVoice ? (
              <div className="space-y-7">
                <div className="space-y-3">
                  <p className="eyebrow">Step 6</p>
                  <h2 className="font-display text-3xl text-white">
                    Configure your agent&apos;s personality
                  </h2>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300">
                    Ever starts with a brand voice pulled from your catalog and positioning. Edit
                    it once here so replies across Reddit and X sound aligned, helpful, and
                    unmistakably on-brand.
                  </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <label className="rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Brand name</span>
                    <input
                      value={brandVoice.brand_name}
                      onChange={(event) => updateBrandVoiceField("brand_name", event.target.value)}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>
                  <label className="rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Tone</span>
                    <input
                      value={brandVoice.tone}
                      onChange={(event) => updateBrandVoiceField("tone", event.target.value)}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>
                </div>

                <label className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                  <span className="text-sm text-slate-300">Brand story</span>
                  <textarea
                    value={brandVoice.story}
                    onChange={(event) => updateBrandVoiceField("story", event.target.value)}
                    rows={4}
                    className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                  />
                </label>

                <label className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                  <span className="text-sm text-slate-300">Target customer</span>
                  <textarea
                    value={brandVoice.target_customer ?? ""}
                    onChange={(event) => updateBrandVoiceField("target_customer", event.target.value)}
                    rows={3}
                    className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                  />
                </label>

                <div className="grid gap-4 lg:grid-cols-3">
                  <label className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Values</span>
                    <textarea
                      value={brandVoice.values.join("\n")}
                      onChange={(event) => updateBrandVoiceListField("values", event.target.value)}
                      rows={5}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>
                  <label className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Do&apos;s</span>
                    <textarea
                      value={brandVoice.dos.join("\n")}
                      onChange={(event) => updateBrandVoiceListField("dos", event.target.value)}
                      rows={5}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>
                  <label className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <span className="text-sm text-slate-300">Don&apos;ts</span>
                    <textarea
                      value={brandVoice.donts.join("\n")}
                      onChange={(event) => updateBrandVoiceListField("donts", event.target.value)}
                      rows={5}
                      className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                    />
                  </label>
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                  {[
                    { key: "reddit", label: "Sample Reddit response" },
                    { key: "twitter", label: "Sample X response" },
                    { key: "product_query", label: "Sample product-query response" },
                  ].map((sample) => (
                    <label
                      key={sample.key}
                      className="block rounded-[1.7rem] border border-white/8 bg-white/4 p-5"
                    >
                      <span className="text-sm text-slate-300">{sample.label}</span>
                      <textarea
                        value={brandVoice.sample_responses[sample.key] ?? ""}
                        onChange={(event) => updateSampleResponse(sample.key, event.target.value)}
                        rows={6}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                  ))}
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => void saveListenerConfig(7)}
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Save and continue
                  </button>
                  <button
                    onClick={() => setStep(5)}
                    className="rounded-full border border-white/10 bg-white/6 px-6 py-4 text-sm font-semibold text-white transition hover:bg-white/10"
                  >
                    Back
                  </button>
                </div>
              </div>
            ) : null}

            {step === 7 && listenerConfig ? (
              <div className="space-y-7">
                <div className="space-y-3">
                  <p className="eyebrow">Step 7</p>
                  <h2 className="font-display text-3xl text-white">Choose your surfaces</h2>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300">
                    Select where the listener should look for purchase intent, then tune how
                    wide a net it casts.
                  </p>
                </div>

                <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                  <p className="text-sm text-slate-300">Aggressiveness</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {[
                      {
                        value: "conservative",
                        label: "Conservative",
                        detail: "Only respond to the strongest signals.",
                      },
                      {
                        value: "balanced",
                        label: "Balanced",
                        detail: "Default. Healthy volume with tighter fit.",
                      },
                      {
                        value: "aggressive",
                        label: "Aggressive",
                        detail: "Cast wider and let review catch edge cases.",
                      },
                    ].map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setListenerConfig((current) =>
                            current
                              ? {
                                  ...current,
                                  aggressiveness: option.value as ListenerConfig["aggressiveness"],
                                  thresholds:
                                    option.value === "conservative"
                                      ? { composite_min: 78, receptivity_min: 68 }
                                      : option.value === "aggressive"
                                        ? { composite_min: 58, receptivity_min: 48 }
                                        : { composite_min: 70, receptivity_min: 60 },
                                }
                              : current,
                          )
                        }
                        className={`rounded-[1.5rem] border p-4 text-left transition ${
                          listenerConfig.aggressiveness === option.value
                            ? "border-emerald-400/40 bg-emerald-400/10"
                            : "border-white/8 bg-slate-950/40"
                        }`}
                      >
                        <p className="font-medium text-white">{option.label}</p>
                        <p className="mt-2 text-sm leading-7 text-slate-400">{option.detail}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="eyebrow">Reddit</p>
                        <h3 className="font-display text-2xl text-white">Community intent</h3>
                      </div>
                      <input
                        type="checkbox"
                        checked={redditSurface?.enabled ?? false}
                        onChange={(event) =>
                          updateSurface("reddit", (surface) => ({
                            ...surface,
                            enabled: event.target.checked,
                          }))
                        }
                        className="h-5 w-5 accent-emerald-400"
                      />
                    </div>
                    <label className="mt-4 block">
                      <span className="text-sm text-slate-300">Subreddits</span>
                      <textarea
                        value={(redditSurface?.subreddits ?? []).join("\n")}
                        onChange={(event) =>
                          updateSurface("reddit", (surface) => ({
                            ...surface,
                            subreddits: event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean),
                          }))
                        }
                        rows={8}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                    <label className="mt-4 block">
                      <span className="text-sm text-slate-300">Keywords</span>
                      <textarea
                        value={(redditSurface?.keywords ?? []).join("\n")}
                        onChange={(event) =>
                          updateSurface("reddit", (surface) => ({
                            ...surface,
                            keywords: event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean),
                          }))
                        }
                        rows={4}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                  </div>

                  <div className="rounded-[1.8rem] border border-white/8 bg-white/4 p-5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="eyebrow">Twitter / X</p>
                        <h3 className="font-display text-2xl text-white">Keyword intent</h3>
                      </div>
                      <input
                        type="checkbox"
                        checked={twitterSurface?.enabled ?? false}
                        onChange={(event) =>
                          updateSurface("twitter", (surface) => ({
                            ...surface,
                            enabled: event.target.checked,
                          }))
                        }
                        className="h-5 w-5 accent-emerald-400"
                      />
                    </div>
                    <label className="mt-4 block">
                      <span className="text-sm text-slate-300">Search queries</span>
                      <textarea
                        value={(twitterSurface?.search_queries ?? []).join("\n")}
                        onChange={(event) =>
                          updateSurface("twitter", (surface) => ({
                            ...surface,
                            search_queries: event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean),
                          }))
                        }
                        rows={8}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                    <label className="mt-4 block">
                      <span className="text-sm text-slate-300">Keywords</span>
                      <textarea
                        value={(twitterSurface?.keywords ?? []).join("\n")}
                        onChange={(event) =>
                          updateSurface("twitter", (surface) => ({
                            ...surface,
                            keywords: event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean),
                          }))
                        }
                        rows={4}
                        className="mt-3 w-full rounded-[1rem] border border-white/10 bg-slate-950/70 px-4 py-3 text-white outline-none"
                      />
                    </label>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => void saveListenerConfig(8)}
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Save surfaces
                  </button>
                  <button
                    onClick={() => setStep(6)}
                    className="rounded-full border border-white/10 bg-white/6 px-6 py-4 text-sm font-semibold text-white transition hover:bg-white/10"
                  >
                    Back
                  </button>
                </div>
              </div>
            ) : null}

            {step === 8 && listenerConfig && listenerStatus ? (
              <div className="space-y-7">
                <div className="space-y-3">
                  <p className="eyebrow">Step 8</p>
                  <h2 className="font-display text-3xl text-white">Review mode</h2>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300">
                    The first 50 approved responses train the system on what good looks like.
                    After that, auto mode can post high-confidence replies while keeping lower
                    confidence ones in review.
                  </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
                  <div className="space-y-4">
                    {[
                      {
                        value: "manual",
                        label: "Full review mode",
                        detail: "Every response waits for approval before it posts.",
                      },
                      {
                        value: "auto",
                        label: "Smart auto mode",
                        detail:
                          "Still reviews your first 50 approved responses, then auto-posts confident replies with spot-checking.",
                      },
                    ].map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setListenerConfig((current) =>
                            current
                              ? {
                                  ...current,
                                  review_mode: option.value as ListenerConfig["review_mode"],
                                }
                              : current,
                          )
                        }
                        className={`w-full rounded-[1.7rem] border p-5 text-left transition ${
                          listenerConfig.review_mode === option.value
                            ? "border-emerald-400/40 bg-emerald-400/10"
                            : "border-white/8 bg-white/4"
                        }`}
                      >
                        <p className="font-medium text-white">{option.label}</p>
                        <p className="mt-2 text-sm leading-7 text-slate-400">{option.detail}</p>
                      </button>
                    ))}
                  </div>

                  <div className="rounded-[1.8rem] border border-white/8 bg-slate-950/45 p-5">
                    <p className="eyebrow">Listener summary</p>
                    <div className="mt-4 space-y-4">
                      <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                          Surfaces active
                        </p>
                        <p className="mt-2 font-display text-3xl text-white">
                          {listenerStatus.surfaces_active_count}
                        </p>
                        <p className="mt-2 text-sm text-slate-400">
                          {listenerStatus.surfaces_active.join(", ")}
                        </p>
                      </div>
                      <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                          Auto-post threshold
                        </p>
                        <p className="mt-2 font-display text-3xl text-white">
                          {listenerConfig.auto_post_after_approvals}
                        </p>
                        <p className="mt-2 text-sm text-slate-400">
                          Approved responses before confident replies can flow automatically.
                        </p>
                      </div>
                      <div className="rounded-[1.4rem] border border-white/8 bg-white/4 p-4">
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                          Thresholds
                        </p>
                        <p className="mt-2 text-sm leading-7 text-slate-200">
                          Composite {listenerConfig.thresholds.composite_min}+ with receptivity at{" "}
                          {listenerConfig.thresholds.receptivity_min}+.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => void handleStartListener()}
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Start intent listener
                  </button>
                  <button
                    onClick={() => setStep(7)}
                    className="rounded-full border border-white/10 bg-white/6 px-6 py-4 text-sm font-semibold text-white transition hover:bg-white/10"
                  >
                    Back
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
