"use client";

import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { errorText } from "@/lib/errors";
import type { Talk, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { Skeleton, buttonClass, useDocTitle } from "../ui";
import { TalkView } from "./talk-view";

export function TalkPage({ testId, talkId }: { testId: string; talkId: string }) {
  const { t } = useI18n();
  const test = useApi<Test>(`/api/tests/${testId}`);
  const talk = useApi<Talk>(`/api/tests/${testId}/talks/${talkId}`);
  useDocTitle(talk.data?.title || t("talk.untitled"));
  const back = `/tests/${testId}?tab=viewers`;

  if (test.data && talk.data) return <TalkView key={talk.data.id} test={test.data} talk={talk.data} />;

  const err = test.error ?? talk.error;
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-canvas">
      {err ? (
        <div className="m-auto max-w-md px-6 text-center">
          <p role="alert" className="text-sm text-danger">{t("talk.loadError")} {errorText(err, t)}</p>
          <Link href={back} className={buttonClass("primary", "md", "mt-5")}>{t("common.back")}</Link>
        </div>
      ) : (
        <div role="status" aria-label={t("common.loading")} className="mx-auto w-full max-w-3xl space-y-4 px-6 pt-24">
          <Skeleton className="ml-auto h-12 w-2/3" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}
    </div>
  );
}
