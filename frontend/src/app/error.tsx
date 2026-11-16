"use client";

import Link from "next/link";
import { useI18n } from "@/components/i18n-provider";
import { Button, buttonClass } from "@/components/ui";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  return (
    <main className="grid min-h-dvh place-items-center px-6 text-center">
      <div role="alert">
        <h1 className="text-3xl font-bold tracking-tight">{t("err.boundaryTitle")}</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-mute">{t("err.boundaryBody")}</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button size="lg" onClick={reset}>{t("common.retry")}</Button>
          <Link href="/" className={buttonClass("outline", "lg")}>{t("common.back")}</Link>
        </div>
      </div>
    </main>
  );
}
