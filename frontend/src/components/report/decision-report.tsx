"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, RefreshCw, Sparkles } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { DecisionReport, Test } from "@/lib/types";
import { apiBase } from "@/lib/format";
import { useI18n } from "../i18n-provider";
import { useToast } from "../toast";
import { LongProgress } from "../long-progress";
import { Button, Card, ErrorNote, SectionHeader, Skeleton, cx } from "../ui";

type State = { status: "none" | "generating" | "ready" | "failed"; report: DecisionReport | null; error?: string };

async function download(url: string, fallback: string): Promise<void> {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m ? decodeURIComponent(m[1]) : fallback;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{label}</p>
      <p className="mt-0.5 text-sm leading-relaxed">{children}</p>
    </div>
  );
}

function Ready({ r, test, onRegenerate }: { r: DecisionReport; test: Test; onRegenerate?: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState<"pptx" | "pdf" | null>(null);
  const [noPdf, setNoPdf] = useState(false);
  const base = `${apiBase(test)}/report`;

  const get = async (kind: "pptx" | "pdf") => {
    setBusy(kind);
    try {
      await download(`${base}.${kind}`, `adlens-report.${kind}`);
    } catch (e) {
      if (kind === "pdf" && e instanceof ApiError && e.status === 501) setNoPdf(true);
      else toast.error(`${t("dr.downloadError")} ${errorText(e, t)}`);
    } finally {
      setBusy(null);
    }
  };

  const cols = [
    { v: "win" as const, label: t("dr.win"), dot: "bg-lime border border-ink" },
    { v: "grow" as const, label: t("dr.grow"), dot: "bg-ink" },
    { v: "deprioritize" as const, label: t("dr.deprioritize"), dot: "bg-line" },
  ];
  const horizons = [
    { h: "48h" as const, label: t("dr.h48h") },
    { h: "2w" as const, label: t("dr.h2w") },
    { h: "6w" as const, label: t("dr.h6w") },
  ];

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("dr.label")}</p>
          {r.decision_question && <p className="mt-1 text-lg font-bold leading-snug">{r.decision_question}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => get("pptx")} disabled={busy !== null}><Download size={14} aria-hidden /> {t("dr.pptx")}</Button>
          {!noPdf && !test.read_only && <Button size="sm" variant="outline" onClick={() => get("pdf")} disabled={busy !== null}><Download size={14} aria-hidden /> {t("dr.pdf")}</Button>}
          {onRegenerate && <Button size="sm" variant="ghost" onClick={onRegenerate}><RefreshCw size={14} aria-hidden /> {t("dr.regenerate")}</Button>}
        </div>
      </div>

      <Card className="p-6 sm:p-10">
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("dr.thesis")}</p>
        <p className="mt-2 text-balance text-2xl font-bold leading-snug tracking-tight sm:text-4xl">{r.thesis}</p>
      </Card>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {r.headline_cards.slice(0, 4).map((c) => (
          <li key={c.label} className="rounded-card bg-surface p-5">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{c.label}</p>
            <p className="mt-2 text-xl font-bold leading-snug">{c.value}</p>
            <p className="mt-1.5 text-sm leading-snug text-mute">{c.note}</p>
          </li>
        ))}
      </ul>

      <section>
        <SectionHeader as="h3" title={t("dr.insights")} />
        <ol className="mt-5 space-y-4">
          {r.insights.map((i, n) => (
            <li key={i.title} className="grid grid-cols-[2.25rem_1fr] gap-4 rounded-card bg-surface p-5 sm:p-6">
              <span className="tnum grid size-9 place-items-center rounded-full bg-ink text-sm font-bold text-lime" aria-hidden>{n + 1}</span>
              <div className="min-w-0">
                <h4 className="text-lg font-bold leading-snug"><span className="sr-only">{n + 1}. </span>{i.title}</h4>
                <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-3">
                  <Block label={t("dr.evidence")}>{i.evidence}</Block>
                  <Block label={t("dr.soWhat")}>{i.so_what}</Block>
                  <Block label={t("dr.nowWhat")}>{i.now_what}</Block>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <SectionHeader as="h3" title={t("dr.segments")} />
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
          {cols.map((c) => {
            const items = r.segments.filter((s) => s.verdict === c.v);
            return (
              <div key={c.v} className="rounded-card bg-surface p-5">
                <h4 className="flex items-center gap-2 text-sm font-bold"><span className={cx("size-2.5 rounded-full", c.dot)} aria-hidden />{c.label}</h4>
                <ul className="mt-4 space-y-4">
                  {items.length === 0 && <li className="text-sm text-mute">–</li>}
                  {items.map((s) => (
                    <li key={s.segment}>
                      <span className="inline-block rounded-full bg-canvas px-3 py-0.5 text-sm font-medium">{s.segment}</span>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink/80">{s.why}</p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      {r.tensions.length > 0 && (
        <section>
          <SectionHeader as="h3" title={t("dr.tensions")} />
          <ul className="mt-5 space-y-3">
            {r.tensions.map((x) => (
              <li key={x.tension} className="grid grid-cols-1 items-start gap-3 rounded-card bg-surface p-5 md:grid-cols-[1fr_auto_1fr]">
                <p className="text-[15px] font-bold leading-snug">{x.tension}</p>
                <span aria-hidden className="hidden pt-0.5 text-xl text-mute md:block">→</span>
                <p className="text-sm leading-relaxed"><span className="sr-only">→ </span>{x.strategy}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <SectionHeader as="h3" title={t("dr.actions")} />
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
          {horizons.map((h) => (
            <div key={h.h} className="rounded-card bg-surface p-5">
              <h4 className="flex items-center gap-2 border-b-2 border-ink pb-2 text-sm font-bold"><span className="size-2.5 rounded-full bg-lime ring-1 ring-ink" aria-hidden />{h.label}</h4>
              <ul className="mt-4 space-y-4">
                {r.actions.filter((a) => a.horizon === h.h).map((a) => (
                  <li key={a.action}>
                    <p className="text-sm font-medium leading-snug">{a.action}</p>
                    <p className="mt-1 text-xs text-mute"><span className="font-medium text-ink">{t("dr.kpi")}</span> · {a.kpi}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <p className="border-t border-line pt-4 text-xs leading-relaxed text-mute">{t("dr.note")}</p>
    </div>
  );
}

export function DecisionReportTab({ test }: { test: Test }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const base = `${apiBase(test)}/report`;
  const [state, setState] = useState<State | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [starting, setStarting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [tick, setTick] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const posting = useRef(false);
  const [since, setSince] = useState(() => Date.now());

  useEffect(() => {
    let stop = false;
    const run = async () => {
      try {
        const d = await api<State>(base);
        if (stop) return;
        if (d.status === "none" && posting.current) {
          timer.current = setTimeout(run, 3000);
          return;
        }
        setState(d);
        setLoadError(null);
        if (d.status === "generating") timer.current = setTimeout(run, 3000);
        else if (d.status === "ready" && d.report) setEditing(false);
      } catch (e) {
        if (stop) return;
        setLoadError(errorText(e, t));
      }
    };
    void run();
    return () => { stop = true; clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t only changes the error text
  }, [base, tick]);

  const generate = useCallback(() => {
    // POST may hold the request for up to ~2 min; show progress right away and keep polling GET as a fallback
    setStarting(true);
    posting.current = true;
    setSince(Date.now());
    setState({ status: "generating", report: null });
    setEditing(false);
    setTick((n) => n + 1);
    api(base, { method: "POST", json: { decision_question: question.trim() || undefined, lang } })
      .catch((e) => {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
          setState({ status: "none", report: null });
          toast.error(errorText(e, t));
        }
      })
      .finally(() => {
        posting.current = false;
        setStarting(false);
        setTick((n) => n + 1);
      });
  }, [base, question, lang, toast, t]);

  if (loadError && !state) return <ErrorNote action={<Button variant="outline" size="sm" onClick={() => setTick((n) => n + 1)}>{t("common.retry")}</Button>}>{loadError}</ErrorNote>;
  if (!state) return <div aria-busy="true" className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-40" /></div>;

  if (state.status === "generating") {
    return (
      <div className="space-y-6">
        <div className="mx-auto max-w-xl rounded-card bg-surface p-6">
          <LongProgress since={since} estimateSec={75} label={t("dr.generating")} />
        </div>
        <Skeleton className="h-28" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}</div>
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (state.status === "ready" && state.report && !editing) {
    return <Ready r={state.report} test={test} onRegenerate={test.read_only ? undefined : () => { setQuestion(state.report?.decision_question ?? ""); setEditing(true); }} />;
  }
  if (test.read_only) return <p className="rounded-card bg-surface px-5 py-8 text-center text-sm text-mute">{t("share.noReport")}</p>;

  return (
    <div className="mx-auto max-w-xl py-8 text-center sm:py-14">
      <div className="mx-auto grid size-12 place-items-center rounded-full bg-ink text-lime"><Sparkles size={20} aria-hidden /></div>
      <h2 className="mt-5 text-2xl font-bold">{t("dr.emptyTitle")}</h2>
      <p className="mt-2 text-sm text-mute">{t("dr.emptyBody")}</p>
      {state.status === "failed" && <div className="mt-4 text-left"><ErrorNote>{t("dr.failed")} {state.error}</ErrorNote></div>}
      <div className="mt-6 text-left">
        <label htmlFor="dr-q" className="text-sm font-medium">{t("dr.question")}</label>
        <textarea
          id="dr-q" rows={3} value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)} placeholder={t("dr.questionPh")}
          className="mt-1.5 w-full resize-y rounded-card border border-line bg-surface p-4 text-sm placeholder:text-mute/70"
        />
      </div>
      <Button size="lg" className="mt-4" onClick={generate} disabled={starting}><Sparkles size={16} aria-hidden /> {t("dr.generate")}</Button>
    </div>
  );
}
