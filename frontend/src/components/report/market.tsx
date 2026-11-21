"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Globe, Loader2, RefreshCw, Search } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { LongProgress } from "../long-progress";
import { useToast } from "../toast";
import { Button, Card, ErrorNote, SectionHeader, cx } from "../ui";

type Src = { id: number; title: string; url: string };
type Market = {
  product: { name: string; brand: string; category: string; confidence: "high" | "medium" | "low"; campaign?: string };
  headline: string;
  market: { point: string; src: number[] }[];
  competitors: { name: string; positioning: string; vs_ad: string; src: number[] }[];
  trends: { trend: string; so_what: string; src: number[] }[];
  fit: { market: string; panel: string; verdict: "aligned" | "gap" | "risk" }[];
  recommendations: { action: string; why: string; src: number[] }[];
  sources: Src[];
  queries: string[];
  research_model: string;
  generated_at: string;
};
type Resp = { status: "none" | "ready"; available: boolean; market: Market | null };

function Cite({ ids, sources }: { ids: number[]; sources: Src[] }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-0.5 align-baseline">
      {ids.map((i) => {
        const s = sources.find((x) => x.id === i);
        return s ? (
          <a
            key={i} href={s.url} target="_blank" rel="noopener noreferrer" title={s.title}
            className="tnum inline-grid h-[18px] min-w-[18px] place-items-center rounded-md bg-canvas px-1 text-[10px] font-semibold text-ink/70 no-underline hover:bg-ink hover:text-white"
          >
            {i}
          </a>
        ) : null;
      })}
    </span>
  );
}

function Block({ label, title, children }: { label: string; title: string; children: React.ReactNode }) {
  return (
    <section>
      <SectionHeader as="h3" label={label} title={title} />
      <div className="mt-5">{children}</div>
    </section>
  );
}

const VERDICT: Record<Market["fit"][number]["verdict"], string> = {
  aligned: "bg-lime text-ink",
  gap: "bg-ink text-white",
  risk: "bg-danger text-white",
};

