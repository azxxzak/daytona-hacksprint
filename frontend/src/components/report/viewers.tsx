"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Check, MessageCircle, Users } from "lucide-react";
import { EvidenceLabel } from "../evidence";
import { PersonaSheet } from "../persona-sheet";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { fmtTime, mean, thoughtOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Persona, Talk, TalkMode, TalkSummary, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { PersonaCard } from "../persona-card";
import { useToast } from "../toast";
import { Avatar, Button, Dialog, ErrorNote, SectionHeader, Skeleton } from "../ui";
import { ModeCard, MODES } from "./talk-modes";

export function usePersonaAverages(test: Test) {
  return useMemo(() => {
    const m = new Map<string, number[]>();
    for (const g of test.gaze) (m.get(g.id) ?? m.set(g.id, []).get(g.id)!).push(g.interest);
    return new Map([...m].map(([id, v]) => [id, mean(v) ?? 0]));
  }, [test.gaze]);
}

function ProfileSheet({ test, persona, onClose, onTalk }: { test: Test; persona: Persona | null; onClose: () => void; onTalk: (p: Persona) => void }) {
  const { t, lang } = useI18n();
  const timeline = useMemo(() => (persona ? test.gaze.filter((g) => g.id === persona.id).sort((a, b) => a.t - b.t) : []), [test.gaze, persona]);
  const avgs = usePersonaAverages(test);
  return (
    <PersonaSheet
      persona={persona} pid={persona ? `${test.id}:${persona.id}` : null} onClose={onClose} readOnly={test.read_only}
      actionLabel={test.read_only ? undefined : t("vw.talk")} onAction={test.read_only ? undefined : onTalk}
    >
      {persona && (
        <p className="tnum mt-4 text-sm text-mute">{t("vw.avg", { v: (avgs.get(persona.id) ?? 0).toFixed(1) })}</p>
      )}
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
                <p className="mt-1 leading-snug">{thoughtOf(g, test.lang ?? lang)}</p>
                <EvidenceLabel basis={g.basis} because={g.because} className="mt-1" />
              </li>
            ))}
          </ol>
        </>
      )}
    </PersonaSheet>
  );
}

export function TalkModeLabel({ mode }: { mode: TalkMode }) {
  const { t } = useI18n();
  return <>{mode === "conversation" ? t("talk.modeConv") : t("talk.modeQa")}</>;
}

