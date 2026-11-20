"use client";

import { useEffect, useState } from "react";
import { useI18n } from "./i18n-provider";
import { ProgressBar } from "./progress-bar";

/** Calm progress for work with no real percentage: time against a typical duration, capped so it never claims "done". */
export function LongProgress({ since, estimateSec, label }: { since: number; estimateSec: number; label: string }) {
  const { t } = useI18n();
  const [t0] = useState(() => since || Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const s = Math.max(0, Math.floor((now - t0) / 1000));
  const pct = Math.min(94, (s / estimateSec) * 100);
  return (
    <div role="status" className="space-y-2">
      <p className="text-sm text-ink">{label}</p>
      <ProgressBar percent={pct} label={label} />
      <p className="tnum flex justify-between text-xs text-mute"><span>{t("long.usually", { s: estimateSec })}</span><span>{t("long.elapsed", { s })}</span></p>
    </div>
  );
}
