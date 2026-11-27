"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, ArrowLeftRight, Loader2, RefreshCw, Sparkles, TriangleAlert, Users } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { fmtTime, thoughtOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { TestSummary } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { LongProgress } from "./long-progress";
import { useToast } from "./toast";
import { Select } from "./menu";
import { Avatar, Button, Card, ErrorNote, SectionHeader, Skeleton, cx, useDocTitle } from "./ui";

type Side = TestSummary & {
  total: number; low_t: number | null; top_focus: string | null; duration: number;
  curve: { x: number; t: number; avg: number }[]; themes: { title: string; share: number }[];
};
type Quote = { t: number; interest: number; thought: string; thought_en: string } | null;
type Cmp = {
  a: Side; b: Side; same_panel: boolean; linked: boolean; lang_a: "ja" | "en"; lang_b: "ja" | "en";
  test: { kind: "paired" | "independent"; diff: number; ci: [number, number] | null; n?: number; prefer_a?: number; prefer_b?: number; same?: number; p?: number };
  leader: "A" | "B" | null; outcome: "clear" | "lean" | "tie";
  segments: { key: string; a: number | null; b: number | null; n_a: number; n_b: number }[];
  movers: { name: string; age: number; gender: string; a: number; b: number; avatar_url?: string; quote_a: Quote; quote_b: Quote }[];
  verdict: Verdict | null;
};
type Verdict = { winner: "A" | "B" | "tie"; headline: string; reasons: { point: string; evidence: string }[]; fix: { version: "A" | "B"; action: string }[]; caveat: string };

const ID = /^[a-f0-9]{12}$/;
const COLOR = { A: "#9a9aa0", B: "#111111" } as const;

function Picker({ label, value, other, tests, onChange }: { label: "A" | "B"; value: string; other: string; tests: TestSummary[]; onChange: (id: string) => void }) {
  const { t, lang } = useI18n();
  const pickHint = (x: TestSummary) =>
    `${new Date(x.created_at).toLocaleDateString(lang === "ja" ? "ja-JP" : "en-US", { month: "short", day: "numeric" })} · ${t("dash.viewers", { n: x.viewers })}`;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3 rounded-card bg-surface shadow-card p-3">
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold text-white" style={{ background: COLOR[label] }}>{label}</span>
      <Select
        variant="field"
        label={t("cmp.version", { v: label })}
        value={value}
        onChange={onChange}
        placeholder={t("cmp.pick")}
        options={tests.map((x) => ({ value: x.id, label: x.name, hint: pickHint(x), disabled: x.id === other }))}
      />
    </div>
  );
}

