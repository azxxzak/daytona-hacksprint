"use client";

import Link from "next/link";
import { Suspense } from "react";
import { usePolled } from "@/lib/hooks";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { Button, Skeleton, buttonClass, useDocTitle } from "../ui";
import { Report } from "./report";
import { RunFailed, RunProgress } from "./run-progress";

export function TestPage({ id }: { id: string }) {
  const { t } = useI18n();
  const { data, error, loading, reload } = usePolled<Test>(`/api/tests/${id}`, (d) => d.status === "queued" || d.status === "running", 2000);

  useDocTitle(data?.name);
  if (!data) {
    if (error && !loading) {
      return (
        <div className="mx-auto max-w-md pt-16 text-center">
          <p role="alert" className="text-sm text-danger">{errorText(error, t)}</p>
          <div className="mt-5 flex justify-center gap-2">
            {error.status !== 404 && <Button variant="outline" onClick={reload}>{t("common.retry")}</Button>}
            <Link href="/" className={buttonClass("primary")}>{t("common.back")}</Link>
          </div>
        </div>
      );
    }
    return <ReportSkeleton label={t("common.loading")} />;
  }
  if (data.status === "queued" || data.status === "running") return <RunProgress test={data} />;
  if (data.status === "failed" || !data.summary) return <RunFailed test={data} />;
  return (
    <Suspense>
      <Report test={data} onRenamed={reload} />
    </Suspense>
  );
}

function ReportSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-10 w-full max-w-3xl" />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Skeleton className="aspect-video" />
        <Skeleton className="h-80" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
