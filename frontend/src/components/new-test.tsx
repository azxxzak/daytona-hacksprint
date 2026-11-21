"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ArrowLeft, Check, FileUp, Film, Image as ImageIcon, Loader2, Play, Plus, RefreshCw, Search, Shuffle, Upload, X } from "lucide-react";
import { ApiError, api, uploadFile, uploadTest } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { useApi } from "@/lib/hooks";
import type { LibraryGroup, Persona } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { LibraryGroupSection } from "./library-groups";
import { PersonaCard } from "./persona-card";
import { PersonaSheet } from "./persona-sheet";
import { useToast } from "./toast";
import { Button, Card, Dialog, ErrorNote, cx, useDocTitle } from "./ui";

const AGE_MIN = 15;
const AGE_MAX = 80;
const MAX_BYTES = 500 * 1024 * 1024;
const MEDIA_RE = /\.(mp4|mov|webm|png|jpe?g)$/i;

type Source = "bank" | "library" | "csv";
type FacetItem = { name: string; label?: string; count: number };
type Facets = { total: number; regions: FacetItem[]; occupations: FacetItem[] };
type Phase = "idle" | "media" | "csv" | "create";

function DualSlider({ min, max, value, onChange, labelMin, labelMax }: {
  min: number; max: number; value: [number, number]; onChange: (v: [number, number]) => void; labelMin: string; labelMax: string;
}) {
  const [lo, hi] = value;
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="relative h-6">
      <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded bg-line" />
      <div className="absolute top-1/2 h-1 -translate-y-1/2 rounded bg-ink" style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }} />
      <input
        type="range" className="range range-dual" min={min} max={max} value={lo} aria-label={labelMin}
        style={{ zIndex: lo > max - 10 ? 3 : 1 }}
        onChange={(e) => onChange([Math.min(Number(e.target.value), hi - 1), hi])}
      />
      <input
        type="range" className="range range-dual" min={min} max={max} value={hi} aria-label={labelMax}
        style={{ zIndex: 2 }}
        onChange={(e) => onChange([lo, Math.max(Number(e.target.value), lo + 1)])}
      />
    </div>
  );
}

