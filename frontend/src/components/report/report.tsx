"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useRef } from "react";
import { ArrowLeft } from "lucide-react";
import { fmtTime, mean } from "@/lib/format";
import type { Persona, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { cx } from "../ui";
import { Interview } from "./interview";
import { Player, type PlayerHandle } from "./player";
import { Results } from "./results";
import { Viewers } from "./viewers";

const TABS = ["results", "viewers", "interview"] as const;
type Tab = (typeof TABS)[number];

export function Report({ test }: { test: Test }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const player = useRef<PlayerHandle>(null);
  const s = test.summary;

  const tabParam = params.get("tab");
  const tab: Tab = (TABS as readonly string[]).includes(tabParam ?? "") ? (tabParam as Tab) : "results";
  const pid = params.get("p");

  const go = useCallback((next: Tab, personaId?: string) => {
    const q = new URLSearchParams(params.toString());
    if (next === "results") q.delete("tab"); else q.set("tab", next);
    if (personaId) q.set("p", personaId); else if (next !== "interview") q.delete("p");
    const qs = q.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }, [params, router]);

  const interviewee: Persona | undefined = useMemo(() => {
    const byId = test.personas.find((p) => p.id === pid);
    if (byId) return byId;
    // default: the viewer who stayed most interested
    const avg = new Map<string, number[]>();
    for (const g of test.gaze) (avg.get(g.id) ?? avg.set(g.id, []).get(g.id)!).push(g.interest);
    return [...test.personas].sort((a, b) => (mean(avg.get(b.id) ?? []) ?? 0) - (mean(avg.get(a.id) ?? []) ?? 0))[0];
  }, [test.personas, test.gaze, pid]);

  const date = new Intl.DateTimeFormat(lang === "ja" ? "ja-JP" : "en-GB", { dateStyle: "long" }).format(new Date(test.created_at));
  const verdict = s
    ? [t("rep.verdict", { engaged: s.engaged, total: s.total }), s.low_t != null && test.media_kind === "video" ? t("rep.verdictDip", { t: fmtTime(s.low_t) }) : ""].filter(Boolean).join(" ")
    : "";

  const tabLabel = { results: "rep.tabResults", viewers: "rep.tabViewers", interview: "rep.tabInterview" } as const;
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
        <p className="tnum text-xs text-mute">{date} · {t("rep.viewersCount", { n: test.viewers })}</p>
        <h1 className="mt-1 truncate text-base font-bold" title={test.name}>{test.name}</h1>
        {s && (
          <>
            <p className="mt-2 max-w-4xl text-balance text-[28px] font-bold leading-snug tracking-tight sm:text-4xl">{verdict}</p>
            <p className="tnum mt-3 text-sm text-mute">
              {s.top_focus && <>{t("rep.topFocus")}: <span className="text-ink">{s.top_focus}</span> · </>}
              {t("rep.avgInterest")}: <span className="text-ink">{t("rep.outOf5", { v: s.avg_interest.toFixed(1) })}</span>
            </p>
          </>
        )}
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
          {tab === "viewers" && <Viewers test={test} onInterview={(p) => go("interview", p.id)} />}
          {tab === "interview" && interviewee && <Interview key={interviewee.id} test={test} persona={interviewee} onSelect={(p) => go("interview", p.id)} />}
        </div>
      </div>
    </div>
  );
}
