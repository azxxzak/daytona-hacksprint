"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { ArrowRight, Eye } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { LangSwitch } from "@/components/app-shell";
import { useI18n } from "@/components/i18n-provider";
import { Button, Logo, Spinner, useDocTitle } from "@/components/ui";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const errId = useId();
  const [sample, setSample] = useState(false);
  useDocTitle(t("login.title"));
  useEffect(() => {
    api<{ available: boolean }>("/api/share/sample/available", { noRedirect: true }).then((r) => setSample(r.available)).catch(() => {});
  }, []);

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

  const field =
    "mt-1.5 h-12 w-full rounded-xl border border-line bg-canvas px-4 text-[15px] transition-[background-color,border-color,box-shadow] placeholder:text-mute/60 hover:border-[#cfcfd4] focus:border-ink focus:bg-white";

  return (
    <main className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section className="relative flex flex-col px-5 py-5 sm:px-10 sm:py-8">
        <div className="flex items-center justify-between">
          <Logo name={t("app.name")} />
          <LangSwitch />
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-12">
          <form onSubmit={submit} className="rise" aria-describedby={error ? errId : undefined}>
            <h1 className="text-[32px] font-bold leading-tight tracking-[-0.02em]">{t("login.title")}</h1>
            <p className="mt-2 text-[15px] text-mute">{t("login.subtitle")}</p>

            <label className="mt-9 block text-sm font-medium" htmlFor="email">
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
              className={field}
            />
            <label className="mt-5 block text-sm font-medium" htmlFor="password">
              {t("login.password")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
            />
            <div id={errId} role="alert" className="min-h-6 pt-3 text-sm text-danger">
              {error}
            </div>
            <Button type="submit" size="lg" className="mt-2 w-full" disabled={busy}>
              {busy && <Spinner />}
              {busy ? t("login.submitting") : t("login.submit")}
            </Button>
          </form>
          {sample && (
            <Link
              href="/share/sample"
              className="group mt-8 flex items-center gap-3 rounded-2xl border border-line bg-surface p-3 pr-4 text-sm shadow-card transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-lift"
            >
              <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-lime">
                <Eye size={18} />
              </span>
              <span className="flex-1 font-medium">{t("login.sample")}</span>
              <ArrowRight size={16} aria-hidden className="text-mute transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />
            </Link>
          )}
        </div>
      </section>
      <HeroPanel />
    </main>
  );
}