function Curve({ a, b }: { a: Side; b: Side }) {
  const { t } = useI18n();
  const W = 640, H = 200, P = 28;
  const path = (c: Side["curve"]) => c.map((p, i) => `${i ? "L" : "M"}${(P + p.x * (W - 2 * P)).toFixed(1)},${(H - P - ((p.avg - 1) / 4) * (H - 2 * P)).toFixed(1)}`).join("");
  const y = (v: number) => H - P - ((v - 1) / 4) * (H - 2 * P);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("cmp.curveAria")}>
        {[1, 2, 3, 4, 5].map((v) => (
          <g key={v}>
            <line x1={P} x2={W - P} y1={y(v)} y2={y(v)} stroke="#e3e3e6" />
            <text x={P - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#6b6b70">{v}</text>
          </g>
        ))}
        <text x={P} y={H - 6} fontSize="11" fill="#6b6b70">0%</text>
        <text x={W - P} y={H - 6} fontSize="11" fill="#6b6b70" textAnchor="end">100%</text>
        {(["A", "B"] as const).map((k) => {
          const c = (k === "A" ? a : b).curve;
          if (c.length < 2) return null;
          const last = c[c.length - 1];
          return (
            <g key={k}>
              <path d={path(c)} fill="none" stroke={COLOR[k]} strokeWidth={k === "B" ? 3 : 2.5} strokeLinejoin="round" strokeLinecap="round" />
              <text x={Math.min(W - 4, P + last.x * (W - 2 * P) + 6)} y={y(last.avg) + 4} fontSize="12" fontWeight="700" fill={COLOR[k]}>{k}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 text-xs text-mute">{t("cmp.curveNote")}</figcaption>
    </figure>
  );
}

function Metric({ label, a, b, better }: { label: string; a: string; b: string; better: "A" | "B" | null }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-baseline gap-4 border-b border-line py-3 last:border-0">
      <dt className="text-sm text-mute">{label}</dt>
      {(["A", "B"] as const).map((k) => (
        <dd key={k} className={cx("tnum w-24 text-right text-lg", better === k ? "font-bold" : "text-ink/70")}>
          {k === "A" ? a : b}{better === k && <span aria-hidden className="ml-1 inline-block size-2 rounded-full bg-lime align-middle ring-1 ring-ink" />}
        </dd>
      ))}
    </div>
  );
}

function VerdictCard({ a, b, initial }: { a: string; b: string; initial: Verdict | null }) {
  const { t } = useI18n();
  const toast = useToast();
  const [v, setV] = useState<Verdict | null>(initial);
  const [busy, setBusy] = useState(false);
  const [since, setSince] = useState(0);
  const run = (regenerate = false) => {
    setBusy(true);
    setSince(Date.now());
    api<Verdict>(`/api/compare/verdict?a=${a}&b=${b}${regenerate ? "&regenerate=true" : ""}`, { method: "POST" })
      .then(setV)
      .catch((e) => toast.error(errorText(e, t)))
      .finally(() => setBusy(false));
  };
  if (busy) return <Card className="p-6"><LongProgress since={since} estimateSec={30} label={t("cmp.writing")} /></Card>;
  if (!v) {
    return (
      <Card className="flex flex-wrap items-center justify-between gap-4 p-6">
        <div className="min-w-0 max-w-xl">
          <p className="font-bold">{t("cmp.verdictTitle")}</p>
          <p className="mt-1 text-sm text-mute">{t("cmp.verdictBody")}</p>
        </div>
        <Button onClick={() => run()}><Sparkles size={15} aria-hidden /> {t("cmp.verdictRun")}</Button>
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden p-0">
      <div className="bg-ink p-6 text-white sm:p-8">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/60">{t("cmp.verdictTitle")}</p>
        <p className="mt-2 text-sm font-semibold text-lime">{v.winner === "tie" ? t("cmp.noWinner") : t("cmp.runVersion", { v: v.winner })}</p>
        <p className="mt-2 text-balance text-xl font-bold leading-snug sm:text-2xl">{v.headline}</p>
      </div>
      <div className="grid gap-8 p-6 sm:p-8 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-bold">{t("cmp.why")}</h3>
          <ul className="mt-3 space-y-3">
            {v.reasons.map((r, i) => (
              <li key={i} className="text-sm leading-relaxed"><p className="font-semibold">{r.point}</p><p className="mt-0.5 text-ink/70">{r.evidence}</p></li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-bold">{t("cmp.fix")}</h3>
          <ul className="mt-3 space-y-3">
            {v.fix.map((f, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed">
                <span aria-hidden className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold text-white" style={{ background: COLOR[f.version] ?? COLOR.B }}>{f.version}</span>
                <span>{f.action}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-4 sm:px-8">
        <p className="max-w-3xl text-xs leading-relaxed text-mute">{v.caveat}</p>
        <Button variant="ghost" size="sm" onClick={() => run(true)}><RefreshCw size={14} aria-hidden /> {t("cmp.rewrite")}</Button>
      </div>
    </Card>
  );
}

export function Compare() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  useDocTitle(t("cmp.title"));
  const a = ID.test(params.get("a") ?? "") ? params.get("a")! : "";
  const b = ID.test(params.get("b") ?? "") ? params.get("b")! : "";
  const list = useApi<{ tests: TestSummary[] }>("/api/tests");
  const done = useMemo(() => (list.data?.tests ?? []).filter((x) => x.status === "done"), [list.data]);
  const cmp = useApi<Cmp>(a && b && a !== b ? `/api/compare?a=${a}&b=${b}` : null);
  const set = (k: "a" | "b", id: string) => {
    const q = new URLSearchParams(params.toString());
    if (id) q.set(k, id); else q.delete(k);
    router.replace(`/compare?${q.toString()}`, { scroll: false });
  };
  const swap = () => router.replace(`/compare?a=${b}&b=${a}`, { scroll: false });
  const c = cmp.data;
  const segLabel: Record<string, string> = { a1: t("cmp.seg.a1"), a2: t("cmp.seg.a2"), a3: t("cmp.seg.a3"), a4: t("cmp.seg.a4"), F: t("new.female"), M: t("new.male") };
  const fmtDiff = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(2)}`;

  return (
    <div className="mx-auto max-w-[1180px] space-y-10">
      <div>
        <Link href={a ? `/tests/${a}` : "/"} className="mb-4 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
          <ArrowLeft size={15} aria-hidden /> {t("common.back")}
        </Link>
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] sm:text-[40px]">{t("cmp.title")}</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-mute">{t("cmp.sub")}</p>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:items-center">
          <Picker label="A" value={a} other={b} tests={done} onChange={(id) => set("a", id)} />
          <button type="button" onClick={swap} disabled={!a || !b} aria-label={t("cmp.swap")} className="grid size-10 shrink-0 place-items-center self-center rounded-full bg-ink text-lime shadow-card transition-transform hover:rotate-180 disabled:bg-surface disabled:text-mute disabled:opacity-60 disabled:hover:rotate-0">
            <ArrowLeftRight size={16} aria-hidden />
          </button>
          <Picker label="B" value={b} other={a} tests={done} onChange={(id) => set("b", id)} />
        </div>
        {a && !b && done.length < 2 && list.data && (
          <p className="mt-3 text-sm text-mute">{t("cmp.needTwo")} <Link className="font-medium text-ink underline underline-offset-4" href={`/tests/new?panel_from=${a}`}>{t("ab.variant")}</Link></p>
        )}
      </div>

      {cmp.error && <ErrorNote>{errorText(cmp.error, t)}</ErrorNote>}
      {cmp.loading && !c && <div className="space-y-4"><Skeleton className="h-36" /><Skeleton className="h-64" /></div>}

      {c && (
        <>
          <div className={cx("flex items-start gap-3 rounded-card p-4 text-sm leading-relaxed", c.same_panel ? "bg-surface" : "bg-danger/5 text-danger")}>
            {c.same_panel ? <Users size={18} className="mt-0.5 shrink-0" aria-hidden /> : <TriangleAlert size={18} className="mt-0.5 shrink-0" aria-hidden />}
            <p>{c.same_panel ? t("cmp.same", { n: c.test.n ?? c.a.total }) : t("cmp.different")}</p>
          </div>

          <Card className="p-6 sm:p-8">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("cmp.result")}</p>
            <p className="mt-2 text-balance text-2xl font-bold leading-snug sm:text-3xl">
              {c.outcome === "tie" ? t("cmp.tie") : c.outcome === "clear" ? t("cmp.clear", { v: c.leader ?? "" }) : t("cmp.lean", { v: c.leader ?? "" })}
            </p>
            <p className="tnum mt-3 text-sm text-ink/75">
              {c.test.ci ? t("cmp.diff", { d: fmtDiff(c.test.diff), lo: fmtDiff(c.test.ci[0]), hi: fmtDiff(c.test.ci[1]) }) : t("cmp.tooFew")}
              {c.test.kind === "paired" && <> {t("cmp.paired", { b: c.test.prefer_b ?? 0, a: c.test.prefer_a ?? 0, s: c.test.same ?? 0, p: (c.test.p ?? 1).toFixed(2) })}</>}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-mute">{t("cmp.method")}</p>
          </Card>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <Card className="p-6">
              <div className="grid grid-cols-[1fr_auto_auto] gap-4 border-b-2 border-ink pb-2 text-sm font-bold">
                <span />
                {(["A", "B"] as const).map((k) => (
                  <Link key={k} href={`/tests/${(k === "A" ? c.a : c.b).id}`} className="w-24 truncate text-right underline-offset-4 hover:underline" title={(k === "A" ? c.a : c.b).name}>
                    <span style={{ color: COLOR[k] }}>{k}</span> · {(k === "A" ? c.a : c.b).name}
                  </Link>
                ))}
              </div>
              <dl>
                <Metric label={t("rep.avgInterest")} a={(c.a.avg_interest ?? 0).toFixed(2)} b={(c.b.avg_interest ?? 0).toFixed(2)} better={c.outcome === "tie" ? null : c.leader} />
                <Metric label={t("rep.engagedLabel")} a={`${c.a.engaged}/${c.a.total}`} b={`${c.b.engaged}/${c.b.total}`}
                  better={(c.a.engaged ?? 0) / (c.a.total || 1) === (c.b.engaged ?? 0) / (c.b.total || 1) ? null : (c.a.engaged ?? 0) / (c.a.total || 1) > (c.b.engaged ?? 0) / (c.b.total || 1) ? "A" : "B"} />
                <Metric label={t("cmp.length")} a={c.a.media_kind === "video" ? fmtTime(c.a.duration) : t("cmp.image")} b={c.b.media_kind === "video" ? fmtTime(c.b.duration) : t("cmp.image")} better={null} />
                <Metric label={t("rep.lowLabel")} a={c.a.low_t != null && c.a.media_kind === "video" ? fmtTime(c.a.low_t) : "–"} b={c.b.low_t != null && c.b.media_kind === "video" ? fmtTime(c.b.low_t) : "–"} better={null} />
              </dl>
              <p className="mt-4 text-xs text-mute">{t("rep.topFocus")}: <span className="text-ink">A · {c.a.top_focus || "–"}</span> / <span className="text-ink">B · {c.b.top_focus || "–"}</span></p>
            </Card>
            <Card className="p-6">
              <p className="text-sm font-bold">{t("cmp.curve")}</p>
              {c.a.curve.length > 1 && c.b.curve.length > 1 ? <div className="mt-3"><Curve a={c.a} b={c.b} /></div> : <p className="mt-3 text-sm text-mute">{t("cmp.noCurve")}</p>}
            </Card>
          </div>

          <VerdictCard key={`${a}:${b}:${lang}`} a={a} b={b} initial={c.verdict} />

          <section>
            <SectionHeader as="h2" label={t("cmp.l.seg")} title={t("cmp.t.seg")} />
            <div className="mt-5 overflow-hidden rounded-card bg-surface shadow-card">
              <ul className="divide-y divide-line">
                {c.segments.map((s) => {
                  const d = s.a != null && s.b != null ? s.b - s.a : null;
                  return (
                    <li key={s.key} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-4 px-5 py-3 text-sm sm:grid-cols-[9rem_1fr_5rem]">
                      <span className="font-medium">{segLabel[s.key]} <span className="tnum text-xs text-mute">({s.n_a}/{s.n_b})</span></span>
                      <span className="flex flex-col gap-1">
                        {(["a", "b"] as const).map((k) => (
                          <span key={k} className="flex items-center gap-2">
                            <span className="h-2 rounded-full" style={{ width: `${(((s[k] ?? 1) - 1) / 4) * 100}%`, minWidth: 4, background: COLOR[k === "a" ? "A" : "B"] }} />
                            <span className="tnum text-xs text-mute">{s[k]?.toFixed(1) ?? "–"}</span>
                          </span>
                        ))}
                      </span>
                      <span
                        className={cx("tnum text-right font-semibold", d == null || Math.abs(d) < 0.2 || Math.min(s.n_a, s.n_b) < 5 ? "font-normal text-mute" : "")}
                        title={Math.min(s.n_a, s.n_b) < 5 ? t("cmp.fewPeople") : undefined}
                      >{d == null ? "–" : fmtDiff(d)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </section>

          {c.movers.length > 0 && (
            <section>
              <SectionHeader as="h2" label={t("cmp.l.movers")} title={t("cmp.t.movers")} />
              <ul className="mt-5 grid gap-3 md:grid-cols-2">
                {c.movers.map((m, i) => (
                  <li key={i} className="rounded-card bg-surface shadow-card p-5">
                    <div className="flex items-center gap-3">
                      {m.avatar_url && <Avatar src={m.avatar_url} name={m.name} rounded="rounded-full" className="size-10 shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-bold">{m.name}</p>
                        <p className="text-xs text-mute">{m.age} · {m.gender === "F" ? t("new.female") : t("new.male")}</p>
                      </div>
                      <p className="tnum text-sm"><span style={{ color: COLOR.A }}>{m.a.toFixed(1)}</span> → <span className="font-bold">{m.b.toFixed(1)}</span></p>
                    </div>
                    <div className="mt-3 space-y-2 text-sm leading-relaxed">
                      {(["a", "b"] as const).map((k) => {
                        const q = k === "a" ? m.quote_a : m.quote_b;
                        return q ? (
                          <p key={k} className="flex gap-2">
                            <span aria-hidden className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-[10px] font-bold text-white" style={{ background: COLOR[k === "a" ? "A" : "B"] }}>{k.toUpperCase()}</span>
                            <span>“{thoughtOf(q, (k === "a" ? c.lang_a : c.lang_b) ?? lang)}” <span className="tnum text-xs text-mute">{q.interest}/5</span></span>
                          </p>
                        ) : null;
                      })}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <SectionHeader as="h2" label={t("cmp.l.themes")} title={t("cmp.t.themes")} />
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {(["A", "B"] as const).map((k) => {
                const side = k === "A" ? c.a : c.b;
                return (
                  <div key={k} className="rounded-card bg-surface shadow-card p-5">
                    <p className="text-sm font-bold"><span style={{ color: COLOR[k] }}>{k}</span> · {side.name}</p>
                    <ul className="mt-3 space-y-2">
                      {side.themes.map((th) => (
                        <li key={th.title} className="flex items-baseline justify-between gap-3 text-sm">
                          <span className="min-w-0">{th.title}</span>
                          <span className="tnum shrink-0 text-mute">{Math.round(th.share * 100)}%</span>
                        </li>
                      ))}
                      {side.themes.length === 0 && <li className="text-sm text-mute">–</li>}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}

      {!a || !b ? (
        list.loading && !list.data ? <Loader2 className="motion-safe:animate-spin" aria-hidden /> : (
          <div className="dots-ink grid place-items-center rounded-[24px] border border-dashed border-[#d6d6db] px-5 py-14 text-center">
            <div aria-hidden className="relative h-20 w-36">
              <span className="absolute left-0 top-2 grid h-16 w-24 -rotate-6 place-items-center rounded-xl bg-surface text-lg font-bold text-[#9a9aa0] shadow-card">A</span>
              <span className="absolute right-0 top-0 grid h-16 w-24 rotate-6 place-items-center rounded-xl bg-ink text-lg font-bold text-lime shadow-lift">B</span>
            </div>
            <p className="mt-6 max-w-sm text-sm text-mute">{t("cmp.empty")}</p>
          </div>
        )
      ) : null}
    </div>
  );
}
