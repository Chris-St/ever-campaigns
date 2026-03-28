import clsx from "clsx";
import Link from "next/link";

interface LogoProps {
  className?: string;
}

export function Logo({ className }: LogoProps) {
  return (
    <Link
      href="/"
      className={clsx(
        "inline-flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.32em] text-slate-100",
        className,
      )}
    >
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 bg-white/6 shadow-[0_0_32px_rgba(16,185,129,0.22)]">
        <span className="text-lg font-black text-emerald-300">E</span>
      </span>
      <span className="font-display text-[0.7rem]">Ever Campaigns</span>
    </Link>
  );
}
