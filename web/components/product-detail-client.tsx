"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";
import { formatCurrency, formatDate, formatMultiplier, formatNumber } from "@/lib/format";
import { fallbackImageSrc } from "@/lib/image";
import type { ProductDetail } from "@/lib/types";

function renderAttributeValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

export function ProductDetailClient({ productId }: { productId: string }) {
  const router = useRouter();
  const { token, loading } = useAuth();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !token) {
      router.replace("/login");
      return;
    }
    if (!token) {
      return;
    }

    let cancelled = false;
    async function loadProduct() {
      try {
        const response = await apiRequest<ProductDetail>(`/products/${productId}`, {
          method: "GET",
          token,
        });
        if (!cancelled) {
          setProduct(response);
          setError(null);
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : "Unable to load product detail.",
          );
        }
      }
    }

    void loadProduct();
    return () => {
      cancelled = true;
    };
  }, [loading, productId, router, token]);

  if (loading || !token || !product) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-slate-300">
        {error ?? "Loading product detail..."}
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AppHeader
        title={product.name}
        subtitle="Structured product detail, campaign contribution, and the exact agent queries driving fit."
      />

      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-8 lg:px-10">
        <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
          <section className="panel p-6">
            <Image
              src={fallbackImageSrc(product.images[0])}
              alt={product.name}
              width={960}
              height={1100}
              unoptimized
              className="h-[420px] w-full rounded-[2rem] object-cover"
            />
            <div className="mt-6 flex flex-wrap gap-2">
              {[product.category, product.subcategory]
                .filter(Boolean)
                .map((label) => (
                  <span
                    key={label}
                    className="rounded-full border border-white/10 bg-white/7 px-3 py-1.5 text-xs uppercase tracking-[0.22em] text-slate-300"
                  >
                    {String(label).replaceAll("_", " ")}
                  </span>
                ))}
            </div>
            <p className="mt-5 text-sm leading-7 text-slate-300">{product.description}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/dashboard"
                className="rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10"
              >
                Back to Dashboard
              </Link>
              <Link
                href="/settings"
                className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100 transition hover:bg-emerald-500/15"
              >
                Edit product data
              </Link>
            </div>
          </section>

          <section className="space-y-6">
            <div className="grid gap-4 md:grid-cols-4">
              {[
                {
                  label: "Price",
                  value: formatCurrency(product.price, product.currency),
                },
                {
                  label: "Matches",
                  value: formatNumber(product.performance.matches),
                },
                {
                  label: "Revenue",
                  value: formatCurrency(product.performance.revenue, product.currency),
                },
                {
                  label: "RoC",
                  value: formatMultiplier(product.performance.return_on_compute),
                },
              ].map((metric) => (
                <div key={metric.label} className="panel p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                    {metric.label}
                  </p>
                  <p className="mt-3 font-display text-3xl text-white">{metric.value}</p>
                </div>
              ))}
            </div>

            <section className="panel p-6">
              <p className="eyebrow">Structured attributes</p>
              <h2 className="font-display text-2xl text-white">What agents can reason over</h2>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {Object.entries(product.attributes).map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-[1.5rem] border border-white/8 bg-white/4 p-4"
                  >
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                      {key.replaceAll("_", " ")}
                    </p>
                    <p className="mt-2 text-sm leading-7 text-slate-200">
                      {renderAttributeValue(value)}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel p-6">
              <p className="eyebrow">Matched queries</p>
              <h2 className="font-display text-2xl text-white">
                Why this product got surfaced
              </h2>
              <div className="mt-6 space-y-4">
                {product.matched_queries.map((query) => (
                  <article
                    key={`${query.query_text}-${query.timestamp}`}
                    className="rounded-[1.6rem] border border-white/8 bg-white/4 p-5"
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm font-medium text-white">{query.query_text}</p>
                      <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
                        {query.agent_source ?? "Agent"} · {formatDate(query.timestamp)}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {query.constraint_matches.map((reason) => (
                        <span
                          key={reason}
                          className="rounded-full border border-white/10 bg-slate-950/50 px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-300"
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                    <p className="mt-3 text-sm text-slate-400">
                      Match score: {query.score.toFixed(1)}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          </section>
        </div>
      </main>
    </div>
  );
}
