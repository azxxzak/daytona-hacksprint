"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Test, TestSummary } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { useToast } from "../toast";

export function TestName({ test, onRenamed }: { test: Test; onRenamed: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(test.name);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const edit = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  const save = async () => {
    const name = value.trim();
    if (!name || name === test.name) { setEditing(false); edit.current?.focus(); return; }
    setBusy(true);
    try {
      await api<TestSummary>(`/api/tests/${test.id}`, { method: "PATCH", json: { name } });
      toast.success(t("toast.renamed"));
      onRenamed();
      setEditing(false);
    } catch (e) {
      toast.error(errorText(e, t));
    } finally {
      setBusy(false);
    }
  };
  const cancel = () => { setEditing(false); setValue(test.name); };

  if (editing) {
    return (
      <form onSubmit={(e) => { e.preventDefault(); void save(); }} className="mt-1 flex max-w-xl items-center gap-2">
        <label className="sr-only" htmlFor="rename-test">{t("rename.label")}</label>
        <input
          ref={input} id="rename-test" value={value} maxLength={120} disabled={busy}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          className="h-9 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-base font-bold"
        />
        <button type="submit" disabled={busy} aria-label={t("common.save")} className="grid size-9 place-items-center rounded-full bg-ink text-lime disabled:opacity-40"><Check size={16} aria-hidden /></button>
        <button type="button" onClick={cancel} aria-label={t("common.cancel")} className="grid size-9 place-items-center rounded-full border border-line bg-surface"><X size={16} aria-hidden /></button>
      </form>
    );
  }
  return (
    <div className="mt-1 flex min-w-0 items-center gap-1">
      <h1 className="truncate text-base font-bold" title={test.name}>{test.name}</h1>
      <button
        ref={edit} type="button" onClick={() => { setValue(test.name); setEditing(true); }} aria-label={t("rename.edit")}
        className="grid size-7 shrink-0 place-items-center rounded-full text-mute hover:bg-ink/5 hover:text-ink"
      >
        <Pencil size={14} aria-hidden />
      </button>
    </div>
  );
}
