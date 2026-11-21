"use client";

import dynamic from "next/dynamic";
import remarkGfm from "remark-gfm";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, FileText, Loader2, MessageCircle, Minus, Plus, Sparkles } from "lucide-react";
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

function H({ children, first }: { children: ReactNode; first?: boolean }) {
  return <h3 className={cx("text-[11px] font-semibold uppercase tracking-[0.14em] text-mute", first ? "mt-0" : "mt-9")}>{children}</h3>;
}

/** Long-form list (drivers, barriers, values): one item per row with a small marker, text wraps freely. */
function Points({ items, tone }: { items: string[]; tone: "plus" | "minus" | "num" }) {
  if (!items.length) return null;
  return (
    <ul className="mt-3 space-y-2">
      {items.map((x, i) => (
        <li key={`${i}-${x}`} className="grid grid-cols-[1.5rem_1fr] gap-2.5 text-sm leading-relaxed">
          <span
            aria-hidden
            className={cx(
              "tnum mt-0.5 grid size-5 place-items-center rounded-full text-[11px] font-bold",
              tone === "plus" ? "bg-lime text-ink" : tone === "minus" ? "bg-ink/[0.07] text-ink/60" : "bg-ink text-white",
            )}
          >
            {tone === "plus" ? <Plus size={11} strokeWidth={3} /> : tone === "minus" ? <Minus size={11} strokeWidth={3} /> : i + 1}
          </span>
          <span>{x}</span>
        </li>
      ))}
    </ul>
  );
}

