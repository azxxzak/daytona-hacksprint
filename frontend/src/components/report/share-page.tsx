"use client";

import Link from "next/link";
import { Suspense } from "react";
import { Eye } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { LangSwitch } from "../app-shell";
import { useI18n } from "../i18n-provider";
import { Skeleton, buttonClass } from "../ui";
import { Report } from "./report";

/** Public, read-only report behind a share link (no sign-in). */
export function SharePage({ token }: { token: string }) {
  const { t } = useI18n();
  const { data, error, loading } = useApi<Test>(`/api/share/${encodeURIComponent(token)}`);
  const sample = token === "sample";
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between gap-3 px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="text-lg font-bold tracking-tight">{t("app.name")}</span>
            <span className="hidden items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-xs text-mute sm:inline-flex">
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
            <p className="mb-6 rounded-card bg-surface px-4 py-3 text-sm leading-relaxed text-mute">
              {sample ? t("share.sampleNote") : t("share.note")}
            </p>
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
