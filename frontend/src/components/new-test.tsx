"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ArrowLeft, FileUp, Film, Image as ImageIcon, Loader2, Play, Upload, X } from "lucide-react";
import { api, uploadTest } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Persona } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { PersonaCard } from "./persona-card";
import { Button, Card, ErrorNote, SectionHeader, cx, useDocTitle } from "./ui";

const AGE_MIN = 15;
const AGE_MAX = 80;
const MAX_BYTES = 500 * 1024 * 1024;
const MEDIA_RE = /\.(mp4|mov|webm|png|jpe?g)$/i;

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

function usePreview(ageMin: number, ageMax: number, genders: string, count: number, csv: File | null) {
  const key = `${ageMin}-${ageMax}-${genders}-${count}-${csv ? `${csv.name}:${csv.size}:${csv.lastModified}` : ""}`;
  const [res, setRes] = useState<{ key: string; personas: Persona[] | null; error: unknown }>({ key: "", personas: null, error: null });
  const [last, setLast] = useState<Persona[] | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    const id = setTimeout(() => {
      const q = new URLSearchParams({ age_min: String(ageMin), age_max: String(ageMax), genders, count: String(count) });
      let req;
      if (csv) {
        const form = new FormData();
        form.append("age_min", String(ageMin)); form.append("age_max", String(ageMax));
        form.append("genders", genders); form.append("count", String(count)); form.append("people_csv", csv);
        req = api<{ personas: Persona[] }>("/api/audience/preview", { method: "POST", form, signal: ac.signal });
      } else {
        req = api<{ personas: Persona[] }>(`/api/audience/preview?${q}`, { signal: ac.signal });
      }
      req
        .then((d) => { setLast(d.personas); setRes({ key, personas: d.personas, error: null }); })
        .catch((e) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setRes({ key, personas: null, error: e });
        });
    }, 400);
    return () => { clearTimeout(id); ac.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key covers csv identity
  }, [ageMin, ageMax, genders, count, key]);
  // keep showing the previous panel (dimmed) while the next one loads
  return { personas: res.key === key ? res.personas ?? last : last, loading: res.key !== key, error: res.key === key ? res.error : null };
}

function formatBytes(n: number) {
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}

