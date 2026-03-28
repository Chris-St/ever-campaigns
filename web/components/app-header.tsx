"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Logo } from "@/components/logo";

interface AppHeaderProps {
  title: string;
  subtitle: string;
}

export function AppHeader({ title, subtitle }: AppHeaderProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  return (
    <header className="animate-rise border-b border-white/8 bg-slate-950/70 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-5 sm:px-8 lg:px-10">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-6">
            <Logo />
            <nav className="hidden items-center gap-2 rounded-full border border-white/8 bg-white/4 p-1 md:flex">
              {[
                { href: "/dashboard", label: "Dashboard" },
                { href: "/review", label: "Review" },
                { href: "/settings", label: "Settings" },
              ].map((item) => {
                const active = pathname?.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      active
                        ? "bg-white/10 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/settings")}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              Settings
            </button>
            <button
              onClick={() => {
                logout();
                router.push("/");
              }}
              className="rounded-full border border-amber-400/20 bg-amber-500/8 px-4 py-2 text-sm text-amber-100 transition hover:bg-amber-500/15"
            >
              Sign Out
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <p className="eyebrow">Return on Compute</p>
          <h1 className="font-display text-3xl tracking-tight text-white sm:text-4xl">
            {title}
          </h1>
          <p className="max-w-3xl text-sm text-slate-400 sm:text-base">{subtitle}</p>
        </div>
      </div>
    </header>
  );
}