function PastTalks({ test, personas }: { test: Test; personas: Map<string, Persona> }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { data, error, loading, reload } = useApi<{ talks: TalkSummary[] }>(`/api/tests/${test.id}/talks`);
  const fmt = new Intl.DateTimeFormat(lang === "ja" ? "ja-JP" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
  return (
    <section className="mt-6" aria-label={t("vw.talksTitle")}>
      <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("vw.talksTitle")}</p>
      {loading && !data && <Skeleton className="h-[72px]" />}
      {error && !data && <ErrorNote action={<Button variant="outline" size="sm" onClick={reload}>{t("common.retry")}</Button>}>{t("vw.talksError")}</ErrorNote>}
      {data && data.talks.length === 0 && <p className="rounded-card bg-surface px-5 py-4 text-sm text-mute">{t("vw.talksEmpty")}</p>}
      {data && data.talks.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.talks.map((k) => {
            const members = k.persona_ids.map((id) => personas.get(id)).filter((p): p is Persona => !!p);
            return (
              <li key={k.id}>
                <button
                  type="button"
                  onClick={() => router.push(`/tests/${test.id}/talks/${k.id}`)}
                  className="flex h-full w-full flex-col gap-2 rounded-card bg-surface p-4 text-left transition-colors hover:bg-white"
                >
                  <span className="line-clamp-2 text-[15px] font-bold leading-snug">{k.title || t("talk.untitled")}</span>
                  <span className="flex items-center justify-between gap-3 text-xs text-mute">
                    <span className="flex items-center">
                      <span className="flex -space-x-2">
                        {members.slice(0, 5).map((p) => (
                          <Avatar key={p.id} src={p.avatar_url} name={p.name} rounded="rounded-full" className="size-6 ring-2 ring-white" />
                        ))}
                      </span>
                      {members.length > 5 && <span className="tnum ml-1.5">+{members.length - 5}</span>}
                    </span>
                    <span className="truncate"><TalkModeLabel mode={k.mode} /> · <span className="tnum">{fmt.format(new Date(k.updated_at))}</span></span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const MAX_PICK = 20;

export function Viewers({ test }: { test: Test }) {
  const { t } = useI18n();
  const router = useRouter();
  const toast = useToast();
  const [open, setOpen] = useState<Persona | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const avgs = usePersonaAverages(test);
  const byId = useMemo(() => new Map(test.personas.map((p) => [p.id, p])), [test.personas]);
  const ids = test.personas.filter((p) => picked.has(p.id)).map((p) => p.id);

  const toggle = (id: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else if (n.size >= MAX_PICK) toast.error(t("vw.selectMax"));
      else n.add(id);
      return n;
    });
  const exitSelect = () => { setSelecting(false); setPicked(new Set()); };

  const create = async (personaIds: string[], mode: TalkMode) => {
    setCreating(true);
    try {
      const talk = await api<Talk>(`/api/tests/${test.id}/talks`, { method: "POST", json: { persona_ids: personaIds, mode } });
      router.push(`/tests/${test.id}/talks/${talk.id}`);
    } catch (e) {
      toast.error(`${t("talk.createError")} ${errorText(e, t)}`);
      setCreating(false);
    }
  };
  const startSelected = () => (ids.length === 1 ? create(ids, "qa") : ids.length > 1 ? setModal(true) : undefined);

  return (
    <div>
      <SectionHeader
        label={t("vw.label")}
        title={t("vw.title")}
        action={
          test.read_only ? undefined : selecting ? (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPicked(new Set(test.personas.slice(0, MAX_PICK).map((p) => p.id)))}>{t("vw.selectAll")}</Button>
              <Button size="sm" onClick={exitSelect}>{t("vw.doneSelect")}</Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setSelecting(true)}>
              <Check size={14} aria-hidden /> {t("vw.select")}
            </Button>
          )
        }
      />
      {!test.read_only && <PastTalks test={test} personas={byId} />}
      <ul className="mt-6 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {test.personas.map((p, i) => (
          <li key={p.id}>
            <PersonaCard
              persona={p}
              eager={i < 6}
              selecting={selecting}
              selected={picked.has(p.id)}
              onToggle={() => toggle(p.id)}
              onDetails={() => setOpen(p)}
              onTalk={test.read_only ? undefined : () => create([p.id], "qa")}
              badge={<span className="tnum rounded-full bg-ink/80 px-2 py-0.5 text-[11px] text-white">{(avgs.get(p.id) ?? 0).toFixed(1)}</span>}
            />
          </li>
        ))}
      </ul>

      {selecting && (
        <div className="fixed inset-x-0 bottom-0 z-20 flex justify-center bg-ink/10 px-4 py-4 backdrop-blur-sm">
          <div className="flex flex-wrap items-center justify-center gap-2">
            <span className="tnum mr-1 hidden text-sm text-ink sm:inline" aria-live="polite">{t("vw.selectedCount", { n: ids.length })}</span>
            <Button size="lg" disabled={ids.length === 0 || creating} onClick={startSelected}>
              <MessageCircle size={16} aria-hidden /> {t("vw.talkWith", { n: ids.length })}
            </Button>
            <Button size="lg" variant="outline" onClick={exitSelect}>{t("common.cancel")}</Button>
          </div>
        </div>
      )}

      <Dialog open={modal} onClose={() => !creating && setModal(false)} label={t("talk.groupTitle")} wide>
        <div className="flex items-center gap-2 pr-10">
          <span className="grid size-8 place-items-center rounded-full bg-ink text-lime"><Users size={16} aria-hidden /></span>
          <h2 className="text-xl font-bold">{t("talk.groupTitle")}</h2>
        </div>
        <p className="mt-1 text-sm text-mute">{t("talk.groupSub", { n: ids.length })}</p>
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {MODES.map((m) => <ModeCard key={m} mode={m} onChoose={() => create(ids, m)} />)}
        </div>
      </Dialog>

      <ProfileSheet test={test} persona={open} onClose={() => setOpen(null)} onTalk={(p) => { setOpen(null); create([p.id], "qa"); }} />
    </div>
  );
}