export function NewTest() {
  const { t } = useI18n();
  const router = useRouter();
  const [age, setAge] = useState<[number, number]>([20, 45]);
  const [genders, setGenders] = useState<{ F: boolean; M: boolean }>({ F: true, M: true });
  const [count, setCount] = useState(20);
  const [csv, setCsv] = useState<File | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [context, setContext] = useState("");
  const [name, setName] = useState("");
  const nameId = useId();
  useDocTitle(t("dash.new"));
  const [dragging, setDragging] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const csvInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const ctxId = useId();
  const hintId = useId();

  const gendersParam = [genders.F && "F", genders.M && "M"].filter(Boolean).join(",");
  const { personas, loading: previewLoading, error: previewError } = usePreview(age[0], age[1], gendersParam, count, csv);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  const isVideo = !!file && /\.(mp4|mov|webm)$/i.test(file.name);

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!MEDIA_RE.test(f.name)) return setFileError(t("new.dropBadType"));
    if (f.size > MAX_BYTES) return setFileError(t("new.dropTooLarge"));
    setFileError(null);
    setFile(f);
  };

  const toggleGender = (g: "F" | "M") =>
    setGenders((s) => {
      const next = { ...s, [g]: !s[g] };
      return next.F || next.M ? next : s; // at least one stays on
    });

  const uploading = pct !== null;
  const start = async () => {
    if (!file || uploading) return;
    setSubmitError(null);
    setPct(0);
    const form = new FormData();
    form.append("media", file);
    form.append("age_min", String(age[0]));
    form.append("age_max", String(age[1]));
    form.append("genders", gendersParam);
    form.append("count", String(count));
    if (name.trim()) form.append("name", name.trim());
    if (context.trim()) form.append("context", context.trim());
    if (csv) form.append("people_csv", csv);
    const up = uploadTest(form, setPct);
    abortRef.current = up.abort;
    try {
      const { id } = await up.promise;
      router.push(`/tests/${id}`);
    } catch (e) {
      if (!(e instanceof DOMException)) setSubmitError(errorText(e, t));
      setPct(null);
    }
  };

  return (
    <div className="mx-auto max-w-[1100px] space-y-14">
      <div>
        <Link href="/" className="mb-4 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
          <ArrowLeft size={15} aria-hidden /> {t("new.back")}
        </Link>

        <SectionHeader
          as="h1"
          label={t("new.audienceLabel")}
          title={t("new.audienceTitle")}
          action={
            <>
              <input
                ref={csvInput} type="file" accept=".csv,text/csv" className="sr-only" tabIndex={-1} aria-hidden
                onChange={(e) => { setCsv(e.target.files?.[0] ?? null); e.target.value = ""; }}
              />
              <Button variant="outline" size="sm" onClick={() => csvInput.current?.click()}>
                <FileUp size={14} aria-hidden /> {csv ? t("new.csvReplace") : t("new.csv")}
              </Button>
            </>
          }
        />

        <Card className="mt-6 grid grid-cols-1 gap-8 p-6 sm:p-8 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium">{t("new.age")}</span>
              <output className="tnum text-sm text-mute" aria-live="polite">{t("new.ageRange", { min: age[0], max: age[1] })}</output>
            </div>
            <div className="mt-3">
              <DualSlider min={AGE_MIN} max={AGE_MAX} value={age} onChange={setAge} labelMin={t("new.ageMin")} labelMax={t("new.ageMax")} />
            </div>
          </div>

          <fieldset>
            <legend className="text-sm font-medium">{t("new.gender")}</legend>
            <div className="mt-3 flex gap-2">
              {(["F", "M"] as const).map((g) => (
                <button
                  key={g} type="button" aria-pressed={genders[g]} onClick={() => toggleGender(g)}
                  className={cx("h-9 flex-1 rounded-full border text-sm font-medium transition-colors",
                    genders[g] ? "border-ink bg-ink text-white" : "border-line bg-surface text-mute hover:text-ink")}
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
            <div className="mt-3">
              <input id="count" type="range" className="range" min={5} max={60} value={count} onChange={(e) => setCount(Number(e.target.value))} />
            </div>
          </div>
        </Card>

        {csv && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-mute">
            <span className="inline-flex items-center gap-2 rounded-full bg-surface py-1 pl-3 pr-1 text-ink">
              <FileUp size={14} aria-hidden /> <span className="max-w-[220px] truncate">{csv.name}</span>
              <button type="button" aria-label={t("new.csvRemove")} onClick={() => setCsv(null)} className="grid size-6 place-items-center rounded-full hover:bg-canvas">
                <X size={14} aria-hidden />
              </button>
            </span>
            <span>{t("new.csvNote")}</span>
          </div>
        )}

        <div className="mt-8">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">
            {t("new.previewLabel")}
            {previewLoading && (
              <span role="status" className="inline-flex items-center gap-1.5 normal-case tracking-normal">
                <Loader2 size={12} className="motion-safe:animate-spin" aria-hidden /> {t("new.previewLoading")}
              </span>
            )}
          </div>
          {previewError != null && !personas && <ErrorNote>{t("new.previewError")} {errorText(previewError, t)}</ErrorNote>}
          <ul className={cx("grid grid-cols-2 gap-x-4 gap-y-6 transition-opacity sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6", previewLoading && personas && "opacity-50")}>
            {(personas ?? []).map((p) => (
              <li key={p.id}><PersonaCard persona={p} /></li>
            ))}
            {!personas && !previewError && Array.from({ length: 12 }, (_, i) => (
              <li key={i}><div className="pulse aspect-[4/5] rounded-card bg-surface" /></li>
            ))}
          </ul>
        </div>
      </div>

      <div>
        <SectionHeader label={t("new.adLabel")} title={t("new.adTitle")} />
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-[1.3fr_1fr]">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
            className={cx("relative grid min-h-[260px] place-items-center rounded-card border-2 border-dashed p-6 text-center transition-colors",
              dragging ? "border-ink bg-white" : "border-line bg-surface", file && "border-solid border-transparent")}
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
                  <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()} disabled={uploading}>{t("new.dropChange")}</Button>
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
              id={ctxId} rows={5} value={context} maxLength={1000} onChange={(e) => setContext(e.target.value)}
              placeholder={t("new.contextPlaceholder")}
              className="mt-2 w-full resize-y rounded-card border border-line bg-surface p-4 text-sm placeholder:text-mute/70"
            />
          </div>
        </div>
        <div role="alert" id={`${hintId}-err`} className="mt-3 min-h-5 text-sm text-danger">
          {fileError ?? submitError}
        </div>
        {!file && !fileError && <p className="mt-1 text-sm text-mute">{t("new.needFile")}</p>}
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center px-4">
        {uploading ? (
          <div className="pointer-events-auto flex h-12 items-center gap-3 rounded-full bg-ink py-1 pl-5 pr-1 text-white" role="status">
            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-white/20 sm:w-40">
              <div className="h-full bg-lime transition-[width]" style={{ width: `${pct}%` }} />
            </div>
            <span className="tnum text-sm">{t("new.uploading", { pct: pct ?? 0 })}</span>
            <button type="button" onClick={() => abortRef.current?.()} aria-label={t("new.cancelUpload")} className="on-dark grid size-10 place-items-center rounded-full hover:bg-white/10">
              <X size={16} aria-hidden />
            </button>
          </div>
        ) : (
          <Button size="lg" className="pointer-events-auto pl-5" disabled={!file} onClick={start}>
            <Play size={16} aria-hidden /> {t("new.start")}
          </Button>
        )}
      </div>
    </div>
  );
}
