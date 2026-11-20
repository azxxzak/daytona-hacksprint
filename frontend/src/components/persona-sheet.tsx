"use client";

import dynamic from "next/dynamic";
import remarkGfm from "remark-gfm";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, FileText, Loader2, MessageCircle } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Key } from "@/lib/i18n";
import type { Persona, Profile } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { usePersonaMeta } from "./persona-card";
import { LongProgress } from "./long-progress";
import { useToast } from "./toast";
import { Avatar, Button, Dialog, cx } from "./ui";

const Markdown = dynamic(() => import("react-markdown"), { loading: () => <p className="pulse text-sm text-mute">…</p> });

function Chips({ items, tone }: { items: string[]; tone?: "dark" }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((x) => (
        <li key={x} className={cx("rounded-full px-2.5 py-0.5 text-xs", tone === "dark" ? "bg-ink text-white" : "bg-canvas")}>{x}</li>
      ))}
    </ul>
  );
}

function H({ children }: { children: ReactNode }) {
  return <h3 className="mt-8 border-b-2 border-ink pb-2 text-sm font-bold">{children}</h3>;
}

const BIG5: { k: keyof Profile["big_five"]; label: Key }[] = [
  { k: "openness", label: "pf.o" },
  { k: "conscientiousness", label: "pf.c" },
  { k: "extraversion", label: "pf.e" },
  { k: "agreeableness", label: "pf.a" },
  { k: "neuroticism", label: "pf.n" },
];

