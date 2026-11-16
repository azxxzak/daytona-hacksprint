"use client";

import Link from "next/link";
import { useI18n } from "@/components/i18n-provider";
import { buttonClass, useDocTitle } from "@/components/ui";

export default function NotFound() {
  const { t } = useI18n();
  useDocTitle(t("err.pageTitle"));
  return (
    <main className="grid min-h-dvh place-items-center px-6 text-center">
      <div>
        <p className="tnum text-sm text-mute">404</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">{t("err.pageTitle")}</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-mute">{t("err.pageBody")}</p>
        <Link href="/" className={buttonClass("primary", "lg", "mt-6")}>{t("common.back")}</Link>
      </div>
    </main>
  );
}
