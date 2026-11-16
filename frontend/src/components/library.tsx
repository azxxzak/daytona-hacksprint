"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, FlaskConical } from "lucide-react";
import { errorText } from "@/lib/errors";
import { useApi } from "@/lib/hooks";
import type { LibraryGroup, Persona } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { LibraryGroupSection } from "./library-groups";
import { PersonaSheet } from "./persona-sheet";
import { useToast } from "./toast";
import { Button, ErrorNote, SectionHeader, Skeleton, useDocTitle } from "./ui";

export function Library() {
  const { t } = useI18n();
  const router = useRouter();
  const toast = useToast();
  useDocTitle(t("nav.library"));
  const { data, error, loading, reload } = useApi<{ groups: LibraryGroup[] }>("/api/library");
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<Persona | null>(null);

  const startTest = (ids: string[]) => router.push(`/tests/new?library=${ids.join(",")}`);
  const toggle = (p: Persona) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(p.id)) n.delete(p.id);
      else if (n.size >= 60) toast.error(t("lib.maxPick"));
      else n.add(p.id);
      return n;
    });
  const exit = () => { setSelecting(false); setPicked(new Set()); };

  return (
    <div className="space-y-12">
      <SectionHeader
        as="h1"
        label={t("lib.label")}
        title={t("lib.title")}
        action={
          selecting ? (
            <Button size="sm" onClick={exit}>{t("vw.doneSelect")}</Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setSelecting(true)}><Check size={14} aria-hidden /> {t("lib.select")}</Button>
          )
        }
      />
      {error && !data && <ErrorNote action={<Button variant="outline" size="sm" onClick={reload}>{t("common.retry")}</Button>}>{t("lib.loadError")} {errorText(error, t)}</ErrorNote>}
      {loading && !data && !error && (
        <div aria-busy="true" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="aspect-[4/5]" />)}
        </div>
      )}
      {data?.groups.map((g) => (
        <LibraryGroupSection
          key={g.id}
          group={g}
          selecting={selecting}
          picked={picked}
          onToggle={toggle}
          onDetails={setOpen}
          onUse={(p) => startTest([p.id])}
          onUseGroup={(grp) => startTest(grp.personas.slice(0, 60).map((p) => p.id))}
        />
      ))}

      {selecting && (
        <div className="fixed inset-x-0 bottom-0 z-20 flex justify-center bg-ink/10 px-4 py-4 backdrop-blur-sm">
          <div className="flex flex-wrap items-center justify-center gap-2">
            <span className="tnum mr-1 hidden text-sm sm:inline" aria-live="polite">{t("vw.selectedCount", { n: picked.size })}</span>
            <Button size="lg" disabled={picked.size === 0} onClick={() => startTest([...picked])}>
              <FlaskConical size={16} aria-hidden /> {t("lib.testWith", { n: picked.size })}
            </Button>
            <Button size="lg" variant="outline" onClick={exit}>{t("common.cancel")}</Button>
          </div>
        </div>
      )}

      <PersonaSheet persona={open} pid={open?.id ?? null} onClose={() => setOpen(null)} actionLabel={t("lib.use")} onAction={(p) => startTest([p.id])} />
    </div>
  );
}