function ProfileBody({ profile }: { profile: Profile }) {
  const { t } = useI18n();
  const basics: [Key, string][] = [["pf.household", profile.household], ["pf.income", profile.income], ["pf.region", profile.region]];
  return (
    <div>
      <H>{t("pf.basic")}</H>
      <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        {basics.map(([k, v]) => v ? <div key={k}><dt className="text-xs text-mute">{t(k)}</dt><dd>{v}</dd></div> : null)}
      </dl>
      {profile.daily_life && (<><H>{t("pf.daily")}</H><p className="mt-3 text-sm leading-relaxed">{profile.daily_life}</p></>)}
      {profile.media?.length > 0 && (<><H>{t("pf.media")}</H><ul className="mt-3 space-y-1.5 text-sm">{profile.media.map((m) => <li key={m} className="flex gap-2"><span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-ink" />{m}</li>)}</ul></>)}
      {profile.ad_attitude && (<><H>{t("pf.ads")}</H><p className="mt-3 text-sm leading-relaxed">{profile.ad_attitude}</p></>)}
      <H>{`${t("pf.drivers")} / ${t("pf.barriers")}`}</H>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div><p className="mb-1.5 text-xs text-mute">{t("pf.drivers")}</p><Chips items={profile.purchase_drivers ?? []} tone="dark" /></div>
        <div><p className="mb-1.5 text-xs text-mute">{t("pf.barriers")}</p><Chips items={profile.purchase_barriers ?? []} /></div>
      </div>
      <H>{t("pf.values")}</H>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div><p className="mb-1.5 text-xs text-mute">{t("pf.valuesTop")}</p><Chips items={profile.values_top ?? []} tone="dark" /></div>
        <div><p className="mb-1.5 text-xs text-mute">{t("pf.valuesLow")}</p><Chips items={profile.values_low ?? []} /></div>
      </div>
      {profile.big_five && (
        <>
          <H>{t("pf.bigFive")}</H>
          <ul className="mt-3 space-y-2.5">
            {BIG5.map(({ k, label }) => {
              const v = Math.max(0, Math.min(100, profile.big_five[k] ?? 0));
              return (
                <li key={k} className="grid grid-cols-[6.5rem_1fr_2rem] items-center gap-3 text-xs">
                  <span className="truncate text-mute">{t(label)}</span>
                  <div className="h-1 rounded-full bg-line" role="img" aria-label={`${t(label)} ${v}`}>
                    <div className="h-full rounded-full bg-lime" style={{ width: `${v}%` }} />
                  </div>
                  <span className="tnum text-right">{v}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {profile.speech_style && (<><H>{t("pf.speech")}</H><p className="mt-3 text-sm leading-relaxed">{profile.speech_style}</p></>)}
      {profile.insights?.length > 0 && (
        <>
          <H>{t("pf.insights")}</H>
          <ul className="mt-3 space-y-3">
            {profile.insights.map((i) => (
              <li key={i.title} className="rounded-card bg-canvas p-4">
                <p className="text-sm font-bold">{i.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink/80">{i.body}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function CompactProfile({ persona }: { persona: Persona }) {
  const { t } = useI18n();
  const rows: [Key, string][] = [["vw.region", persona.region], ["vw.occupation", persona.occupation], ["vw.income", persona.income]];
  const chips: [Key, string][] = [["vw.interests", persona.interests], ["vw.media", persona.media], ["vw.values", persona.values]];
  return (
    <div>
      <H>{t("vw.profile")}</H>
      <dl className="mt-3 space-y-3 text-sm">
        {rows.map(([k, v]) => v ? <div key={k}><dt className="text-xs text-mute">{t(k)}</dt><dd>{v}</dd></div> : null)}
        {chips.map(([k, v]) => v ? <div key={k}><dt className="text-xs text-mute">{t(k)}</dt><dd className="mt-1.5"><Chips items={v.split(",").map((x) => x.trim()).filter(Boolean)} /></dd></div> : null)}
      </dl>
    </div>
  );
}

const slug = (s: string) => s.trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "");

function DeepView({ markdown, onBack }: { markdown: string; onBack: () => void }) {
  const { t } = useI18n();
  const wrap = useRef<HTMLDivElement>(null);
  const toc = useMemo(() => {
    const lv3 = [...markdown.matchAll(/^###\s+(.+)$/gm)].map((m) => m[1].replace(/[*_`]/g, "").trim());
    if (lv3.length) return lv3;
    return [...markdown.matchAll(/^##\s+(.+)$/gm)].map((m) => m[1].replace(/[*_`]/g, "").trim());
  }, [markdown]);
  const text = (c: ReactNode): string => (Array.isArray(c) ? c.map(text).join("") : typeof c === "string" ? c : "");
  const go = (h: string) => wrap.current?.querySelector(`#${CSS.escape(`h-${slug(h)}`)}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  return (
    <div>
      <button type="button" onClick={onBack} className="mb-4 inline-flex items-center gap-1.5 text-sm text-mute hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> {t("pf.back")}
      </button>
      {toc.length > 0 && (
        <nav aria-label={t("pf.toc")} className="sticky top-0 z-10 -mx-1 mb-4 overflow-x-auto bg-surface px-1 py-2">
          <ul className="flex gap-1.5">
            {toc.map((h) => (
              <li key={h} className="shrink-0">
                <button type="button" onClick={() => go(h)} className="rounded-full border border-line px-3 py-1 text-xs hover:border-ink">{h}</button>
              </li>
            ))}
          </ul>
        </nav>
      )}
      <div ref={wrap} className="max-w-[68ch] text-[15px] leading-[1.85]">
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => <h2 id={`h-${slug(text(children))}`} className="mt-8 scroll-mt-14 text-2xl font-bold">{children}</h2>,
            h2: ({ children }) => <h2 id={`h-${slug(text(children))}`} className="mt-8 scroll-mt-14 border-b-2 border-ink pb-2 text-xl font-bold">{children}</h2>,
            h3: ({ children }) => <h3 id={`h-${slug(text(children))}`} className="mt-8 scroll-mt-14 text-lg font-bold">{children}</h3>,
            h4: ({ children }) => <h4 className="mt-5 text-[15px] font-bold">{children}</h4>,
            p: ({ children }) => <p className="mt-3">{children}</p>,
            ul: ({ children }) => <ul className="mt-3 list-disc space-y-1.5 pl-5 marker:text-mute">{children}</ul>,
            ol: ({ children }) => <ol className="mt-3 list-decimal space-y-1.5 pl-5 marker:text-mute">{children}</ol>,
            strong: ({ children }) => <strong className="font-bold">{children}</strong>,
            blockquote: ({ children }) => <blockquote className="mt-3 border-l-2 border-ink pl-4 text-ink/80">{children}</blockquote>,
            table: ({ children }) => <div className="mt-3 overflow-x-auto"><table className="w-full border-collapse text-sm leading-snug">{children}</table></div>,
            thead: ({ children }) => <thead className="border-b-2 border-ink text-left text-xs text-mute">{children}</thead>,
            th: ({ children }) => <th className="px-3 py-2 font-medium">{children}</th>,
            td: ({ children }) => <td className="border-b border-line px-3 py-2 align-top">{children}</td>,
            hr: () => <hr className="my-6 border-line" />,
          }}
        >
          {markdown}
        </Markdown>
      </div>
    </div>
  );
}

type Deep = { markdown: string | null; status: "none" | "generating" | "ready" };

/** Right-hand sheet: tier-1 profile page, plus on-demand deep profile. */
export function PersonaSheet({
  persona, pid, onClose, actionLabel, onAction, children,
}: {
  persona: Persona | null; pid: string | null; onClose: () => void; actionLabel: string; onAction: (p: Persona) => void; children?: ReactNode;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const meta = usePersonaMeta();
  const [deep, setDeep] = useState<Deep | null>(null);
  const [view, setView] = useState<"summary" | "deep">("summary");
  const [requested, setRequested] = useState<string | null>(null);
  const posting = useRef(false);
  const [since, setSince] = useState(0);

  const open = !!persona && !!pid;
  const fetchDeep = useCallback(async (id: string) => {
    try { return await api<Deep>(`/api/personas/${encodeURIComponent(id)}/deep`); } catch { return null; }
  }, []);

  // load status when a sheet opens; poll every 3 s while generating
  useEffect(() => {
    if (!pid) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const d = await fetchDeep(pid);
      if (stop) return;
      if (d && !(d.status === "none" && posting.current)) setDeep(d);
      if (!d || d.status === "generating") timer = setTimeout(tick, 3000);
    };
    void tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [pid, fetchDeep, requested]);

  const generate = () => {
    if (!pid) return;
    // POST can hold for up to ~2 min: show progress immediately, poll GET in parallel
    posting.current = true;
    setSince(Date.now());
    setDeep({ markdown: null, status: "generating" });
    setRequested(`${pid}:${Date.now()}`);
    api(`/api/personas/${encodeURIComponent(pid)}/deep`, { method: "POST" })
      .catch((e) => {
        setDeep({ markdown: null, status: "none" });
        toast.error(`${t("pf.deepError")} ${errorText(e, t)}`);
      })
      .finally(() => {
        posting.current = false;
        setRequested(`${pid}:${Date.now()}`);
      });
  };

  const shown = deep && pid ? deep : null;
  const p = persona?.profile;
  const closeAll = () => { setView("summary"); setDeep(null); onClose(); };

  return (
    <Dialog open={open} onClose={closeAll} label={p?.full_name ?? persona?.name ?? ""} side xl={view === "deep"}>
      {persona && (
        view === "deep" && shown?.markdown ? (
          <DeepView markdown={shown.markdown} onBack={() => setView("summary")} />
        ) : (
          <div>
            <div className="flex items-center gap-4 pr-10">
              <Avatar src={persona.avatar_url} name={persona.name} color={persona.color} rounded="rounded-full" eager className="size-20 shrink-0" />
              <div className="min-w-0">
                <h2 className="text-xl font-bold leading-tight">{p?.full_name || persona.name}</h2>
                <p className="mt-0.5 text-sm text-mute">{p?.meta || meta(persona)}</p>
                {p?.headline && <p className="mt-1 text-sm font-bold">{p.headline}</p>}
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button className="flex-1" onClick={() => onAction(persona)}><MessageCircle size={16} aria-hidden /> {actionLabel}</Button>
              {p && (
                shown?.status === "ready" && shown.markdown ? (
                  <Button variant="outline" className="flex-1" onClick={() => setView("deep")}><FileText size={16} aria-hidden /> {t("pf.deepTitle")}</Button>
                ) : shown?.status === "generating" ? (
                  <Button variant="outline" className="flex-1" disabled><Loader2 size={16} className="motion-safe:animate-spin" aria-hidden /> {t("pf.generate")}</Button>
                ) : (
                  <Button variant="outline" className="flex-1" onClick={generate}><FileText size={16} aria-hidden /> {t("pf.generate")}</Button>
                )
              )}
            </div>
            {shown?.status === "generating" && <div className="mt-4 rounded-xl bg-canvas p-4"><LongProgress since={since} estimateSec={80} label={t("pf.generating")} /></div>}
            {p ? <ProfileBody profile={p} /> : <CompactProfile persona={persona} />}
            {children}
          </div>
        )
      )}
    </Dialog>
  );
}
