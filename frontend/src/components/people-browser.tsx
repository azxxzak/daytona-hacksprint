"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Persona } from "@/lib/types";
import { FacetField, type FacetItem } from "./facet-field";
import { useI18n } from "./i18n-provider";
import { PersonaCard } from "./persona-card";
import { Button, ErrorNote, cx } from "./ui";

type Facets = { total: number; regions: FacetItem[]; occupations: FacetItem[] };
type Page = { personas: Persona[]; total: number };

const PAGE = 36;
const AGES: [number, number][] = [[15, 19], [20, 29], [30, 39], [40, 49], [50, 59], [60, 69], [70, 79]];

/**
 * Browse the whole persona bank to hand-pick a panel: free-text search (Japanese or English: names, jobs,
 * prefectures, one-line descriptions) + age / gender / prefecture / occupation filters, paged with "Show more".
 */
export function PeopleBrowser({ facets, picked, onToggle, onDetails }: {
  facets: Facets | null;
  picked: Set<string>;
  onToggle: (p: Persona) => void;
  onDetails: (p: Persona) => void;
}) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [ages, setAges] = useState<number[]>([]);           // indexes into AGES
  const [genders, setGenders] = useState({ F: true, M: true });
  const [regions, setRegions] = useState<string[]>([]);
  const [occupations, setOccupations] = useState<string[]>([]);
  const [items, setItems] = useState<Persona[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const reqId = useRef(0);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(id);
  }, [q]);

  const sel = ages.map((i) => AGES[i]);
  const ageMin = sel.length ? Math.min(...sel.map((a) => a[0])) : 15;
  const ageMax = sel.length ? Math.max(...sel.map((a) => a[1])) : 79;
  const g = (["F", "M"] as const).filter((k) => genders[k]).join(",") || "F,M";
  const key = [debounced, ageMin, ageMax, g, regions.join("|"), occupations.join("|"), lang].join("~");

  const load = (offset: number) => {
    const my = ++reqId.current;
    setLoading(true);
    const p = new URLSearchParams({ q: debounced, age_min: String(ageMin), age_max: String(ageMax), genders: g, offset: String(offset), limit: String(PAGE) });
    if (regions.length) p.set("regions", regions.join(","));
    if (occupations.length) p.set("occupations", occupations.join(","));
    api<Page>(`/api/audience/search?${p}`)
      .then((d) => {
        if (my !== reqId.current) return;
        // browsing shows existing portraits only; a new one is drawn when someone is picked or opened
        const rows = d.personas.map((x) => ({ ...x, avatar_url: x.avatar_url.includes("/api/avatars/p/") ? `${x.avatar_url}?draw=0` : x.avatar_url }));
        setItems((prev) => (offset ? [...prev, ...rows] : rows));
        setTotal(d.total);
        setError(null);
      })
      .catch((e) => { if (my === reqId.current) setError(e); })
      .finally(() => { if (my === reqId.current) setLoading(false); });
  };

  useEffect(() => {
    const id = setTimeout(() => load(0), 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures every filter
  }, [key]);

  const filtersOn = !!(debounced || ages.length || !genders.F || !genders.M || regions.length || occupations.length);
  const reset = () => { setQ(""); setAges([]); setGenders({ F: true, M: true }); setRegions([]); setOccupations([]); };

  return (
    <div>
      <div className="sticky top-0 z-10 -mx-6 bg-surface px-6 pb-4 pt-1 sm:-mx-8 sm:px-8">
        <div className="relative">
          <Search size={16} aria-hidden className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-mute" />
          <label htmlFor="people-q" className="sr-only">{t("pick.search")}</label>
          <input
            id="people-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("pick.searchPh")}
            className="h-12 w-full rounded-full border border-line bg-canvas pl-11 pr-4 text-[15px] placeholder:text-mute/80"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {AGES.map(([lo], i) => {
            const on = ages.includes(i);
            return (
              <button
                key={lo} type="button" aria-pressed={on}
                onClick={() => setAges((a) => (on ? a.filter((x) => x !== i) : [...a, i]))}
                className={cx("h-8 rounded-full border px-3 text-xs font-medium transition-colors", on ? "border-ink bg-ink text-white" : "border-line hover:border-ink")}
              >
                {lo === 15 ? t("pick.teens") : t("age.decade", { n: lo })}
              </button>
            );
          })}
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          {(["F", "M"] as const).map((k) => (
            <button
              key={k} type="button" aria-pressed={genders[k]}
              onClick={() => setGenders((x) => ({ ...x, [k]: !x[k] }))}
              className={cx("h-8 rounded-full border px-3 text-xs font-medium transition-colors", genders[k] ? "border-ink bg-ink text-white" : "border-line text-mute hover:border-ink")}
            >
              {k === "F" ? t("new.female") : t("new.male")}
            </button>
          ))}
        </div>
        {facets && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FacetField label={t("new.regions")} items={facets.regions} value={regions} onChange={setRegions} />
            <FacetField label={t("new.occupations")} items={facets.occupations} value={occupations} onChange={setOccupations} />
          </div>
        )}
        <div className="mt-3 flex items-center justify-between text-sm">
          <p className="tnum text-mute" aria-live="polite">
            {total == null ? t("common.loading") : t("pick.matches", { n: total.toLocaleString() })}
          </p>
          {filtersOn && (
            <button type="button" onClick={reset} className="inline-flex items-center gap-1 text-xs text-mute hover:text-ink">
              <X size={12} aria-hidden /> {t("pick.reset")}
            </button>
          )}
        </div>
      </div>

      {error != null && <ErrorNote>{t("pick.error")} {errorText(error, t)}</ErrorNote>}
      {total === 0 && !loading && <p className="py-12 text-center text-sm text-mute">{t("pick.none")}</p>}

      <ul className={cx("mt-2 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4", loading && !items.length && "opacity-50")}>
        {items.map((p, i) => (
          <li key={p.id}>
            <PersonaCard
              persona={p} eager={i < 8} meta={p.profile?.meta} title={p.profile?.headline || p.name}
              selecting selected={picked.has(p.id)} onToggle={() => onToggle(p)} onDetails={() => onDetails(p)}
            />
          </li>
        ))}
        {loading && !items.length && Array.from({ length: 8 }, (_, i) => (
          <li key={`s${i}`}><div className="pulse aspect-[4/5] rounded-card bg-canvas" /><div className="mt-2 h-3 w-2/3 rounded bg-canvas" /></li>
        ))}
      </ul>

      {total != null && items.length < total && (
        <div className="mt-8 flex justify-center">
          <Button variant="outline" onClick={() => load(items.length)} disabled={loading}>
            {loading ? <Loader2 size={15} className="motion-safe:animate-spin" aria-hidden /> : null}
            {t("pick.more", { shown: items.length.toLocaleString(), total: total.toLocaleString() })}
          </Button>
        </div>
      )}
    </div>
  );
}
