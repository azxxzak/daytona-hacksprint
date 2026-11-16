"use client";

import { useMemo, useState } from "react";
import { MessageCircle } from "lucide-react";
import { fmtTime, mean, thoughtOf } from "@/lib/format";
import type { Persona, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { PersonaCard, usePersonaMeta } from "../persona-card";
import { Avatar, Button, Dialog, SectionHeader } from "../ui";

export function usePersonaAverages(test: Test) {
  return useMemo(() => {
    const m = new Map<string, number[]>();
    for (const g of test.gaze) (m.get(g.id) ?? m.set(g.id, []).get(g.id)!).push(g.interest);
    return new Map([...m].map(([id, v]) => [id, mean(v) ?? 0]));
  }, [test.gaze]);
}

function Chips({ value }: { value: string }) {
  const items = value.split(",").map((s) => s.trim()).filter(Boolean);
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((x) => <li key={x} className="rounded-full bg-canvas px-2.5 py-0.5 text-xs">{x}</li>)}
    </ul>
  );
}

function ProfileSheet({ test, persona, onClose, onInterview }: { test: Test; persona: Persona | null; onClose: () => void; onInterview: (p: Persona) => void }) {
  const { t, lang } = useI18n();
  const meta = usePersonaMeta();
  const timeline = useMemo(() => (persona ? test.gaze.filter((g) => g.id === persona.id).sort((a, b) => a.t - b.t) : []), [test.gaze, persona]);
  const avgs = usePersonaAverages(test);
  const rowsDef: [Parameters<typeof t>[0], string][] = persona
    ? [["vw.region", persona.region], ["vw.occupation", persona.occupation], ["vw.income", persona.income]]
    : [];
  return (
    <Dialog open={!!persona} onClose={onClose} label={persona?.name ?? t("vw.details")} side>
      {persona && (
        <div>
          <div className="flex items-center gap-4 pr-10">
            <Avatar src={persona.avatar_url} name={persona.name} color={persona.color} rounded="rounded-full" eager className="size-20 shrink-0" />
            <div className="min-w-0">
              <h2 className="truncate text-xl font-bold">{persona.name}</h2>
              <p className="text-sm text-mute">{meta(persona)}</p>
              <p className="tnum mt-1 text-sm">{t("vw.avg", { v: (avgs.get(persona.id) ?? 0).toFixed(1) })}</p>
            </div>
          </div>
          <Button className="mt-5 w-full" onClick={() => onInterview(persona)}>
            <MessageCircle size={16} aria-hidden /> {t("vw.interview")}
          </Button>

          <h3 className="mt-8 border-b-2 border-ink pb-2 text-sm font-bold">{t("vw.profile")}</h3>
          <dl className="mt-3 space-y-3 text-sm">
            {rowsDef.map(([k, v]) => v ? (
              <div key={k}><dt className="text-xs text-mute">{t(k)}</dt><dd>{v}</dd></div>
            ) : null)}
            {([["vw.interests", persona.interests], ["vw.media", persona.media], ["vw.values", persona.values]] as const).map(([k, v]) => v ? (
              <div key={k}><dt className="text-xs text-mute">{t(k)}</dt><dd><Chips value={v} /></dd></div>
            ) : null)}
          </dl>

          {timeline.length > 0 && (
            <>
              <h3 className="mt-8 border-b-2 border-ink pb-2 text-sm font-bold">{t("vw.timeline")}</h3>
              <ol className="mt-3 divide-y divide-line">
                {timeline.map((g) => (
                  <li key={g.t} className="py-3 text-sm">
                    <p className="tnum flex items-center justify-between text-xs text-mute">
                      <span>{test.media_kind === "video" ? fmtTime(g.t) : ""} {g.looking_at && `· ${g.looking_at}`}</span>
                      <span className="text-ink">{g.interest} / 5</span>
                    </p>
                    <p className="mt-1 leading-snug">{thoughtOf(g, lang)}</p>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </Dialog>
  );
}

export function Viewers({ test, onInterview }: { test: Test; onInterview: (p: Persona) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<Persona | null>(null);
  const avgs = usePersonaAverages(test);
  return (
    <div>
      <SectionHeader label={t("vw.label")} title={t("vw.title")} />
      <ul className="mt-6 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {test.personas.map((p, i) => (
          <li key={p.id}>
            <PersonaCard
              persona={p}
              eager={i < 6}
              onDetails={() => setOpen(p)}
              onInterview={() => onInterview(p)}
              badge={<span className="tnum rounded-full bg-ink/80 px-2 py-0.5 text-[11px] text-white">{(avgs.get(p.id) ?? 0).toFixed(1)}</span>}
            />
          </li>
        ))}
      </ul>
      <ProfileSheet test={test} persona={open} onClose={() => setOpen(null)} onInterview={(p) => { setOpen(null); onInterview(p); }} />
    </div>
  );
}