function Pane({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-card border border-line bg-surface p-4">
      <p className="text-xs font-semibold">{title}</p>
      {children}
    </div>
  );
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
    <div className="mt-8">
      <H first>{t("pf.basic")}</H>
      <dl className="mt-3 divide-y divide-line rounded-card bg-canvas px-4">
        {basics.map(([k, v]) => v ? (
          <div key={k} className="grid grid-cols-1 gap-0.5 py-3 sm:grid-cols-[6.5rem_1fr] sm:gap-4">
            <dt className="text-xs font-medium text-mute sm:pt-px">{t(k)}</dt>
            <dd className="text-sm leading-relaxed">{v}</dd>
          </div>
        ) : null)}
      </dl>

      {profile.daily_life && (<><H>{t("pf.daily")}</H><p className="mt-3 text-[15px] leading-[1.8]">{profile.daily_life}</p></>)}

      {profile.ad_attitude && (
        <>
          <H>{t("pf.ads")}</H>
          <p className="mt-3 rounded-card border-l-[3px] border-ink bg-canvas px-4 py-3 text-sm leading-relaxed">{profile.ad_attitude}</p>
        </>
      )}

      {profile.media?.length > 0 && (
        <>
          <H>{t("pf.media")}</H>
          <ul className="mt-3 divide-y divide-line rounded-card border border-line">
            {profile.media.map((m) => {
              const i = m.search(/[:：]/);
              const name = i > 0 && i < 32 ? m.slice(0, i).trim() : "";
              const how = name ? m.slice(i + 1).trim() : m;
              return (
                <li key={m} className="grid grid-cols-1 gap-0.5 px-4 py-3 text-sm sm:grid-cols-[8.5rem_1fr] sm:gap-4">
                  {name && <span className="font-semibold">{name}</span>}
                  <span className={cx("leading-relaxed", name && "text-ink/80")}>{how}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <H>{`${t("pf.drivers")} / ${t("pf.barriers")}`}</H>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Pane title={t("pf.drivers")}><Points items={profile.purchase_drivers ?? []} tone="plus" /></Pane>
        <Pane title={t("pf.barriers")}><Points items={profile.purchase_barriers ?? []} tone="minus" /></Pane>
      </div>

      <H>{t("pf.values")}</H>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Pane title={t("pf.valuesTop")}><Points items={profile.values_top ?? []} tone="num" /></Pane>
        <Pane title={t("pf.valuesLow")}><Points items={profile.values_low ?? []} tone="minus" /></Pane>
      </div>

      {profile.big_five && (
        <>
          <H>{t("pf.bigFive")}</H>
          <ul className="mt-3 space-y-3">
            {BIG5.map(({ k, label }) => {
              const v = Math.max(0, Math.min(100, profile.big_five[k] ?? 0));
              return (
                <li key={k} className="grid grid-cols-[8.5rem_1fr_2rem] items-center gap-3 text-xs">
                  <span className="truncate text-ink/80">{t(label)}</span>
                  <div className="h-1.5 rounded-full bg-canvas" role="img" aria-label={`${t(label)} ${v}`}>
                    <div className="h-full rounded-full bg-ink" style={{ width: `${v}%` }} />
                  </div>
                  <span className="tnum text-right font-semibold">{v}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}

      {profile.speech_style && (
        <>
          <H>{t("pf.speech")}</H>
          <p className="mt-3 text-sm leading-relaxed text-ink/85">{profile.speech_style}</p>
        </>
      )}

      {profile.insights?.length > 0 && (
        <>
          <H>{t("pf.insights")}</H>
          <ol className="mt-3 space-y-2">
            {profile.insights.map((i, n) => (
              <li key={i.title} className="grid grid-cols-[1.5rem_1fr] gap-2.5 rounded-card bg-canvas p-4">
                <span aria-hidden className="tnum mt-0.5 grid size-5 place-items-center rounded-full bg-ink text-[11px] font-bold text-lime">{n + 1}</span>
                <div>
                  <p className="text-sm font-bold leading-snug">{i.title}</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink/80">{i.body}</p>
                </div>
              </li>
            ))}
          </ol>
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
  persona: Persona | null; pid: string | null; onClose: () => void; actionLabel?: string; onAction?: (p: Persona) => void; children?: ReactNode;
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
            <header className="flex flex-col gap-4 pr-10 sm:flex-row sm:items-center sm:gap-5">
              <Avatar src={persona.avatar_url} name={persona.name} color={persona.color} rounded="rounded-2xl" eager className="size-24 shrink-0 sm:size-28" />
              <div className="min-w-0">
                <h2 className="text-2xl font-bold leading-tight tracking-tight">{p?.full_name || persona.name}</h2>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {(p?.meta || meta(persona)).split(/\s*\/\s*/).filter(Boolean).map((m) => (
                    <li key={m} className="rounded-md bg-canvas px-2 py-0.5 text-xs text-ink/75">{m}</li>
                  ))}
                </ul>
                {p?.headline && <p className="mt-3 text-[15px] font-semibold leading-snug">{p.headline}</p>}
              </div>
            </header>
            {actionLabel && onAction && (
              <div className="mt-5">
                <Button className="w-full" onClick={() => onAction(persona)}><MessageCircle size={16} aria-hidden /> {actionLabel}</Button>
              </div>
            )}
            {p && (
              <section aria-label={t("pf.deepTitle")} className="mt-4 rounded-card bg-ink p-4 text-white">
                {shown?.status === "ready" && shown.markdown ? (
                  <button type="button" onClick={() => setView("deep")} className="flex w-full items-center gap-3 text-left">
                    <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-lime text-ink"><FileText size={16} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-bold">{t("pf.deepTitle")}</span>
                      <span className="block text-xs text-white/65">{t("pf.deepReady")}</span>
                    </span>
                    <ArrowRight size={16} aria-hidden />
                  </button>
                ) : (
                  <div className="flex flex-wrap items-center gap-3">
                    <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-lime text-ink"><Sparkles size={16} /></span>
                    <div className="min-w-[12rem] flex-1">
                      <p className="text-sm font-bold">{t("pf.deepTitle")}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-white/65">{t("pf.deepDesc")}</p>
                    </div>
                    <button
                      type="button" onClick={generate} disabled={shown?.status === "generating"}
                      className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-white px-4 text-sm font-semibold text-ink transition-colors hover:bg-lime disabled:opacity-60"
                    >
                      {shown?.status === "generating" ? <Loader2 size={15} className="motion-safe:animate-spin" aria-hidden /> : null}
                      {shown?.status === "generating" ? t("pf.generatingShort") : t("pf.generate")}
                    </button>
                  </div>
                )}
                {shown?.status === "generating" && <div className="mt-4 rounded-xl bg-white/10 p-3 [&_*]:!text-white"><LongProgress since={since} estimateSec={80} label={t("pf.generating")} /></div>}
              </section>
            )}
            {p ? <ProfileBody profile={p} /> : <CompactProfile persona={persona} />}
            {children}
          </div>
        )
      )}
    </Dialog>
  );
}
