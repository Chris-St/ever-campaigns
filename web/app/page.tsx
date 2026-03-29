import Link from "next/link";

export default function Home() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.18),transparent_22%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.14),transparent_26%),radial-gradient(circle_at_center,rgba(59,130,246,0.14),transparent_30%)]" />
      <div className="absolute inset-0 subtle-grid opacity-40" />

      <div className="relative mx-auto flex w-full max-w-7xl flex-col gap-10 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between py-4">
          <Link
            href="/"
            className="inline-flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.32em] text-slate-100"
          >
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 bg-white/6 shadow-[0_0_32px_rgba(16,185,129,0.22)]">
              <span className="text-lg font-black text-emerald-300">E</span>
            </span>
            <span className="font-display text-[0.72rem]">Ever Campaigns</span>
          </Link>

          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              Log In
            </Link>
            <Link
              href="/signup"
              className="rounded-full bg-emerald-400 px-5 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
            >
              Get Started
            </Link>
          </div>
        </header>

        <main className="space-y-10 pb-10">
          <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="panel flex flex-col justify-between p-8 sm:p-10">
              <div className="space-y-6">
                <p className="eyebrow">Autonomous commerce</p>
                <h1 className="max-w-4xl font-display text-5xl tracking-tight text-white sm:text-7xl">
                  Give an autonomous agent a budget. Tell it to sell.
                </h1>
                <p className="max-w-2xl text-lg leading-9 text-slate-300">
                  Ever gives an autonomous agent your catalog, your brand identity, and a compute
                  budget. It decides the channels and tactics. You watch Return on Compute.
                </p>
                <div className="flex flex-wrap gap-3">
                  <Link
                    href="/signup"
                    className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
                  >
                    Get Started
                  </Link>
                  <Link
                    href="/dashboard"
                    className="rounded-full border border-white/10 bg-white/6 px-6 py-4 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
                  >
                    View Demo Dashboard
                  </Link>
                </div>
              </div>

              <div className="mt-10 grid gap-4 sm:grid-cols-3">
                {[
                  { value: "1", label: "agent with full tactical freedom" },
                  { value: "24/7", label: "autonomous action and reporting loop" },
                  { value: "RoC", label: "single operating metric that matters" },
                ].map((item) => (
                  <div key={item.label} className="rounded-[1.7rem] border border-white/8 bg-white/4 p-5">
                    <p className="font-display text-4xl text-white">{item.value}</p>
                    <p className="mt-2 text-sm leading-7 text-slate-400">{item.label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel overflow-hidden p-6 sm:p-8">
              <div className="rounded-[2rem] border border-white/8 bg-slate-950/60 p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="eyebrow">Live campaign preview</p>
                    <h2 className="font-display text-3xl text-white">Bia × Ever</h2>
                  </div>
                  <span className="rounded-full bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-200">
                    RoC 4.2x
                  </span>
                </div>

                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  {[
                    { label: "Compute spent", value: "$1,124" },
                    { label: "Conversions", value: "131" },
                    { label: "Revenue", value: "$4,748" },
                    { label: "Projected month-end", value: "$1,982" },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-[1.5rem] border border-white/8 bg-white/4 p-4">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                        {metric.label}
                      </p>
                      <p className="mt-3 font-display text-3xl text-white">{metric.value}</p>
                    </div>
                  ))}
                </div>

                <div className="mt-6 rounded-[1.8rem] border border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.95),rgba(12,18,32,0.72))] p-5">
                  <div className="flex items-center justify-between text-xs uppercase tracking-[0.24em] text-slate-500">
                    <span>Compute spend</span>
                    <span>Attributed revenue</span>
                  </div>
                  <div className="mt-5 h-48 rounded-[1.4rem] bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.18),transparent_55%),linear-gradient(180deg,rgba(255,255,255,0.03),transparent)] p-4">
                    <div className="flex h-full items-end gap-3">
                      {[48, 56, 44, 72, 64, 80, 94].map((height) => (
                        <div key={height} className="flex flex-1 items-end gap-2">
                          <div
                            className="w-1/2 rounded-t-full bg-blue-400/80"
                            style={{ height: `${height}%` }}
                          />
                          <div
                            className="w-1/2 rounded-t-full bg-emerald-400/80"
                            style={{ height: `${Math.min(height * 1.18, 100)}%` }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-5 md:grid-cols-3">
            {[
              {
                step: "01",
                title: "Connect your store",
                body: "Paste a URL, let Ever crawl the catalog, and confirm the product truth your agent will use.",
              },
              {
                step: "02",
                title: "Define budget and brand",
                body: "Set the compute budget, review the brand voice, and choose how aggressively the agent should operate.",
              },
              {
                step: "03",
                title: "Watch the agent work",
                body: "Track actions, channel choices, conversions, revenue, and Return on Compute in one live dashboard.",
              },
            ].map((item) => (
              <article key={item.step} className="panel p-6">
                <p className="font-display text-4xl text-blue-200">{item.step}</p>
                <h3 className="mt-5 font-display text-2xl text-white">{item.title}</h3>
                <p className="mt-3 text-sm leading-7 text-slate-400">{item.body}</p>
              </article>
            ))}
          </section>

          <section className="panel overflow-hidden">
            <div className="border-b border-white/8 px-6 py-5">
              <p className="eyebrow">Comparison</p>
              <h2 className="font-display text-3xl text-white">
                Why compute outperforms impression buying
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-white/6">
                <thead className="bg-white/4 text-left text-xs uppercase tracking-[0.22em] text-slate-400">
                  <tr>
                    {["", "Meta Ads", "Google Ads", "Ever"].map((label) => (
                      <th key={label || "row"} className="px-6 py-4">
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/6">
                  {[
                    ["You pay for", "Impressions", "Clicks", "Conversions"],
                    ["Conversion rate", "1-2%", "2-4%", "~100% matched"],
                    ["Avg CAC", "$25-45", "$15-35", "$0.50-5.00"],
                    ["Setup time", "Days", "Hours", "Minutes"],
                  ].map((row) => (
                    <tr key={row[0]}>
                      {row.map((cell, index) => (
                        <td
                          key={cell}
                          className={`px-6 py-4 text-sm ${
                            index === 0 ? "font-medium text-white" : "text-slate-300"
                          } ${index === row.length - 1 ? "text-emerald-200" : ""}`}
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel flex flex-col gap-5 p-8 text-center sm:p-10">
            <p className="eyebrow self-center">Start free</p>
            <h2 className="font-display text-4xl text-white sm:text-5xl">
              Get started free. Pay only when you sell.
            </h2>
            <p className="mx-auto max-w-3xl text-base leading-8 text-slate-300">
              This is acquisition infrastructure for brands spending real money on growth.
              The MCP server is the product. The dashboard is how your team watches it work.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link
                href="/signup"
                className="rounded-full bg-emerald-400 px-6 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
              >
                Get started
              </Link>
              <a
                href="mailto:hello@ever.com"
                className="rounded-full border border-white/10 bg-white/5 px-6 py-4 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
              >
                Contact
              </a>
            </div>
          </section>
        </main>

        <footer className="flex flex-col gap-4 border-t border-white/8 py-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>Ever Campaigns v1</p>
          <div className="flex flex-wrap gap-4">
            <Link href="/signup" className="hover:text-white">
              Docs
            </Link>
            <a href="mailto:hello@ever.com" className="hover:text-white">
              Contact
            </a>
            <a href="#" className="hover:text-white">
              Terms
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
