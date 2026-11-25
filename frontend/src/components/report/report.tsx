"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { ArrowLeft, Columns2, Link2, Repeat } from "lucide-react";
import { fmtTime, interestRange } from "@/lib/format";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { Button, buttonClass, cx, useDocTitle } from "../ui";
import { ShareDialog } from "./share-dialog";
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
  const [sharing, setSharing] = useState(false);
  const s = test.summary;
  const range = interestRange(test.gaze);
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
        {!test.read_only && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
              <ArrowLeft size={15} aria-hidden /> {t("common.back")}
            </Link>
            <div className="flex flex-wrap gap-2">
              <Link href={`/tests/new?panel_from=${test.id}`} className={buttonClass("outline", "sm")} title={t("ab.variantHint")}>
                <Repeat size={14} aria-hidden /> {t("ab.variant")}
              </Link>
              <Link href={`/compare?a=${test.id}`} className={buttonClass("outline", "sm")}>
                <Columns2 size={14} aria-hidden /> {t("ab.compare")}
              </Link>
              <Button size="sm" onClick={() => setSharing(true)}><Link2 size={14} aria-hidden /> {test.share_token ? t("share.shared") : t("share.button")}</Button>
            </div>
          </div>
        )}
        <div className="rounded-[20px] bg-surface p-6 sm:p-10">
          <p className="tnum text-xs text-mute">{date} · {t("rep.viewersCount", { n: test.viewers })}</p>
          {test.read_only ? <h1 className="mt-1 truncate text-base font-bold">{test.name}</h1> : <TestName test={test} onRenamed={onRenamed} />}
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
                  {range && <dd className="tnum mt-0.5 text-xs text-mute" title={t("rep.rangeHint")}>± {range.half.toFixed(1)} {t("rep.range95")}</dd>}
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
              {s.total < 20 && (
                <p className="mt-5 rounded-xl bg-canvas px-4 py-3 text-xs leading-relaxed text-mute">{t("rep.smallPanel", { n: s.total })}</p>
              )}
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
      {!test.read_only && sharing && <ShareDialog test={test} open onClose={() => setSharing(false)} onChanged={onRenamed} />}
    </div>
  );
}
