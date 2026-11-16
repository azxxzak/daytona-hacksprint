"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { LangSwitch } from "@/components/app-shell";
import { useI18n } from "@/components/i18n-provider";
import { Button, Spinner } from "@/components/ui";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errId = useId();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/login", { method: "POST", json: { email, password }, noRedirect: true });
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError(err.message || t("login.badCreds"));
      else if (err instanceof ApiError && err.status === 429) setError(err.message || t("login.tooMany"));
      else setError(errorText(err, t));
      setBusy(false);
    }
  };

  return (
    <main className="relative grid min-h-dvh place-items-center px-4">
      <div className="absolute right-4 top-4 sm:right-8 sm:top-5">
        <LangSwitch />
      </div>
      <div className="w-full max-w-[400px]">
        <p className="mb-8 text-center text-xl font-bold tracking-tight">{t("app.name")}</p>
        <form onSubmit={submit} className="rounded-[18px] bg-surface p-7 sm:p-9" aria-describedby={error ? errId : undefined}>
          <h1 className="text-2xl font-bold tracking-tight">{t("login.title")}</h1>
          <p className="mt-1 text-sm text-mute">{t("login.subtitle")}</p>

          <label className="mt-7 block text-sm font-medium" htmlFor="email">
            {t("login.email")}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1.5 h-11 w-full rounded-xl border border-line bg-canvas px-3.5 text-[15px] focus:bg-white"
          />
          <label className="mt-4 block text-sm font-medium" htmlFor="password">
            {t("login.password")}
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1.5 h-11 w-full rounded-xl border border-line bg-canvas px-3.5 text-[15px] focus:bg-white"
          />
          <div id={errId} role="alert" className="min-h-6 pt-3 text-sm text-danger">
            {error}
          </div>
          <Button type="submit" size="lg" className="mt-2 w-full" disabled={busy}>
            {busy && <Spinner />}
            {busy ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>
      </div>
    </main>
  );
}