/** Multi-select over a long list (prefectures, occupations) in a dialog, shown as removable chips outside. */
function FacetField({ label, items, value, onChange }: {
  label: string; items: FacetItem[]; value: string[]; onChange: (v: string[]) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const nameOf = (v: string) => items.find((i) => i.name === v)?.label || v;
  const needle = q.trim().toLowerCase();
  const shown = items.filter((i) => i.name.toLowerCase().includes(needle) || (i.label ?? "").toLowerCase().includes(needle));
  const toggle = (n: string) => onChange(value.includes(n) ? value.filter((x) => x !== n) : [...value, n]);
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <button type="button" onClick={() => setOpen(true)} className="inline-flex h-8 items-center gap-1 rounded-full border border-line px-3 text-xs hover:border-ink">
          <Plus size={12} aria-hidden /> {value.length ? t("new.pickN", { n: value.length }) : t("new.any")}
        </button>
      </div>
      {value.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {value.map((v) => (
            <li key={v}>
              <button type="button" onClick={() => toggle(v)} aria-label={`${nameOf(v)} ×`} className="inline-flex items-center gap-1 rounded-full bg-ink px-2.5 py-0.5 text-xs text-white">
                {nameOf(v)} <X size={11} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} label={label} wide>
        <h2 className="pr-10 text-lg font-bold">{label}</h2>
        <div className="relative mt-4">
          <Search size={15} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-mute" />
          <label htmlFor={`fq-${label}`} className="sr-only">{t("new.filterSearch")}</label>
          <input
            id={`fq-${label}`} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("new.filterSearch")}
            className="h-10 w-full rounded-full border border-line bg-canvas pl-10 pr-4 text-sm"
          />
        </div>
        <ul className="mt-4 grid max-h-[50vh] grid-cols-2 gap-1.5 overflow-y-auto pr-1 sm:grid-cols-3">
          {shown.map((i) => {
            const on = value.includes(i.name);
            return (
              <li key={i.name}>
                <button
                  type="button" aria-pressed={on} onClick={() => toggle(i.name)}
                  className={cx("flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left text-[13px]", on ? "border-ink bg-ink text-white" : "border-line hover:border-ink")}
                >
                  <span className="truncate">{i.label || i.name}</span>
                  <span className={cx("tnum text-[11px]", on ? "text-white/70" : "text-mute")}>{i.count}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="mt-5 flex justify-between">
          <Button variant="ghost" size="sm" onClick={() => onChange([])} disabled={value.length === 0}>{t("new.clear")}</Button>
          <Button onClick={() => setOpen(false)}>{t("new.done")}</Button>
        </div>
      </Dialog>
    </div>
  );
}

type PreviewArgs = {
  enabled: boolean; ageMin: number; ageMax: number; genders: string; count: number;
  regions: string[]; occupations: string[]; seed: number; csv: File | null; lang: string;
};

function usePreview(a: PreviewArgs) {
  const key = [a.ageMin, a.ageMax, a.genders, a.count, a.regions.join("|"), a.occupations.join("|"), a.seed, a.csv ? `${a.csv.name}:${a.csv.size}:${a.csv.lastModified}` : "", a.lang].join("~");
  const [res, setRes] = useState<{ key: string; personas: Persona[] | null; matched?: number; error: unknown }>({ key: "", personas: null, error: null });
  const [last, setLast] = useState<{ personas: Persona[]; matched?: number } | null>(null);
  useEffect(() => {
    if (!a.enabled) return;
    const ac = new AbortController();
    const id = setTimeout(() => {
      type R = { personas: Persona[]; matched?: number };
      let req: Promise<R>;
      if (a.csv) {
        const form = new FormData();
        form.append("age_min", String(a.ageMin)); form.append("age_max", String(a.ageMax));
        form.append("genders", a.genders); form.append("count", String(a.count)); form.append("people_csv", a.csv);
        req = api<R>("/api/audience/preview", { method: "POST", form, signal: ac.signal });
      } else {
        const q = new URLSearchParams({ age_min: String(a.ageMin), age_max: String(a.ageMax), genders: a.genders, count: String(a.count), seed: String(a.seed) });
        if (a.regions.length) q.set("regions", a.regions.join(","));
        if (a.occupations.length) q.set("occupations", a.occupations.join(","));
        req = api<R>(`/api/audience/preview?${q}`, { signal: ac.signal });
      }
      req
        .then((d) => { setLast(d); setRes({ key, personas: d.personas, matched: d.matched, error: null }); })
        .catch((e) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setRes({ key, personas: null, error: e });
        });
    }, 350);
    return () => { clearTimeout(id); ac.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures every input
  }, [key, a.enabled]);
  if (!a.enabled) return { personas: null as Persona[] | null, matched: undefined as number | undefined, loading: false, error: null as unknown };
  const fresh = res.key === key;
  return {
    personas: fresh ? res.personas ?? last?.personas ?? null : last?.personas ?? null,
    matched: fresh ? res.matched ?? last?.matched : last?.matched,
    loading: !fresh,
    error: fresh ? res.error : null,
  };
}

function formatBytes(n: number) {
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}

function StepHead({ n, title }: { n: number; title: string }) {
  return (
    <div className="flex items-center gap-3 border-b-2 border-ink pb-3">
      <span className="tnum grid size-8 shrink-0 place-items-center rounded-full bg-ink text-sm font-bold text-lime" aria-hidden>{n}</span>
      <h2 className="text-2xl font-bold leading-tight tracking-tight sm:text-[26px]">{title}</h2>
    </div>
  );
}

export function NewTest() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const toast = useToast();
  const params = useSearchParams();
  useDocTitle(t("dash.new"));
  const initialLib = (params.get("library") ?? "").split(",").map((x) => x.trim()).filter(Boolean);

  const [source, setSource] = useState<Source>(initialLib.length ? "library" : "bank");
  const [libIds, setLibIds] = useState<string[]>(initialLib);
  const [picker, setPicker] = useState(false);
  const [age, setAge] = useState<[number, number]>([20, 45]);
  const [genders, setGenders] = useState<{ F: boolean; M: boolean }>({ F: true, M: true });
  const [count, setCount] = useState(20);
  const [regions, setRegions] = useState<string[]>([]);
  const [occupations, setOccupations] = useState<string[]>([]);
  const [seed, setSeed] = useState(1);
  const [csv, setCsv] = useState<File | null>(null);
  const [sheet, setSheet] = useState<Persona | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dur, setDur] = useState<number | null>(null);
  const [context, setContext] = useState("");
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [pct, setPct] = useState(0);
  const [submitError, setSubmitError] = useState<{ text: string; retry: boolean } | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const uploaded = useRef<{ media?: { f: File; id: string }; csv?: { f: File; id: string } }>({});
  const csvInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const nameId = useId();
  const ctxId = useId();
  const hintId = useId();

  const facets = useApi<Facets>(source === "bank" ? "/api/audience/facets" : null);
  const lib = useApi<{ groups: LibraryGroup[] }>(source === "library" ? "/api/library" : null);
  const libById = useMemo(() => {
    const m = new Map<string, Persona>();
    lib.data?.groups.forEach((g) => g.personas.forEach((p) => m.set(p.id, p)));
    return m;
  }, [lib.data]);

  const gendersArr = (["F", "M"] as const).filter((g) => genders[g]);
  const gendersParam = gendersArr.join(",");
  const previewOn = source === "bank" || (source === "csv" && !!csv);
  const { personas, matched, loading: previewLoading, error: previewError } = usePreview({
    enabled: previewOn, ageMin: age[0], ageMax: age[1], genders: gendersParam, count,
    regions: source === "bank" ? regions : [], occupations: source === "bank" ? occupations : [], seed, csv: source === "csv" ? csv : null, lang,
  });

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  const isVideo = !!file && /\.(mp4|mov|webm)$/i.test(file.name);

  useEffect(() => {
    if (!previewUrl || !isVideo) return;
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => setDur(Number.isFinite(v.duration) ? v.duration : null);
    v.src = previewUrl;
    return () => { v.onloadedmetadata = null; v.removeAttribute("src"); };
  }, [previewUrl, isVideo]);

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!MEDIA_RE.test(f.name)) return setFileError(t("new.dropBadType"));
    if (f.size > MAX_BYTES) return setFileError(t("new.dropTooLarge"));
    setFileError(null);
    setDur(null);
    setFile(f);
  };

  const toggleGender = (g: "F" | "M") =>
    setGenders((s) => {
      const next = { ...s, [g]: !s[g] };
      return next.F || next.M ? next : s;
    });

  const audienceOk = source === "bank" || (source === "csv" && !!csv) || (source === "library" && libIds.length >= 5 && libIds.length <= 60);
  const busy = phase !== "idle";
  const ready = !!file && audienceOk && !busy;
  const panelCount = source === "library" ? libIds.length : count;
  const minutes = Math.max(1, Math.round(0.5 + (isVideo ? (dur ?? 60) / 120 : 0) + panelCount / 40));

  const start = async () => {
    if (!file || !audienceOk || busy) return;
    setSubmitError(null);
    setPct(0);
    try {
      let mediaId = uploaded.current.media?.f === file ? uploaded.current.media.id : undefined;
      if (!mediaId) {
        setPhase("media");
        const up = uploadFile(file, setPct);
        abortRef.current = up.abort;
        mediaId = await up.promise;
        uploaded.current.media = { f: file, id: mediaId };
      }
      let csvId: string | undefined;
      if (source === "csv" && csv) {
        csvId = uploaded.current.csv?.f === csv ? uploaded.current.csv.id : undefined;
        if (!csvId) {
          setPhase("csv");
          setPct(0);
          const up = uploadFile(csv, setPct);
          abortRef.current = up.abort;
          csvId = await up.promise;
          uploaded.current.csv = { f: csv, id: csvId };
        }
      }
      setPhase("create");
      const panel =
        source === "library"
          ? { source: "library", persona_ids: libIds }
          : source === "csv"
            ? { source: "csv", csv_upload_id: csvId, age_min: age[0], age_max: age[1], genders: gendersArr, count }
            : { source: "bank", age_min: age[0], age_max: age[1], genders: gendersArr, count, seed, ...(regions.length ? { regions } : {}), ...(occupations.length ? { occupations } : {}) };
      const { id } = await api<{ id: string }>("/api/tests", {
        method: "POST",
        json: { upload_id: mediaId, name: name.trim() || undefined, context: context.trim() || undefined, panel, lang },
      });
      router.push(`/tests/${id}`);
    } catch (e) {
      if (e instanceof DOMException) { setPhase("idle"); return; }
      if (e instanceof ApiError && (e.status === 404 || e.status === 405) && !uploaded.current.media) {
        // older backend without direct uploads: fall back to the multipart form
        await legacyStart();
        return;
      }
      if (e instanceof ApiError && e.message === "expired") {
        uploaded.current = {};
        setSubmitError({ text: t("new.uploadExpired"), retry: true });
      } else if (e instanceof ApiError && e.status === 0) {
        setSubmitError({ text: t("new.uploadNet"), retry: true });
      } else {
        setSubmitError({ text: errorText(e, t), retry: true });
      }
      setPhase("idle");
    }
  };

  const legacyStart = async () => {
    if (!file) return;
    setPhase("media");
    const form = new FormData();
    form.append("media", file);
    if (source === "library") form.append("library_persona_ids", libIds.join(","));
    else {
      form.append("age_min", String(age[0])); form.append("age_max", String(age[1]));
      form.append("genders", gendersParam); form.append("count", String(count));
      if (source === "csv" && csv) form.append("people_csv", csv);
    }
    if (name.trim()) form.append("name", name.trim());
    if (context.trim()) form.append("context", context.trim());
    const up = uploadTest(form, setPct);
    abortRef.current = up.abort;
    try {
      const { id } = await up.promise;
      router.push(`/tests/${id}`);
    } catch (e) {
      if (!(e instanceof DOMException)) setSubmitError({ text: errorText(e, t), retry: true });
      setPhase("idle");
    }
  };

  const phaseText = phase === "media" ? t("new.uploading", { pct }) : phase === "csv" ? t("new.phaseCsv") : phase === "create" ? t("new.phaseCreate") : "";
  const audienceSummary =
    source === "library" ? `${t("new.srcLibrary")} · ${t("new.people", { n: libIds.length })}`
      : source === "csv" ? (csv ? `${t("new.srcCsv")} · ${t("new.people", { n: count })}` : "")
        : `${t("new.srcBank")} · ${age[0]}–${age[1]} · ${gendersArr.map((g) => (g === "F" ? t("new.female") : t("new.male"))).join("/")} · ${t("new.people", { n: count })}`;

  const startButton = (full?: boolean) => (
    busy ? (
      <div className={cx("flex items-center gap-3 rounded-full bg-ink py-1 pl-5 pr-1 text-white", full ? "w-full" : "h-12")} role="status">
        <div className="h-1.5 min-w-16 flex-1 overflow-hidden rounded-full bg-white/20">
          <div className="h-full bg-lime transition-[width]" style={{ width: `${phase === "create" ? 100 : pct}%` }} />
        </div>
        <span className="tnum shrink-0 text-sm">{phaseText}</span>
        <button type="button" onClick={() => abortRef.current?.()} disabled={phase === "create"} aria-label={t("new.cancelUpload")} className="on-dark grid size-10 shrink-0 place-items-center rounded-full hover:bg-white/10 disabled:opacity-30">
          <X size={16} aria-hidden />
        </button>
      </div>
    ) : (
      <Button size="lg" className={cx(full && "w-full")} disabled={!ready} onClick={start}>
        <Play size={16} aria-hidden /> {t("new.start")}
      </Button>
    )
  );

  return (
    <div className="mx-auto max-w-[1180px]">
      <Link href="/" className="mb-5 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> {t("new.back")}
      </Link>
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-12">
        <div className="min-w-0 space-y-14">
          {/* STEP 1 */}
          <section aria-labelledby="step1">
            <div id="step1"><StepHead n={1} title={t("new.step1")} /></div>
            <div role="radiogroup" aria-label={t("new.src")} className="mt-6 grid w-full grid-cols-3 gap-1 rounded-[14px] bg-surface p-1 sm:inline-grid sm:w-auto sm:rounded-full">
              {([["bank", "new.srcBank"], ["library", "new.srcLibrary"], ["csv", "new.srcCsv"]] as const).map(([k, label]) => (
                <button
                  key={k} type="button" role="radio" aria-checked={source === k} onClick={() => setSource(k)}
                  className={cx("min-h-9 rounded-[10px] px-2 py-1.5 text-[13px] font-medium leading-tight transition-colors sm:rounded-full sm:px-4", source === k ? "bg-ink text-white" : "text-mute hover:text-ink")}
                >
                  {t(label)}
                </button>
              ))}
            </div>

            {source === "library" && (
              <div className="mt-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="tnum text-sm text-mute" aria-live="polite">{libIds.length < 5 ? t("new.libEmpty") : t("lib.count", { n: libIds.length })}</p>
                  <Button variant="outline" size="sm" onClick={() => setPicker(true)}><Plus size={14} aria-hidden /> {t("new.libAdd")}</Button>
                </div>
                {lib.error && <div className="mt-3"><ErrorNote>{t("lib.loadError")}</ErrorNote></div>}
                <ul className="mt-4 grid grid-cols-3 gap-x-4 gap-y-6 sm:grid-cols-4 md:grid-cols-5">
                  {libIds.map((id) => {
                    const p = libById.get(id);
                    return (
                      <li key={id} className="relative">
                        {p ? <PersonaCard persona={p} meta={p.profile?.meta} title={p.profile?.headline || p.name} onDetails={() => setSheet(p)} /> : <div className="pulse aspect-[4/5] rounded-card bg-surface" />}
                        <button
                          type="button" aria-label={t("new.libRemove", { name: p?.name ?? id })}
                          onClick={() => setLibIds((x) => x.filter((i) => i !== id))}
                          className="absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-ink/80 text-white hover:bg-ink"
                        >
                          <X size={14} aria-hidden />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {source === "csv" && (
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <input
                  ref={csvInput} type="file" accept=".csv,text/csv" className="sr-only" tabIndex={-1} aria-hidden
                  onChange={(e) => { setCsv(e.target.files?.[0] ?? null); e.target.value = ""; }}
                />
                <Button variant="outline" size="sm" onClick={() => csvInput.current?.click()}>
                  <FileUp size={14} aria-hidden /> {csv ? t("new.csvReplace") : t("new.csvPick")}
                </Button>
                {csv ? (
                  <span className="inline-flex items-center gap-2 rounded-full bg-surface py-1 pl-3 pr-1 text-sm">
                    <span className="max-w-[220px] truncate">{csv.name}</span>
                    <button type="button" aria-label={t("new.csvRemove")} onClick={() => setCsv(null)} className="grid size-6 place-items-center rounded-full hover:bg-canvas"><X size={14} aria-hidden /></button>
                  </span>
                ) : <span className="text-sm text-mute">{t("new.csvPickHint")}</span>}
              </div>
            )}

            {source !== "library" && (
              <Card className="mt-5 grid grid-cols-1 gap-x-8 gap-y-7 p-6 sm:p-7 md:grid-cols-[1.4fr_1fr_1fr]">
                <div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm font-medium">{t("new.age")}</span>
                    <output className="tnum text-sm text-mute" aria-live="polite">{t("new.ageRange", { min: age[0], max: age[1] })}</output>
                  </div>
                  <div className="mt-3"><DualSlider min={AGE_MIN} max={AGE_MAX} value={age} onChange={setAge} labelMin={t("new.ageMin")} labelMax={t("new.ageMax")} /></div>
                </div>
                <fieldset>
                  <legend className="text-sm font-medium">{t("new.gender")}</legend>
                  <div className="mt-3 flex gap-2">
                    {(["F", "M"] as const).map((g) => (
                      <button
                        key={g} type="button" aria-pressed={genders[g]} onClick={() => toggleGender(g)}
                        className={cx("h-9 flex-1 rounded-full border text-sm font-medium transition-colors", genders[g] ? "border-ink bg-ink text-white" : "border-line bg-surface text-mute hover:text-ink")}
                      >
                        {g === "F" ? t("new.female") : t("new.male")}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <div>
                  <div className="flex items-baseline justify-between">
                    <label htmlFor="count" className="text-sm font-medium">{t("new.count")}</label>
                    <output htmlFor="count" className="tnum text-sm text-mute">{count}</output>
                  </div>
                  <div className="mt-3"><input id="count" type="range" className="range" min={5} max={60} value={count} onChange={(e) => setCount(Number(e.target.value))} /></div>
                </div>
                {source === "bank" && facets.data && (
                  <>
                    <div className="md:col-span-1"><FacetField label={t("new.regions")} items={facets.data.regions} value={regions} onChange={setRegions} /></div>
                    <div className="md:col-span-2"><FacetField label={t("new.occupations")} items={facets.data.occupations} value={occupations} onChange={setOccupations} /></div>
                  </>
                )}
              </Card>
            )}

            {previewOn && (
              <div className="mt-8">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">
                    {t("new.previewLabel")}
                    {previewLoading && (
                      <span role="status" className="inline-flex items-center gap-1.5 normal-case tracking-normal">
                        <Loader2 size={12} className="motion-safe:animate-spin" aria-hidden /> {t("new.previewLoading")}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {matched != null && facets.data && (
                      <p className="tnum text-sm" aria-live="polite">
                        <b>{matched.toLocaleString()}</b> <span className="text-mute">{t("new.matchedOf", { total: facets.data.total.toLocaleString() })}</span>
                      </p>
                    )}
                    {source === "bank" && (
                      <Button variant="outline" size="sm" onClick={() => setSeed(Math.floor(Math.random() * 1_000_000))}><Shuffle size={13} aria-hidden /> {t("new.shuffle")}</Button>
                    )}
                  </div>
                </div>
                {previewError != null && !personas && <ErrorNote>{t("new.previewError")} {errorText(previewError, t)}</ErrorNote>}
                <ul className={cx("grid grid-cols-2 gap-x-4 gap-y-6 transition-opacity duration-300 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5", previewLoading && personas && "opacity-50")}>
                  {(personas ?? []).map((p) => (
                    <li key={p.id}><PersonaCard persona={p} meta={p.profile?.meta} title={p.profile?.headline || p.name} onDetails={p.profile ? () => setSheet(p) : undefined} /></li>
                  ))}
                  {!personas && !previewError && Array.from({ length: Math.min(count, 10) }, (_, i) => (
                    <li key={i}><div className="pulse aspect-[4/5] rounded-card bg-surface" style={{ animationDelay: `${i * 80}ms` }} /><div className="mt-2 h-2.5 w-2/3 rounded bg-surface" /><div className="mt-1.5 h-3 w-full rounded bg-surface" /></li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* STEP 2 */}
          <section aria-labelledby="step2">
            <div id="step2"><StepHead n={2} title={t("new.step2")} /></div>
            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-[1.3fr_1fr]">
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
                className={cx("relative grid min-h-[260px] place-items-center rounded-card border-2 border-dashed p-6 text-center transition-colors", dragging ? "border-ink bg-white" : "border-line bg-surface", file && "border-solid border-transparent")}
              >
                <input
                  ref={fileInput} id="media-file" type="file" className="sr-only" accept=".mp4,.mov,.webm,.png,.jpg,.jpeg,video/*,image/png,image/jpeg"
                  onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }}
                  aria-describedby={fileError ? `${hintId}-err` : hintId}
                />
                {file && previewUrl ? (
                  <div className="w-full">
                    <div className="mx-auto max-h-[300px] overflow-hidden rounded-xl bg-ink">
                      {isVideo
                        ? <video src={previewUrl} muted playsInline preload="metadata" className="mx-auto max-h-[300px] w-full object-contain" />
                        // eslint-disable-next-line @next/next/no-img-element -- local blob preview
                        : <img src={previewUrl} alt="" className="mx-auto max-h-[300px] w-full object-contain" />}
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3 text-left text-sm">
                      <span className="flex min-w-0 items-center gap-2">
                        {isVideo ? <Film size={16} aria-hidden /> : <ImageIcon size={16} aria-hidden />}
                        <span className="truncate font-medium">{file.name}</span>
                        <span className="tnum shrink-0 text-mute">{formatBytes(file.size)}</span>
                      </span>
                      <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()} disabled={busy}>{t("new.dropChange")}</Button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="mx-auto grid size-12 place-items-center rounded-full bg-ink text-lime"><Upload size={20} aria-hidden /></div>
                    <p className="mt-4 text-lg font-bold">{t("new.drop")}</p>
                    <button type="button" onClick={() => fileInput.current?.click()} className="mt-1 text-sm underline underline-offset-4">{t("new.dropOr")}</button>
                    <p id={hintId} className="mt-3 text-xs text-mute">{t("new.dropHint")}</p>
                  </div>
                )}
              </div>
              <div>
                <label htmlFor={nameId} className="text-sm font-medium">{t("new.name")}</label>
                <input
                  id={nameId} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={t("new.namePlaceholder")}
                  className="mb-5 mt-2 h-11 w-full rounded-card border border-line bg-surface px-4 text-sm placeholder:text-mute/70"
                />
                <label htmlFor={ctxId} className="text-sm font-medium">{t("new.context")}</label>
                <p className="mt-0.5 text-xs text-mute">{t("new.contextHint")}</p>
                <textarea
                  id={ctxId} rows={5} value={context} maxLength={1000} onChange={(e) => setContext(e.target.value)} placeholder={t("new.contextPlaceholder")}
                  className="mt-2 w-full resize-y rounded-card border border-line bg-surface p-4 text-sm placeholder:text-mute/70"
                />
              </div>
            </div>
            <div role="alert" id={`${hintId}-err`} className="mt-3 min-h-5 text-sm text-danger">{fileError}</div>
          </section>

          {/* STEP 3 (mobile: inline; desktop: the sticky summary) */}
          <section aria-labelledby="step3" className="lg:hidden">
            <div id="step3"><StepHead n={3} title={t("new.step3")} /></div>
            {renderSummary()}
          </section>
        </div>

        <aside className="hidden lg:block">
          <div className="sticky top-20">
            {renderSummary()}
          </div>
        </aside>
      </div>

      <Dialog open={picker} onClose={() => setPicker(false)} label={t("new.libPickerTitle")} side xl>
        <h2 className="pr-10 text-xl font-bold">{t("new.libPickerTitle")}</h2>
        <div className="mt-6 space-y-10">
          {lib.loading && <p className="pulse text-sm text-mute">{t("common.loading")}</p>}
          {lib.data?.groups.map((g) => (
            <LibraryGroupSection
              key={g.id} group={g} headingAs="h3" selecting picked={new Set(libIds)}
              onToggle={(p) => setLibIds((x) => (x.includes(p.id) ? x.filter((i) => i !== p.id) : x.length >= 60 ? (toast.error(t("lib.maxPick")), x) : [...x, p.id]))}
            />
          ))}
        </div>
        <div className="sticky bottom-0 -mx-6 mt-6 flex items-center justify-between bg-surface px-6 py-3 sm:-mx-8 sm:px-8">
          <span className="tnum text-sm text-mute">{t("vw.selectedCount", { n: libIds.length })}</span>
          <Button onClick={() => setPicker(false)}>{t("new.libDone")}</Button>
        </div>
      </Dialog>
      <PersonaSheet persona={sheet} pid={sheet?.id ?? null} onClose={() => setSheet(null)} />
    </div>
  );

  function renderSummary() {
    return (
      <Card className="p-6">
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("new.summary")}</p>
        <dl className="mt-4 space-y-4 text-sm">
          <div>
            <dt className="flex items-center gap-2 text-xs text-mute"><span className={cx("grid size-4 place-items-center rounded-full", audienceOk ? "bg-ink text-lime" : "border border-line")} aria-hidden>{audienceOk && <Check size={10} strokeWidth={3} />}</span>{t("new.sumAudience")}</dt>
            <dd className="mt-1 font-medium leading-snug">{audienceSummary || t("new.sumNone")}</dd>
            {source === "bank" && (regions.length > 0 || occupations.length > 0) && <dd className="mt-0.5 text-xs text-mute">{[...regions.map((r) => facets.data?.regions.find((x) => x.name === r)?.label || r), ...occupations.map((o) => facets.data?.occupations.find((x) => x.name === o)?.label || o)].join(" · ")}</dd>}
          </div>
          <div>
            <dt className="flex items-center gap-2 text-xs text-mute"><span className={cx("grid size-4 place-items-center rounded-full", file ? "bg-ink text-lime" : "border border-line")} aria-hidden>{file && <Check size={10} strokeWidth={3} />}</span>{t("new.sumAd")}</dt>
            <dd className="mt-1 truncate font-medium">{file ? file.name : t("new.sumNone")}</dd>
          </div>
          <div>
            <dt className="text-xs text-mute">{t("new.sumTime")}</dt>
            <dd className="tnum mt-1 text-2xl font-bold">{t("new.sumTimeVal", { n: minutes })}</dd>
            <dd className="mt-1 text-xs leading-relaxed text-mute">{t("new.sumHint")}</dd>
          </div>
        </dl>
        {submitError && (
          <div role="alert" className="mt-4 rounded-xl bg-danger/5 p-3 text-sm text-danger">
            <p>{submitError.text}</p>
            {submitError.retry && <button type="button" onClick={start} className="mt-2 inline-flex items-center gap-1.5 font-medium underline underline-offset-4"><RefreshCw size={13} aria-hidden /> {t("new.retry")}</button>}
          </div>
        )}
        <div className="mt-5">{startButton(true)}</div>
        {!file && <p className="mt-2 text-center text-xs text-mute">{t("new.needFile")}</p>}
      </Card>
    );
  }
}
