"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { ArrowLeft, BarChart3, Columns2, Crosshair, Globe2, Link2, Repeat, Target, UsersRound } from "lucide-react";
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
  const tabIcon = { results: BarChart3, viewers: UsersRound, decision: Target, market: Globe2 } as const;
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
              <Button size="sm" className="h-8" onClick={() => setSharing(true)}><Link2 size={14} aria-hidden /> {test.share_token ? t("share.shared") : t("share.button")}</Button>
            </div>
          </div>
        )}
        <div className="relative overflow-hidden rounded-[24px] bg-surface p-6 shadow-card sm:p-10">
          <div aria-hidden className="dots-ink pointer-events-none absolute inset-y-0 right-0 w-1/3 [mask-image:linear-gradient(to_left,black,transparent)]" />
          <p className="tnum relative flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-mute">
            <span>{date}</span>
            <span aria-hidden className="size-1 rounded-full bg-line" />
            <span>{t("rep.viewersCount", { n: test.viewers })}</span>
          </p>
          <div className="relative">
            {test.read_only ? <h1 className="mt-1 truncate text-base font-bold">{test.name}</h1> : <TestName test={test} onRenamed={onRenamed} />}
          </div>
          {s && (
            <>
              <p className="relative mt-4 max-w-4xl text-balance text-[28px] font-bold leading-snug tracking-[-0.025em] sm:text-[46px] sm:leading-[1.18]">
                <Marked text={verdict} />
              </p>
              <dl className="relative mt-8 grid grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
                <Stat label={t("rep.engagedLabel")}>
                  <dd className="tnum text-[28px] font-bold leading-none tracking-[-0.02em]">{s.engaged}<span className="text-base font-medium text-mute"> / {s.total}</span></dd>
                  <dd className="mt-3"><ViewerDots engaged={s.engaged} total={s.total} /></dd>
                </Stat>
                <Stat label={t("rep.avgInterest")}>
                  <dd className="tnum text-[28px] font-bold leading-none tracking-[-0.02em]">{s.avg_interest.toFixed(1)}<span className="text-base font-medium text-mute"> / 5</span></dd>
                  <dd className="mt-3"><Scale mean={s.avg_interest} half={range?.half} /></dd>
                  {range && <dd className="tnum mt-1.5 text-[11px] text-mute" title={t("rep.rangeHint")}>± {range.half.toFixed(1)} {t("rep.range95")}</dd>}
                </Stat>
                {s.low_t != null && test.media_kind === "video" && (
                  <Stat label={t("rep.lowLabel")}>
                    <dd className="tnum text-[28px] font-bold leading-none tracking-[-0.02em]">{fmtTime(s.low_t)}</dd>
                    {s.curve.length > 2 && <dd className="mt-2"><Spark curve={s.curve} at={s.low_t} /></dd>}
                  </Stat>
                )}
                {s.top_focus && (
                  <Stat label={t("rep.topFocus")}>
                    <dd className="flex items-start gap-2 text-[17px] font-bold leading-snug">
                      <Crosshair size={16} aria-hidden className="mt-1 shrink-0 text-mute" />
                      <span>{s.top_focus}</span>
                    </dd>
                  </Stat>
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
        <div className="sticky top-14 z-20 -mx-4 bg-canvas/85 px-4 py-2.5 backdrop-blur-xl sm:-mx-8 sm:px-8">
          <div role="tablist" aria-label={t("rep.tabs")} className="flex w-full gap-0.5 overflow-x-auto rounded-full bg-[#e7e7ea] p-1 sm:w-fit">
            {TABS.map((k, i) => {
              const Icon = tabIcon[k];
              return (
                <button
                  key={k} id={`tab-${k}`} role="tab" type="button" aria-selected={tab === k} aria-controls={`panel-${k}`}
                  tabIndex={tab === k ? 0 : -1} onClick={() => go(k)} onKeyDown={(e) => onKey(e, i)}
                  className={cx(
                    "flex h-9 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium transition-[color,background-color,box-shadow]",
                    tab === k ? "bg-surface text-ink shadow-[0_1px_3px_rgb(17_17_17/0.14)]" : "text-mute hover:text-ink",
                  )}
                >
                  <Icon size={15} aria-hidden className={cx(tab === k && "text-ink")} />
                  {t(tabLabel[k])}
                </button>
              );
            })}
          </div>
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} key={tab} className="rise pt-6">
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

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl border border-line bg-surface/70 p-3.5 backdrop-blur-sm sm:p-4">
      <dt className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-mute sm:text-[11px]">{label}</dt>
      {children}
    </div>
  );
}

/** Numbers and times in the headline get a lime marker underneath. */
function Marked({ text }: { text: string }) {
  const parts = text.split(/(\d+(?:[:.]\d+)?(?:\s*(?:\/|of|人中|人)\s*\d+)?)/);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <span key={i} className="tnum box-decoration-clone bg-[linear-gradient(transparent_62%,#c8f031_62%,#c8f031_92%,transparent_92%)] px-0.5">{p}</span>
        ) : (
          p
        ),
      )}
    </>
  );
}

/** One dot per viewer: filled for those who stayed interested. */
function ViewerDots({ engaged, total }: { engaged: number; total: number }) {
  if (total > 120) return null;
  return (
    <span aria-hidden className="flex flex-wrap gap-[3px]">
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={cx("size-[6px] rounded-full sm:size-[7px]", i < engaged ? "bg-ink" : "bg-[#dcdce0]")} />
      ))}
    </span>
  );
}

/** 1–5 scale with the mean as a mark and the 95% range as a band. */
function Scale({ mean, half }: { mean: number; half?: number }) {
  const pos = (v: number) => `${((Math.min(5, Math.max(1, v)) - 1) / 4) * 100}%`;
  return (
    <span aria-hidden className="block">
      <span className="relative block h-2 rounded-full bg-[linear-gradient(90deg,#e4e4e8,#e4e4e8_40%,#d6ef7a_75%,#c8f031)]">
        {half != null && (
          <span className="absolute inset-y-0 rounded-full bg-ink/15" style={{ left: pos(mean - half), right: `calc(100% - ${pos(mean + half)})` }} />
        )}
        <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-surface bg-ink shadow" style={{ left: pos(mean) }} />
      </span>
      <span className="tnum mt-1 flex justify-between text-[10px] text-mute"><span>1</span><span>5</span></span>
    </span>
  );
}

/** Tiny interest curve with the biggest dip marked. */
function Spark({ curve, at }: { curve: { t: number; avg: number }[]; at: number }) {
  const t0 = curve[0].t;
  const t1 = curve[curve.length - 1].t || 1;
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * 100;
  const y = (v: number) => 30 - ((Math.min(5, Math.max(1, v)) - 1) / 4) * 26;
  const d = curve.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(2)} ${y(p.avg).toFixed(2)}`).join(" ");
  const low = curve.reduce((a, p) => (Math.abs(p.t - at) < Math.abs(a.t - at) ? p : a), curve[0]);
  return (
    <svg aria-hidden viewBox="0 0 100 32" preserveAspectRatio="none" className="h-10 w-full overflow-visible">
      <path d={`${d} L100 32 L0 32Z`} fill="#c8f031" fillOpacity="0.25" />
      <path d={d} fill="none" stroke="#111" strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <line x1={x(low.t)} x2={x(low.t)} y1="0" y2="32" stroke="#b3261e" strokeWidth="1.5" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
