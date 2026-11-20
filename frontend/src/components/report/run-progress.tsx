"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check } from "lucide-react";
import type { Step, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { ProgressBar } from "../progress-bar";
import { Avatar, buttonClass, cx } from "../ui";

const STEPS = ["sandbox", "analysis", "viewers", "saving"] as const;

function useElapsed(since: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000));
}

export function RunProgress({ test }: { test: Test }) {
  const { t } = useI18n();
  const step: Step = test.progress?.step ?? "queued";
  const idx = step === "queued" ? -1 : STEPS.indexOf(step as (typeof STEPS)[number]);
  const pct = test.progress?.percent ?? 0;
  const elapsed = useElapsed(test.created_at);
  const reacted = useMemo(() => new Set((test.gaze ?? []).map((g) => g.id)), [test.gaze]);
  const people = test.personas ?? [];
  const mm = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  const desc = step === "queued" ? t("run.queuedD") : t(`run.${step as (typeof STEPS)[number]}D` as "run.sandboxD");

  return (
    <div className="mx-auto max-w-4xl pt-4 sm:pt-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> {t("common.back")}
      </Link>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="rounded-[18px] bg-surface p-7 sm:p-9">
          <p className="truncate text-xs text-mute" title={test.name}>{test.name}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">{t("run.title")}</h1>
          <p className="tnum mt-1 text-sm text-mute" aria-live="off">{t("run.elapsed", { t: mm })}</p>

          <ol className="mt-7 space-y-5">
            {STEPS.map((s, i) => {
              const state = i < idx ? "done" : i === idx ? "active" : "todo";
              return (
                <li key={s} className="flex items-start gap-3" aria-current={state === "active" ? "step" : undefined}>
                  <span
                    aria-hidden
                    className={cx(
                      "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2",
                      state === "done" && "border-ink bg-ink text-lime",
                      state === "active" && "border-ink bg-lime pulse",
                      state === "todo" && "border-line",
                    )}
                  >
                    {state === "done" && <Check size={11} strokeWidth={3} />}
                  </span>
                  <span className="min-w-0">
                    <span className={cx("block text-[15px]", state === "todo" ? "text-mute" : "font-medium")}>{t(`run.${s}`)}</span>
                    {state === "active" && <span className="fade-in mt-0.5 block text-[13px] leading-snug text-mute">{desc}</span>}
                  </span>
                </li>
              );
            })}
          </ol>

          <div className="mt-8">
            <ProgressBar percent={pct} label={t("run.percent", { n: Math.round(pct) })} />
            <div className="mt-2 flex items-center justify-between gap-4 text-sm">
              <p className="min-w-0 truncate text-mute" role="status" aria-live="polite">{test.progress?.message || t("run.queued")}</p>
              <p className="tnum shrink-0 font-medium">{Math.round(pct)}%</p>
            </div>
          </div>
        </div>

        <div className="rounded-[18px] bg-surface p-7 sm:p-9">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("run.panel")}</p>
            {people.length > 0 && <p className="tnum text-xs text-mute">{t("run.reacted", { n: reacted.size, total: people.length })}</p>}
          </div>
          {people.length === 0 ? (
            <div className="mt-4 grid grid-cols-5 gap-3" aria-hidden>
              {Array.from({ length: Math.min(test.viewers || 10, 15) }, (_, i) => <div key={i} className="pulse aspect-square rounded-full bg-canvas" style={{ animationDelay: `${i * 90}ms` }} />)}
            </div>
          ) : (
            <ul className="mt-4 grid grid-cols-5 gap-3 sm:grid-cols-6 md:grid-cols-5 lg:grid-cols-6">
              {people.map((p) => {
                const on = reacted.has(p.id);
                return (
                  <li key={p.id} title={p.name} className={cx("transition-all duration-500", on ? "scale-100 opacity-100" : "scale-95 opacity-35")}>
                    <Avatar src={p.avatar_url} name={p.name} color={p.color} rounded="rounded-full" className="aspect-square w-full" />
                    <span className="sr-only">{p.name}{on ? ` ✓` : ""}</span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-6 border-t border-line pt-4 text-xs leading-relaxed text-mute">{t("run.keepGoing")}</p>
        </div>
      </div>
    </div>
  );
}

export function RunFailed({ test }: { test: Test }) {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-xl pt-12 text-center">
      <h1 className="text-2xl font-bold">{t("run.failedTitle")}</h1>
      <p className="mt-2 text-sm text-mute">{t("run.failedBody")}</p>
      {test.error && <p role="alert" className="mx-auto mt-4 max-w-md rounded-card bg-surface px-4 py-3 text-left text-sm text-danger">{test.error}</p>}
      <div className="mt-6 flex justify-center gap-2">
        <Link href="/" className={buttonClass("outline")}>{t("common.back")}</Link>
        <Link href="/tests/new" className={buttonClass("primary")}>{t("run.failedNew")}</Link>
      </div>
    </div>
  );
}
