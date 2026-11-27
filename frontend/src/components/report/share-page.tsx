"use client";

import Link from "next/link";
import { Suspense } from "react";
import { Eye } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { LangSwitch } from "../app-shell";
import { useI18n } from "../i18n-provider";
import { Logo, Skeleton, buttonClass } from "../ui";
import { Report } from "./report";

/** Public, read-only report behind a share link (no sign-in). */
export function SharePage({ token }: { token: string }) {
  const { t } = useI18n();
  const { data, error, loading } = useApi<Test>(`/api/share/${encodeURIComponent(token)}`);
  const sample = token === "sample";
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-surface/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between gap-3 px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/login" className="rounded-lg"><Logo name={t("app.name")} /></Link>
            <span className="hidden items-center gap-1.5 rounded-full bg-canvas px-2.5 py-1 text-xs text-mute sm:inline-flex">
              <Eye size={13} aria-hidden /> {sample ? t("share.sampleBadge") : t("share.badge")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <LangSwitch />
            <Link href="/login" className={buttonClass("primary", "sm")}>{t("share.signIn")}</Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-8">
        {data ? (
          <>
            <div className="mb-6 rounded-card bg-surface shadow-card px-4 py-3 text-sm leading-relaxed text-mute">
              <p>{sample ? t("share.sampleNote") : t("share.note")}</p>
              {data.credit && <Credit c={data.credit} />}
            </div>
            <Suspense><Report test={data} onRenamed={() => {}} /></Suspense>
          </>
        ) : error && !loading ? (
          <div className="mx-auto max-w-md pt-16 text-center">
            <p role="alert" className="text-sm text-danger">{error.status === 404 ? t("share.gone") : errorText(error, t)}</p>
          </div>
        ) : (
          <div role="status" aria-label={t("common.loading")} className="space-y-6">
            <Skeleton className="h-40" />
            <Skeleton className="aspect-video" />
          </div>
        )}
      </main>
    </div>
  );
}

/** Attribution for an openly licensed sample ad (CC BY asks for source, license and a note of changes). */
function Credit({ c }: { c: NonNullable<Test["credit"]> }) {
  const { t } = useI18n();
  const link = "underline decoration-line underline-offset-2 hover:text-ink";
  return (
    <p className="mt-1.5 text-xs">
      {t("share.credit")}:{" "}
      {c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer" className={link}>{c.text}</a> : c.text}
      {c.license && (
        <>
          {" · "}
          {c.license_url ? <a href={c.license_url} target="_blank" rel="noopener noreferrer" className={link}>{c.license}</a> : c.license}
        </>
      )}
      {". "}{t("share.creditChanges")}
    </p>
  );
}
