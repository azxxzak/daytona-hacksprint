"use client";

import Link from "next/link";
import { Suspense } from "react";
import { usePolled } from "@/lib/hooks";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { Button, buttonClass } from "../ui";
import { Report } from "./report";
import { RunFailed, RunProgress } from "./run-progress";

export function TestPage({ id }: { id: string }) {
  const { t } = useI18n();
  const { data, error, loading, reload } = usePolled<Test>(`/api/tests/${id}`, (d) => d.status === "queued" || d.status === "running", 2000);

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
    return <div className="pulse mx-auto h-64 max-w-xl rounded-[18px] bg-surface" role="status" aria-label={t("common.loading")} />;
  }
  if (data.status === "queued" || data.status === "running") return <RunProgress test={data} />;
  if (data.status === "failed" || !data.summary) return <RunFailed test={data} />;
  return (
    <Suspense>
      <Report test={data} />
    </Suspense>
  );
}