/** Brand panel: an illustrated ad frame with an attention map, two viewer thoughts and an interest curve. */
function HeroPanel() {
  const { t } = useI18n();
  return (
    <aside aria-hidden className="relative m-3 hidden overflow-hidden rounded-[28px] bg-ink text-white lg:flex lg:flex-col">
      <div className="dots absolute inset-0" />
      <div className="absolute -right-32 -top-32 size-[420px] rounded-full bg-lime/20 blur-3xl" />
      <div className="relative flex flex-1 flex-col justify-between p-12 xl:p-16">
        <div className="max-w-[30rem]">
          <p className="text-balance text-[40px] font-bold leading-[1.15] tracking-[-0.025em] xl:text-[48px]">{t("login.heroTitle")}</p>
          <p className="mt-5 max-w-[28rem] text-[15px] leading-relaxed text-white/60">{t("login.heroSub")}</p>
        </div>

        <div className="relative mt-12">
          <span className="absolute -top-7 right-0 text-[11px] font-medium uppercase tracking-[0.14em] text-white/35">{t("login.heroExample")}</span>
          <div className="relative aspect-video overflow-hidden rounded-2xl bg-[linear-gradient(150deg,#3d4a52_0%,#262e33_55%,#181c1f_100%)] ring-1 ring-white/10">
            {/* an abstract ad layout: headline, copy, button, product */}
            <div className="absolute left-[8%] top-[24%] h-[7%] w-[38%] rounded-full bg-white/90" />
            <div className="absolute left-[8%] top-[35%] h-[7%] w-[28%] rounded-full bg-white/90" />
            <div className="absolute left-[8%] top-[50%] h-[3.5%] w-[34%] rounded-full bg-white/30" />
            <div className="absolute left-[8%] top-[57%] h-[3.5%] w-[26%] rounded-full bg-white/30" />
            <div className="absolute left-[8%] top-[70%] h-[10%] w-[17%] rounded-full bg-lime" />
            <div className="absolute right-[12%] top-1/2 aspect-square w-[30%] -translate-y-1/2 rounded-full bg-[radial-gradient(circle_at_35%_30%,#f4f1ea,#c9c1b2_45%,#7d756a_100%)] shadow-[0_30px_50px_-20px_rgb(0_0_0/0.7)]" />
            <div className="absolute right-[21%] top-[30%] h-[40%] w-[12%] rounded-[40%_40%_18%_18%] bg-[linear-gradient(90deg,#2b2b2e,#4a4a50_50%,#2b2b2e)]" />
            {/* attention map */}
            <div className="hero-blob absolute left-[60%] top-[22%] aspect-square w-[30%] rounded-full bg-[radial-gradient(circle,rgb(255_70_40/0.85),rgb(255_190_40/0.5)_40%,rgb(120_230_90/0.25)_65%,transparent_72%)] mix-blend-screen blur-md" />
            <div className="hero-blob-2 absolute left-[4%] top-[10%] aspect-square w-[26%] rounded-full bg-[radial-gradient(circle,rgb(255_190_40/0.7),rgb(120_230_90/0.3)_50%,transparent_70%)] mix-blend-screen blur-md" />
            {/* viewer faces */}
            <Face at="left-[74%] top-[44%]" c="#c8f031" i="A" />
            <Face at="left-[20%] top-[30%]" c="#7fd3ff" i="K" />
            <Face at="left-[30%] top-[54%]" c="#ffb36b" i="M" />
            <div className="absolute bottom-0 inset-x-0 h-1 bg-white/10"><div className="h-full w-[38%] bg-lime" /></div>
          </div>

          <Thought className="-right-6 top-[6%]" c="#c8f031" i="A" text={t("login.heroT1")} />
          <Thought className="-left-6 top-[66%]" c="#ffb36b" i="M" text={t("login.heroT2")} />

          <div className="mt-6 rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/45">{t("login.heroCurve")}</p>
            <svg viewBox="0 0 400 60" className="mt-2 h-14 w-full" preserveAspectRatio="none">
              <defs>
                <linearGradient id="hero-fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stopColor="#c8f031" stopOpacity="0.35" />
                  <stop offset="1" stopColor="#c8f031" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d="M0 22 C40 14 70 10 110 16 S170 30 200 26 S250 12 290 30 S350 52 400 44 L400 60 L0 60Z" fill="url(#hero-fill)" />
              <path d="M0 22 C40 14 70 10 110 16 S170 30 200 26 S250 12 290 30 S350 52 400 44" fill="none" stroke="#c8f031" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
              <line x1="152" x2="152" y1="0" y2="60" stroke="white" strokeOpacity="0.35" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
        </div>
      </div>
    </aside>
  );
}

function Face({ at, c, i }: { at: string; c: string; i: string }) {
  return (
    <span className={`absolute ${at} grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#2a2a2e] text-xs font-bold text-white`} style={{ boxShadow: `0 0 0 2.5px ${c}, 0 6px 16px rgb(0 0 0 / 0.4)` }}>
      {i}
    </span>
  );
}

function Thought({ className, c, i, text }: { className: string; c: string; i: string; text: string }) {
  return (
    <div className={`absolute ${className} flex max-w-[260px] items-start gap-2.5 rounded-2xl bg-white p-3 pr-4 text-[13px] leading-snug text-ink shadow-[0_20px_40px_-12px_rgb(0_0_0/0.5)]`}>
      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#2a2a2e] text-[11px] font-bold text-white" style={{ boxShadow: `0 0 0 2px ${c}` }}>{i}</span>
      <span className="pt-0.5">{text}</span>
    </div>
  );
}
