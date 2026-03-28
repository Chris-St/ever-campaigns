import clsx from "clsx";

import { AnimatedNumber } from "@/components/animated-number";
import { Sparkline } from "@/components/sparkline";

interface DashboardMetricCardProps {
  label: string;
  value: number;
  format?: "currency" | "compact" | "number" | "multiplier";
  currency?: string;
  accentClass: string;
  caption: string;
  sparkline: number[];
  progress?: number;
}

export function DashboardMetricCard({
  label,
  value,
  format = "number",
  currency = "USD",
  accentClass,
  caption,
  sparkline,
  progress,
}: DashboardMetricCardProps) {
  const progressDegrees = Math.max(0, Math.min(progress ?? 0, 1)) * 360;

  return (
    <article className="panel metric-glow flex h-full flex-col gap-5 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-[0.26em] text-slate-400">
            {label}
          </p>
          <AnimatedNumber
            value={value}
            format={format}
            currency={currency}
            className="font-display text-3xl tracking-tight text-white sm:text-4xl"
          />
          <p className="text-sm text-slate-400">{caption}</p>
        </div>

        {progress !== undefined ? (
          <div
            className="relative h-14 w-14 rounded-full border border-white/8 p-1"
            style={{
              background: `conic-gradient(rgba(96,165,250,0.95) ${progressDegrees}deg, rgba(255,255,255,0.08) ${progressDegrees}deg 360deg)`,
            }}
          >
            <div className="flex h-full w-full items-center justify-center rounded-full bg-slate-950/90 text-xs font-semibold text-white">
              {Math.round(progress * 100)}%
            </div>
          </div>
        ) : (
          <div
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em]",
              accentClass,
            )}
          >
            Live
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-white/6 bg-white/3 px-4 py-2">
        <Sparkline values={sparkline} color={accentClass.includes("emerald") ? "#34D399" : accentClass.includes("amber") ? "#FBBF24" : "#60A5FA"} />
      </div>
    </article>
  );
}
