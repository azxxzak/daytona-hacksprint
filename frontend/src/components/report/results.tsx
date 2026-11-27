"use client";

import { useId, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AGE_GROUPS, fmtTime, inSegment, mean } from "@/lib/format";
import type { Test } from "@/lib/types";
import type { Key } from "@/lib/i18n";
import { useI18n } from "../i18n-provider";
import { Avatar, Card, SectionHeader, cx } from "../ui";

const W = 800, H = 300, PL = 36, PR = 16, PT = 16, PB = 30;

function InterestChart({ test }: { test: Test }) {
  const { t } = useI18n();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const curve = test.summary?.curve ?? [];
  const maxT = Math.max(test.duration || 0, ...curve.map((c) => c.t), 1);

  const groups = useMemo(() => {
    const persona = new Map(test.personas.map((p) => [p.id, p]));
    return AGE_GROUPS.map((gp) => {
      const byT = new Map<number, number[]>();
      for (const g of test.gaze) {
        const p = persona.get(g.id);
        if (!p || !inSegment(p, gp.key)) continue;
        const k = Math.round(g.t * 1000) / 1000;
        (byT.get(k) ?? byT.set(k, []).get(k)!).push(g.interest);
      }
      const pts = [...byT].sort((a, b) => a[0] - b[0]).map(([tt, v]) => ({ t: tt, avg: mean(v)! }));
      return { ...gp, pts };
    }).filter((g) => g.pts.length > 0);
  }, [test.gaze, test.personas]);

  const x = (v: number) => PL + (v / maxT) * (W - PL - PR);
  const y = (v: number) => PT + (1 - (v - 1) / 4) * (H - PT - PB);
  const path = (pts: { t: number; avg: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.avg).toFixed(1)}`).join(" ");
  const step = maxT > 120 ? 30 : maxT > 40 ? 10 : maxT > 12 ? 5 : 1;
  const ticks = Array.from({ length: Math.floor(maxT / step) + 1 }, (_, i) => i * step);

  if (curve.length < 2) return <p className="py-10 text-center text-sm text-mute">{t("res.curveEmpty")}</p>;

  const toggle = (k: string) => setHidden((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const hoverT = hover != null ? curve[hover].t : null;
  const valuesAt = (tt: number) =>
    groups.filter((g) => !hidden.has(g.key)).map((g) => {
      const near = g.pts.reduce((a, b) => (Math.abs(b.t - tt) < Math.abs(a.t - tt) ? b : a));
      return { g, v: near.avg };
    });

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2 text-[13px]">
        <span className="inline-flex h-8 items-center gap-2 rounded-full bg-ink px-3 text-white"><span className="h-0.5 w-4 bg-white" aria-hidden />{t("res.panel")}</span>
        {groups.map((g) => (
          <button
            key={g.key} type="button" aria-pressed={!hidden.has(g.key)} onClick={() => toggle(g.key)}
            className={cx("inline-flex h-8 items-center gap-2 rounded-full border px-3 transition-opacity", hidden.has(g.key) ? "border-line text-mute opacity-60" : "border-line bg-surface")}
          >
            <span className="h-0.5 w-4 rounded" style={{ background: g.color }} aria-hidden />{t(g.label)}
          </button>
        ))}
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("res.curveAria")} className="h-auto w-full touch-pan-y select-none"
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - r.left) / r.width) * W;
            let best = 0, bd = Infinity;
            curve.forEach((c, i) => { const d = Math.abs(x(c.t) - px); if (d < bd) { bd = d; best = i; } });
            setHover(best);
          }}
          onPointerLeave={() => setHover(null)}
        >
          {[1, 2, 3, 4, 5].map((v) => (
            <g key={v}>
              <line x1={PL} x2={W - PR} y1={y(v)} y2={y(v)} stroke="#e3e3e6" strokeWidth={1} />
              <text x={PL - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="#6b6b70" className="tnum">{v}</text>
            </g>
          ))}
          {ticks.map((tt) => <text key={tt} x={x(tt)} y={H - 8} textAnchor="middle" fontSize={11} fill="#6b6b70" className="tnum">{fmtTime(tt)}</text>)}
          {groups.filter((g) => !hidden.has(g.key)).map((g) => (
            <path key={g.key} d={path(g.pts)} fill="none" stroke={g.color} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" opacity={0.9} />
          ))}
          <path d={path(curve)} fill="none" stroke="#111" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
          {curve.map((c) => <circle key={c.t} cx={x(c.t)} cy={y(c.avg)} r={3.5} fill="#fff" stroke="#111" strokeWidth={2} />)}
          {hover != null && hoverT != null && (
            <g>
              <line x1={x(hoverT)} x2={x(hoverT)} y1={PT} y2={H - PB} stroke="#111" strokeDasharray="3 3" strokeWidth={1} />
              <circle cx={x(hoverT)} cy={y(curve[hover].avg)} r={6} fill="#111" />
            </g>
          )}
        </svg>
        {hover != null && hoverT != null && (
          <div
            className="pointer-events-none absolute top-0 z-10 min-w-36 -translate-x-1/2 rounded-xl bg-ink px-3 py-2 text-xs text-white"
            style={{ left: `${Math.min(88, Math.max(12, (x(hoverT) / W) * 100))}%` }}
          >
            <p className="tnum font-medium">{fmtTime(hoverT)}  ·  {curve[hover].avg.toFixed(1)}</p>
            {valuesAt(hoverT).map(({ g, v }) => (
              <p key={g.key} className="tnum flex items-center gap-1.5 text-white/80">
                <span className="size-2 rounded-full" style={{ background: g.color }} aria-hidden />{t(g.label)} {v.toFixed(1)}
              </p>
            ))}
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>{t("res.curveLabel")}</caption>
        <tbody>{curve.map((c) => <tr key={c.t}><th scope="row">{fmtTime(c.t)}</th><td>{c.avg.toFixed(1)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function FocusBars({ test }: { test: Test }) {
  const { t } = useI18n();
  const top = useMemo(() => {
    const m = new Map<string, { label: string; n: number }>();
    for (const g of test.gaze) {
      const raw = (g.looking_at || "").trim();
      if (!raw) continue;
      const k = raw.toLowerCase();
      const e = m.get(k);
      if (e) e.n++; else m.set(k, { label: raw, n: 1 });
    }
    return [...m.values()].sort((a, b) => b.n - a.n).slice(0, 10);
  }, [test.gaze]);
  const max = top[0]?.n ?? 1;
  if (!top.length) return <p className="text-sm text-mute">{t("res.noData")}</p>;
  return (
    <ol className="space-y-3">
      {top.map((e, i) => (
        <li key={e.label} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 text-sm">
          <span className="tnum text-xs text-mute">{i + 1}</span>
          <span className="truncate" title={e.label}>{e.label}</span>
          <span className="tnum text-xs text-mute">{t("res.glances", { n: e.n })}</span>
          <span />
          <div className="col-span-2 h-1.5 rounded-full bg-canvas" aria-hidden>
            <div className="h-full rounded-full bg-ink" style={{ width: `${(e.n / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function AgeGenderTable({ test }: { test: Test }) {
  const { t } = useI18n();
  const rows = useMemo(() => {
    const persona = new Map(test.personas.map((p) => [p.id, p]));
    const cell = (ageKey: (typeof AGE_GROUPS)[number]["key"] | "all", gender: "F" | "M" | "all") => {
      const vals: number[] = [];
      const ids = new Set<string>();
      for (const g of test.gaze) {
        const p = persona.get(g.id);
        if (!p || !inSegment(p, ageKey) || (gender !== "all" && !inSegment(p, gender))) continue;
        vals.push(g.interest); ids.add(p.id);
      }
      return { avg: mean(vals), n: ids.size };
    };
    return [...AGE_GROUPS.map((a) => ({ key: a.key, label: a.label })), { key: "all" as const, label: null }].map((a) => ({
      label: a.label, F: cell(a.key, "F"), M: cell(a.key, "M"), all: cell(a.key, "all"),
    }));
  }, [test.gaze, test.personas]);

  const Cell = ({ c, strong }: { c: { avg: number | null; n: number }; strong?: boolean }) => (
    <td className={cx("tnum px-3 py-3 text-right", strong && "font-bold")}>
      {c.avg == null ? <span className="text-mute">–</span> : <>{c.avg.toFixed(1)} <span className="text-xs font-normal text-mute">({c.n})</span></>}
    </td>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-mute">
            <th scope="col" className="px-3 py-2 font-medium">{t("res.age")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("gender.Female")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("gender.Male")}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t("res.all")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i} className={r.label ? "" : "border-t-2 border-ink font-medium"}>
              <th scope="row" className="px-3 py-3 text-left font-medium">{r.label ? t(r.label) : t("res.all")}</th>
              <Cell c={r.F} /><Cell c={r.M} /><Cell c={r.all} strong />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Transcript({ test, onSeek }: { test: Test; onSeek: (t: number) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <Card className="p-6">
      <button
        type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-4 text-left"
      >
        <span>
          <span className="block text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("res.transcriptLabel")}</span>
          <span className="block text-lg font-bold">{t("res.transcriptTitle")}</span>
        </span>
        <span className="inline-flex items-center gap-1.5 text-sm text-mute">
          {open ? t("res.transcriptHide") : t("res.transcriptShow")}
          <ChevronDown size={16} aria-hidden className={cx("transition-transform", open && "rotate-180")} />
        </span>
      </button>
      <div id={id} hidden={!open} className="mt-4 border-t border-line pt-4">
        {test.transcript.length === 0 ? (
          <p className="text-sm text-mute">{t("res.transcriptEmpty")}</p>
        ) : (
          <ul className="max-h-[420px] space-y-1 overflow-y-auto">
            {test.transcript.map((s, i) => (
              <li key={i} className="flex gap-3 text-sm">
                {test.media_kind === "video" ? (
                  <button type="button" onClick={() => onSeek(s.start)} aria-label={t("res.seekTo", { t: fmtTime(s.start) })} className="tnum w-12 shrink-0 rounded-md py-1 text-left text-xs text-mute underline-offset-4 hover:text-ink hover:underline">
                    {fmtTime(s.start)}
                  </button>
                ) : null}
                <span className="py-1">{s.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function Themes({ test, onSeek }: { test: Test; onSeek: (t: number) => void }) {
  const { t } = useI18n();
  const themes = test.themes;
  const byId = useMemo(() => new Map(test.personas.map((p) => [p.id, p])), [test.personas]);
  if (!themes || themes.length === 0) return null;
  const video = test.media_kind === "video";
  return (
    <section aria-label={t("th.title")}>
      <SectionHeader label={t("th.label")} title={t("th.title")} />
      <ul className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {themes.map((th) => (
          <li key={th.id} className="rounded-card bg-surface shadow-card p-6">
            <div className="flex items-start justify-between gap-4">
              <h3 className="text-lg font-bold leading-snug">{th.title}</h3>
              <span className="tnum shrink-0 text-sm font-medium">{Math.round(th.share * 100)}%</span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-canvas" role="img" aria-label={t("th.share", { n: Math.round(th.share * 100) })}>
              <div className="h-full rounded-full bg-ink" style={{ width: Math.round(Math.min(1, th.share) * 100) + "%" }} />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink/80">{th.description}</p>
            {th.by_segment.length > 0 && (
              <div className="mt-4">
                <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("th.seg")}</p>
                <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
                  {th.by_segment.map((g) => (
                    <li key={g.segment} className="text-xs">
                      <span className="flex justify-between text-mute"><span>{t(("seg." + g.segment) as Key)}</span><span className="tnum">{Math.round(g.share * 100)}%</span></span>
                      <span className="mt-0.5 block h-1 rounded-full bg-canvas"><span className="block h-full rounded-full bg-ink/60" style={{ width: Math.round(Math.min(1, g.share) * 100) + "%" }} /></span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {th.examples.length > 0 && (
              <ul className="mt-4 space-y-2">
                {th.examples.slice(0, 3).map((e, i) => {
                  const p = byId.get(e.persona_id);
                  const inner = (
                    <>
                      {p && <Avatar src={p.avatar_url} name={p.name} color={p.color} rounded="rounded-full" className="size-7 shrink-0" />}
                      <span className="min-w-0 flex-1 text-[13px] leading-snug">{e.text}</span>
                      {video && <span className="tnum shrink-0 text-[11px] text-mute">{fmtTime(e.t)}</span>}
                    </>
                  );
                  return (
                    <li key={i}>
                      {video ? (
                        <button type="button" onClick={() => onSeek(e.t)} aria-label={t("th.jump", { t: fmtTime(e.t) })} className="flex w-full items-start gap-2.5 rounded-xl bg-canvas p-2.5 text-left hover:bg-line/60">{inner}</button>
                      ) : (
                        <div className="flex items-start gap-2.5 rounded-xl bg-canvas p-2.5">{inner}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Results({ test, onSeek }: { test: Test; onSeek: (t: number) => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <Themes test={test} onSeek={onSeek} />
      <Card className="p-6 sm:p-8">
        <SectionHeader label={t("res.curveLabel")} title={t("res.curveTitle")} />
        <div className="mt-6"><InterestChart test={test} /></div>
      </Card>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-6 sm:p-8">
          <SectionHeader label={t("res.focusLabel")} title={t("res.focusTitle")} as="h3" />
          <div className="mt-6"><FocusBars test={test} /></div>
        </Card>
        <Card className="p-6 sm:p-8">
          <SectionHeader label={t("res.tableLabel")} title={t("res.tableTitle")} as="h3" />
          <div className="mt-4"><AgeGenderTable test={test} /></div>
        </Card>
      </div>
      <Transcript test={test} onSeek={onSeek} />
    </div>
  );
}
