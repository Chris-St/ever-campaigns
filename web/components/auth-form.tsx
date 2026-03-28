"use client";

import Link from "next/link";
import { startTransition, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Logo } from "@/components/logo";
import { apiRequest } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";

interface AuthFormProps {
  mode: "login" | "signup";
}

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const { setSessionData } = useAuth();
  const [email, setEmail] = useState("founder@ever.com");
  const [password, setPassword] = useState("testpass123");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSignup = mode === "signup";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const response = await apiRequest<AuthResponse>(
        isSignup ? "/auth/signup" : "/auth/login",
        {
          method: "POST",
          body: { email, password },
        },
      );

      setSessionData(response);
      startTransition(() => {
        router.push(response.user.campaigns.length > 0 ? "/dashboard" : "/onboarding");
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Something went wrong while authenticating.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.16),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.18),transparent_30%)]" />
      <div className="relative mx-auto grid min-h-screen w-full max-w-7xl gap-8 px-5 py-8 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:px-10">
        <section className="panel flex flex-col justify-between p-8 sm:p-10">
          <div className="space-y-8">
            <Logo />
            <div className="space-y-5">
              <p className="eyebrow">Agent-first growth</p>
              <h1 className="font-display text-4xl tracking-tight text-white sm:text-6xl">
                In the agent economy, CAC is just compute.
              </h1>
              <p className="max-w-xl text-base leading-8 text-slate-300 sm:text-lg">
                Launch an AI-powered acquisition campaign that makes Return on Compute the
                operating system for growth.
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Weekly AI shopping queries", value: "700M+" },
              { label: "Higher conversion than search", value: "6.6x" },
              { label: "Typical CAC vs Meta", value: "$0.50" },
            ].map((item) => (
              <div key={item.label} className="rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
                <p className="font-display text-3xl text-white">{item.value}</p>
                <p className="mt-2 text-sm text-slate-400">{item.label}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="panel flex items-center p-8 sm:p-10">
          <form onSubmit={handleSubmit} className="w-full space-y-6">
            <div className="space-y-3">
              <p className="eyebrow">{isSignup ? "Create account" : "Welcome back"}</p>
              <h2 className="font-display text-3xl text-white">
                {isSignup ? "Set up your first campaign" : "Get back to your dashboard"}
              </h2>
              <p className="text-sm leading-7 text-slate-400">
                Email and password only for v1. No OAuth detours, no setup maze.
              </p>
            </div>

            <label className="block space-y-2">
              <span className="text-sm text-slate-300">Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-[1.4rem] border border-white/12 bg-slate-950/70 px-5 py-4 text-white outline-none transition focus:border-emerald-400/50"
                placeholder="founder@brand.com"
                required
              />
            </label>

            <label className="block space-y-2">
              <span className="text-sm text-slate-300">Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-[1.4rem] border border-white/12 bg-slate-950/70 px-5 py-4 text-white outline-none transition focus:border-emerald-400/50"
                placeholder="At least 8 characters"
                required
              />
            </label>

            {error ? (
              <div className="rounded-[1.3rem] border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-full bg-emerald-400 px-5 py-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSubmitting
                ? isSignup
                  ? "Creating account..."
                  : "Signing in..."
                : isSignup
                  ? "Create Account"
                  : "Sign In"}
            </button>

            <p className="text-sm text-slate-400">
              {isSignup ? "Already have an account?" : "Need an account?"}{" "}
              <Link
                href={isSignup ? "/login" : "/signup"}
                className="font-medium text-emerald-300 hover:text-emerald-200"
              >
                {isSignup ? "Log in" : "Sign up"}
              </Link>
            </p>
          </form>
        </section>
      </div>
    </div>
  );
}