export function MarketTab({ test }: { test: Test }) {
  const { t } = useI18n();
  const toast = useToast();
  const base = `/api/tests/${test.id}/market`;
  const [data, setData] = useState<Resp | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [since, setSince] = useState(0);

  useEffect(() => {
    api<Resp>(base).then(setData).catch((e) => setLoadError(errorText(e, t)));
  }, [base, t]);

  const run = useCallback(() => {
    setBusy(true);
    setSince(Date.now());
    api<Resp>(base, { method: "POST" })
      .then(setData)
      .catch((e) => toast.error(`${t("mk.error")} ${errorText(e, t)}`))
      .finally(() => setBusy(false));
  }, [base, t, toast]);

  if (loadError) return <ErrorNote>{loadError}</ErrorNote>;
  if (!data) return <p className="pulse text-sm text-mute">{t("common.loading")}</p>;

  if (busy) {
    return (
      <Card className="p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <Loader2 size={18} className="motion-safe:animate-spin" aria-hidden />
          <p className="font-bold">{t("mk.running")}</p>
        </div>
        <ol className="mt-4 space-y-1.5 text-sm text-mute">
          <li>1. {t("mk.step1")}</li>
          <li>2. {t("mk.step2")}</li>
        </ol>
        <div className="mt-5"><LongProgress since={since} estimateSec={110} label={t("mk.wait")} /></div>
      </Card>
    );
  }

  const m = data.market;
  if (!m) {
    return (
      <Card className="grid gap-6 p-6 sm:p-8 md:grid-cols-[1fr_auto] md:items-center">
        <div>
          <span aria-hidden className="grid size-11 place-items-center rounded-full bg-ink text-lime"><Globe size={20} /></span>
          <h3 className="mt-4 text-xl font-bold">{t("mk.emptyTitle")}</h3>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-mute">{t("mk.emptyBody")}</p>
          <ul className="mt-4 grid gap-1.5 text-sm sm:grid-cols-2">
            {(["mk.li1", "mk.li2", "mk.li3", "mk.li4"] as const).map((k) => (
              <li key={k} className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />{t(k)}</li>
            ))}
          </ul>
        </div>
        <div className="md:text-right">
          <Button onClick={run} disabled={!data.available}><Search size={16} aria-hidden /> {t("mk.run")}</Button>
          <p className="mt-2 text-xs text-mute">{data.available ? t("mk.time") : t("mk.off")}</p>
        </div>
      </Card>
    );
  }

  const S = m.sources;
  return (
    <div className="space-y-12">
      <Card className="overflow-hidden p-0">
        <div className="bg-ink p-6 text-white sm:p-8">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/60">{t("mk.identified")}</p>
          <h3 className="mt-2 text-2xl font-bold tracking-tight">{m.product.name}</h3>
          <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
            {[m.product.brand, m.product.category].filter(Boolean).map((x) => <span key={x} className="rounded-md bg-white/10 px-2 py-0.5">{x}</span>)}
            <span className={cx("rounded-md px-2 py-0.5 font-semibold", m.product.confidence === "high" ? "bg-lime text-ink" : "bg-white/20")}>
              {t("mk.confidence")}: {t(`mk.conf.${m.product.confidence}` as "mk.conf.high")}
            </span>
          </div>
          {m.product.campaign && <p className="mt-3 text-sm text-white/75">{t("mk.campaign")}: {m.product.campaign}</p>}
        </div>
        <p className="p-6 text-lg font-semibold leading-snug sm:p-8">{m.headline}</p>
      </Card>

      <Block label={t("mk.l.recs")} title={t("mk.t.recs")}>
        <ol className="space-y-3">
          {m.recommendations.map((r, i) => (
            <li key={i} className="grid grid-cols-[2rem_1fr] gap-4 rounded-card bg-surface p-5">
              <span aria-hidden className="tnum grid size-8 place-items-center rounded-full bg-ink text-sm font-bold text-lime">{i + 1}</span>
              <div>
                <p className="font-bold leading-snug">{r.action}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-ink/75">{r.why}<Cite ids={r.src} sources={S} /></p>
              </div>
            </li>
          ))}
        </ol>
      </Block>

      <Block label={t("mk.l.fit")} title={t("mk.t.fit")}>
        <div className="overflow-hidden rounded-card bg-surface">
          <div className="hidden grid-cols-[1fr_1fr_6rem] gap-6 border-b border-line px-5 py-3 text-xs font-medium text-mute md:grid">
            <span>{t("mk.col.market")}</span><span>{t("mk.col.panel")}</span><span className="text-right">{t("mk.col.verdict")}</span>
          </div>
          <ul className="divide-y divide-line">
            {m.fit.map((f, i) => (
              <li key={i} className="grid gap-3 px-5 py-4 text-sm leading-relaxed md:grid-cols-[1fr_1fr_6rem] md:gap-6">
                <p><span className="mr-1 text-xs font-semibold text-mute md:hidden">{t("mk.col.market")}:</span>{f.market}</p>
                <p><span className="mr-1 text-xs font-semibold text-mute md:hidden">{t("mk.col.panel")}:</span>{f.panel}</p>
                <span className={cx("h-fit w-fit rounded-full px-2.5 py-0.5 text-xs font-semibold md:justify-self-end", VERDICT[f.verdict])}>{t(`mk.v.${f.verdict}` as "mk.v.gap")}</span>
              </li>
            ))}
          </ul>
        </div>
      </Block>

      <div className="grid gap-12 lg:grid-cols-2">
        <Block label={t("mk.l.market")} title={t("mk.t.market")}>
          <ul className="space-y-3">
            {m.market.map((x, i) => (
              <li key={i} className="rounded-card bg-surface p-4 text-sm leading-relaxed">{x.point}<Cite ids={x.src} sources={S} /></li>
            ))}
          </ul>
        </Block>
        <Block label={t("mk.l.trends")} title={t("mk.t.trends")}>
          <ul className="space-y-3">
            {m.trends.map((x, i) => (
              <li key={i} className="rounded-card bg-surface p-4">
                <p className="text-sm font-bold leading-snug">{x.trend}<Cite ids={x.src} sources={S} /></p>
                <p className="mt-1.5 text-sm leading-relaxed text-ink/75">{x.so_what}</p>
              </li>
            ))}
          </ul>
        </Block>
      </div>

      <Block label={t("mk.l.comp")} title={t("mk.t.comp")}>
        <ul className="grid gap-3 md:grid-cols-2">
          {m.competitors.map((c, i) => (
            <li key={i} className="rounded-card bg-surface p-5">
              <p className="font-bold">{c.name}<Cite ids={c.src} sources={S} /></p>
              <p className="mt-2 text-sm leading-relaxed">{c.positioning}</p>
              <p className="mt-3 border-t border-line pt-3 text-sm leading-relaxed text-ink/75"><span className="font-semibold text-ink">{t("mk.vsAd")}: </span>{c.vs_ad}</p>
            </li>
          ))}
        </ul>
      </Block>

      <section aria-label={t("mk.sources")} className="rounded-card bg-surface p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-bold">{t("mk.sources")} <span className="tnum font-normal text-mute">({S.length})</span></h3>
          <Button variant="outline" size="sm" onClick={run}><RefreshCw size={14} aria-hidden /> {t("mk.rerun")}</Button>
        </div>
        <ol className="mt-4 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {S.map((s) => (
            <li key={s.id} className="flex min-w-0 gap-2">
              <span className="tnum w-5 shrink-0 text-right text-xs text-mute">{s.id}</span>
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-w-0 items-center gap-1 truncate underline-offset-4 hover:underline">
                <span className="truncate">{s.title}</span><ArrowUpRight size={12} className="shrink-0" aria-hidden />
              </a>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs leading-relaxed text-mute">
          {t("mk.method", { model: m.research_model, date: new Date(m.generated_at).toLocaleDateString() })}
        </p>
      </section>
    </div>
  );
}
