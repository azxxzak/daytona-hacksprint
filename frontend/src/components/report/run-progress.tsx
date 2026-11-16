"use client";

import Link from "next/link";
import { ArrowLeft, Check } from "lucide-react";
import type { Step, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { ProgressBar } from "../progress-bar";
import { buttonClass, cx } from "../ui";

const STEPS = ["sandbox", "analysis", "viewers", "saving"] as const;

export function RunProgress({ test }: { test: Test }) {
  const { t } = useI18n();
  const step: Step = test.progress?.step ?? "queued";
  const idx = step === "queued" ? -1 : STEPS.indexOf(step as (typeof STEPS)[number]);
  const pct = test.progress?.percent ?? 0;

  return (
    <div className="mx-auto max-w-xl pt-6 sm:pt-12">
      <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> {t("common.back")}
      </Link>
      <div className="rounded-[18px] bg-surface p-7 sm:p-10">
        <p className="truncate text-xs text-mute" title={test.name}>{test.name}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight">{t("run.title")}</h1>
        <p className="mt-1 text-sm text-mute">{t("run.sub")}</p>

        <ol className="mt-8 space-y-4">
          {STEPS.map((s, i) => {
            const state = i < idx ? "done" : i === idx ? "active" : "todo";
            return (
              <li key={s} className="flex items-center gap-3" aria-current={state === "active" ? "step" : undefined}>
                <span
                  aria-hidden
                  className={cx(
                    "grid size-5 shrink-0 place-items-center rounded-full border-2",
                    state === "done" && "border-ink bg-ink text-lime",
                    state === "active" && "border-ink bg-lime pulse",
                    state === "todo" && "border-line",
                  )}
                >
                  {state === "done" && <Check size={11} strokeWidth={3} />}
                </span>
                <span className={cx("text-[15px]", state === "todo" ? "text-mute" : "font-medium")}>{t(`run.${s}`)}</span>
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
