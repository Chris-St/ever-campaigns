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
  BillingCheckoutResponse,
  CampaignOverview,
  StoreScanResponse,
  StructuredProduct,
} from "@/lib/types";

const stepLabels = [
  "Connect store",
  "Review products",
  "Set budget",
  "Add payment",
  "Agent endpoints",
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

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
    }
  }, [loading, router, token]);

  const estimatedInteractions = Math.round(budget * 42);
  const estimatedConversions = Math.max(Math.round(budget / 18), 8);
  const estimatedRoc = 2.6 + budget / 2800;

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
      setCheckoutResponse(response);
      setCampaign(liveCampaign);
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

                <button
                  onClick={() => startTransition(() => router.push("/dashboard"))}
                  className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                >
                  Go to Dashboard
                </button>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
