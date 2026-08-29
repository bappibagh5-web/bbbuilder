"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, LoaderCircle } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "./auth-provider";

function safeDestination() {
  const value = new URLSearchParams(window.location.search).get("next");
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export function LoginForm() {
  const { login, status } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace(safeDestination());
  }, [router, status]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace(safeDestination());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Sign in could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-slate-100 px-4 py-10">
      <section className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-sm sm:p-8">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#163451] text-white">
            <Building2 className="h-6 w-6" />
          </span>
          <div>
            <p className="text-sm font-bold tracking-[.12em] text-[#163451]">BB BUILDERS</p>
            <p className="text-xs uppercase tracking-[.14em] text-slate-500">Bid Management</p>
          </div>
        </div>
        <h1 className="mt-8 text-2xl font-semibold text-slate-950">Sign in</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">Use your BB Builders account to continue.</p>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium text-slate-700">
            Email address
            <input
              required
              autoComplete="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1.5 h-11 w-full rounded-lg border bg-white px-3 outline-none focus:border-blue-700"
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Password
            <input
              required
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1.5 h-11 w-full rounded-lg border bg-white px-3 outline-none focus:border-blue-700"
            />
          </label>
          {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <button
            disabled={submitting || status === "loading"}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#163451] px-4 text-sm font-semibold text-white transition hover:bg-[#102a43] disabled:opacity-60"
            type="submit"
          >
            {submitting && <LoaderCircle className="h-4 w-4 animate-spin" />}
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
