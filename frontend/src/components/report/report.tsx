"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef } from "react";
import { ArrowLeft } from "lucide-react";
import { fmtTime } from "@/lib/format";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { cx, useDocTitle } from "../ui";
import { Player, type PlayerHandle } from "./player";
import { MarketTab } from "./market";
import { DecisionReportTab } from "./decision-report";
import { Results } from "./results";
import { TestName } from "./test-name";
import { Viewers } from "./viewers";

const TABS = ["results", "viewers", "decision", "market"] as const;
type Tab = (typeof TABS)[number];

export function Report({ test, onRenamed }: { test: Test; onRenamed: () => void }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const player = useRef<PlayerHandle>(null);
  const s = test.summary;
  useDocTitle(test.name);

  const tabParam = params.get("tab");
  const tab: Tab = (TABS as readonly string[]).includes(tabParam ?? "") ? (tabParam as Tab) : "results";

  const go = useCallback((next: Tab) => {
    const q = new URLSearchParams(params.toString());
    if (next === "results") q.delete("tab"); else q.set("tab", next);
    const qs = q.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }, [params, router]);

  const date = new Intl.DateTimeFormat(lang === "ja" ? "ja-JP" : "en-GB", { dateStyle: "long" }).format(new Date(test.created_at));
  const verdict = s
    ? [t("rep.verdict", { engaged: s.engaged, total: s.total }), s.low_t != null && test.media_kind === "video" ? t("rep.verdictDip", { t: fmtTime(s.low_t) }) : ""].filter(Boolean).join(lang === "ja" ? "" : " ")
    : "";

  const tabLabel = { results: "rep.tabResults", viewers: "rep.tabViewers", decision: "rep.tabDecision", market: "rep.tabMarket" } as const;
  const onKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const n = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    go(n);
    requestAnimationFrame(() => document.getElementById(`tab-${n}`)?.focus());
  };

  return (
    <div className="space-y-8">
      <header>
        <Link href="/" className="mb-4 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
          <ArrowLeft size={15} aria-hidden /> {t("common.back")}
        </Link>
        <div className="rounded-[20px] bg-surface p-6 sm:p-10">
          <p className="tnum text-xs text-mute">{date} · {t("rep.viewersCount", { n: test.viewers })}</p>
          <TestName test={test} onRenamed={onRenamed} />
          {s && (
            <>
              <p className="mt-4 max-w-4xl text-balance text-[28px] font-bold leading-snug tracking-tight sm:text-[44px] sm:leading-[1.25]">{verdict}</p>
              <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-line pt-6 sm:grid-cols-4">
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("rep.engagedLabel")}</dt>
                  <dd className="tnum mt-1 text-2xl font-bold">{s.engaged}<span className="text-base font-medium text-mute"> / {s.total}</span></dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("rep.avgInterest")}</dt>
                  <dd className="tnum mt-1 text-2xl font-bold">{s.avg_interest.toFixed(1)}<span className="text-base font-medium text-mute"> / 5</span></dd>
                </div>
                {s.low_t != null && test.media_kind === "video" && (
                  <div>
                    <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("rep.lowLabel")}</dt>
                    <dd className="tnum mt-1 text-2xl font-bold">{fmtTime(s.low_t)}</dd>
                  </div>
                )}
                {s.top_focus && (
                  <div className="col-span-2 sm:col-span-1">
                    <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("rep.topFocus")}</dt>
                    <dd className="mt-1 text-base font-bold leading-snug">{s.top_focus}</dd>
                  </div>
                )}
              </dl>
            </>
          )}
        </div>
      </header>

      <Player ref={player} test={test} />

      <div>
        <div role="tablist" aria-label={t("rep.tabs")} className="flex gap-6 border-b-2 border-ink">
          {TABS.map((k, i) => (
            <button
              key={k} id={`tab-${k}`} role="tab" type="button" aria-selected={tab === k} aria-controls={`panel-${k}`}
              tabIndex={tab === k ? 0 : -1} onClick={() => go(k)} onKeyDown={(e) => onKey(e, i)}
              className={cx("-mb-[2px] border-b-2 py-3 text-[15px] font-medium transition-colors", tab === k ? "border-lime text-ink" : "border-transparent text-mute hover:text-ink")}
            >
              <span className={cx(tab === k && "border-b-2 border-ink pb-[10px]")}>{t(tabLabel[k])}</span>
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="pt-6">
          {tab === "results" && <Results test={test} onSeek={(sec) => player.current?.seek(sec)} />}
          {tab === "viewers" && <Viewers test={test} />}
          {tab === "decision" && <DecisionReportTab test={test} />}
          {tab === "market" && <MarketTab test={test} />}
        </div>
      </div>
    </div>
  );
}
