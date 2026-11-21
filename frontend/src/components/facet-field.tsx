"use client";

import { useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { useI18n } from "./i18n-provider";
import { Button, Dialog, cx } from "./ui";

export type FacetItem = { name: string; label?: string; count: number };

/** Multi-select filter with a searchable dialog. `name` is the value sent to the API, `label` what people read. */
export function FacetField({ label, items, value, onChange }: {
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
