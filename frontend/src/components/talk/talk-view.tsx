"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, ChevronDown, ChevronUp, Play, Settings2, Sparkles, Square, Trash2, Users, X } from "lucide-react";
import { ApiError, api, streamAsk } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Key } from "@/lib/i18n";
import type { Persona, Talk, TalkMessage, TalkMode, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { usePersonaMeta } from "../persona-card";
import { useToast } from "../toast";
import { Avatar, Button, Dialog, cx } from "../ui";
import { MODES } from "../report/talk-modes";

const CHIPS: Key[] = ["talk.chip1", "talk.chip2", "talk.chip3", "talk.chip4", "talk.chip5", "talk.chip6"];
const AUTO_ROUNDS = 5;

type Reply = { kind: "msg"; m: Extract<TalkMessage, { role: "persona" }> } | { kind: "thinking"; id: string };
type Block = { kind: "user"; m: Extract<TalkMessage, { role: "user" }>; key: string } | { kind: "replies"; items: Reply[]; key: string };

function usePersonaLabel() {
  const { t, lang } = useI18n();
  return (p: Persona) => {
    const lo = Math.floor(p.age / 10) * 10;
    const g = t(p.gender === "Female" ? "talk.female" : "talk.male");
    return lang === "ja" ? `${g}${lo}-${lo + 9}歳` : `${g} ${lo}–${lo + 9}`;
  };
}

function Typing({ label }: { label: string }) {
  return (
    <span className="flex gap-1.5 py-2" role="status" aria-label={label}>
      {[0, 1, 2].map((i) => <span key={i} aria-hidden className="dot-bounce size-1.5 rounded-full bg-mute" style={{ animationDelay: `${i * 0.15}s` }} />)}
    </span>
  );
}

function ReplyCard({ p, text, wide }: { p: Persona; text?: string; wide: boolean }) {
  const { t } = useI18n();
  const label = usePersonaLabel()(p);
  return (
    <div className={cx("min-w-0", wide && "max-w-2xl")}>
      <p className="mb-1 pl-1 text-[11px] text-mute">{label} · <span className="font-medium text-ink">{p.name}</span></p>
      <div className="fade-in flex gap-3 rounded-[18px] bg-surface p-3.5">
        <Avatar src={p.avatar_url} name={p.name} color={p.color} rounded="rounded-full" className="size-10 shrink-0" />
        <div className="min-w-0 flex-1 text-[15px] leading-relaxed">
          {text === undefined ? <Typing label={t("talk.thinking", { name: p.name })} /> : <p className="whitespace-pre-wrap">{text}</p>}
        </div>
      </div>
    </div>
  );
}

export function TalkView({ test, talk }: { test: Test; talk: Talk }) {
  const { t } = useI18n();
  const router = useRouter();
  const toast = useToast();
  const meta = usePersonaMeta();
  const base = `/api/tests/${test.id}/talks/${talk.id}`;
  const back = `/tests/${test.id}?tab=viewers`;

  const [mode, setMode] = useState<TalkMode>(talk.mode);
  const [messages, setMessages] = useState<TalkMessage[]>(talk.messages);
  const [thinking, setThinking] = useState<string[]>([]);
  const [suggestion, setSuggestion] = useState<string | null>(talk.suggestion);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [auto, setAuto] = useState(false);
  const [members, setMembers] = useState(false);
  const [settings, setSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const stopAuto = useRef(false);
  const suggestionRef = useRef(suggestion);
  const abort = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const membersWrap = useRef<HTMLDivElement>(null);

  const byId = useMemo(() => new Map(test.personas.map((p) => [p.id, p])), [test.personas]);
  const people = useMemo(() => talk.persona_ids.map((id) => byId.get(id)).filter((p): p is Persona => !!p), [talk.persona_ids, byId]);
  const solo = talk.persona_ids.length === 1 ? people[0] : undefined;

  const setSug = (v: string | null) => { suggestionRef.current = v; setSuggestion(v); };

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Escape closes the talk unless a dialog or the member list is handling it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (document.querySelector("dialog[open]")) return;
      if (members) { setMembers(false); return; }
      router.push(back);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, back, members]);

  useEffect(() => {
    if (!members) return;
    const onDown = (e: MouseEvent) => { if (!membersWrap.current?.contains(e.target as Node)) setMembers(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [members]);

  const scrollToBottom = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, []);

  const pinQuestion = useRef(false);
  useEffect(() => {
    const c = scroller.current;
    if (!c) return;
    if (pinQuestion.current) {
      // keep the newest question at the top while its answers stream in underneath
      const qs = c.querySelectorAll<HTMLElement>("[data-q]");
      const last = qs[qs.length - 1];
      if (last) {
        const y = last.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop - 16;
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        c.scrollTo({ top: Math.max(0, y), behavior: reduce ? "auto" : "smooth" });
      }
      pinQuestion.current = false;
    } else if (nearBottom.current) scrollToBottom();
  }, [messages.length, thinking.length, scrollToBottom]);

  const blocks = useMemo<Block[]>(() => {
    const out: Block[] = [];
    messages.forEach((m, i) => {
      if (m.role === "user") out.push({ kind: "user", m, key: `u${i}` });
      else {
        let last = out[out.length - 1];
        if (!last || last.kind !== "replies") { last = { kind: "replies", items: [], key: `r${i}` }; out.push(last); }
        last.items.push({ kind: "msg", m });
      }
    });
    if (thinking.length) {
      let last = out[out.length - 1];
      if (!last || last.kind !== "replies") { last = { kind: "replies", items: [], key: "rt" }; out.push(last); }
      for (const id of thinking) last.items.push({ kind: "thinking", id });
    }
    return out;
  }, [messages, thinking]);

  /** One round: streams the answers in. Resolves true when the round completed without a transport failure. */
  const ask = useCallback(async (body: { message: string } | { use_suggestion: true }): Promise<boolean> => {
    const typed = "message" in body ? body.message : null;
    let haveUser = false;
    let received = 0;
    const ac = new AbortController();
    abort.current = ac;
    setSending(true);
    setSug(null);
    pinQuestion.current = true;
    nearBottom.current = false;
    if (typed) {
      haveUser = true;
      setMessages((m) => [...m, { role: "user", content: typed, at: new Date().toISOString() }]);
      setDraft("");
    }
    let ok = true;
    try {
      await streamAsk(`${base}/ask`, body, (ev) => {
        switch (ev.event) {
          case "user":
            if (!haveUser) { haveUser = true; setMessages((m) => [...m, { role: "user", content: ev.data.content, at: ev.data.at }]); }
            break;
          case "thinking":
            received++;
            setThinking((x) => (x.includes(ev.data.persona_id) ? x : [...x, ev.data.persona_id]));
            break;
          case "message":
            received++;
            setThinking((x) => x.filter((id) => id !== ev.data.persona_id));
            setMessages((m) => [...m, { role: "persona", persona_id: ev.data.persona_id, content: ev.data.content, at: ev.data.at }]);
            break;
          case "suggestion":
            setSug(ev.data.content || null);
            break;
          case "error":
            toast.error(ev.data.detail || t("talk.askError"));
            break;
        }
      }, ac.signal);
    } catch (e) {
      ok = false;
      if (!(e instanceof DOMException)) {
        if (typed && received === 0) {
          // nothing came back: roll the question out of the thread and give the words back
          setMessages((m) => m.slice(0, -1));
          setDraft(typed);
          toast.error(`${t("talk.sendFailed")} ${e instanceof ApiError ? errorText(e, t) : ""}`);
        } else toast.error(errorText(e, t));
      }
    } finally {
      setThinking([]);
      setSending(false);
    }
    return ok;
  }, [base, t, toast]);

  const submit = (text: string) => {
    const v = text.trim();
    if (v && !sending && !auto) void ask({ message: v });
  };

  const runAuto = async () => {
    stopAuto.current = false;
    setAuto(true);
    for (let i = 0; i < AUTO_ROUNDS; i++) {
      if (stopAuto.current || !suggestionRef.current) break;
      const ok = await ask({ use_suggestion: true });
      if (!ok) break;
    }
    setAuto(false);
  };

  const jump = (dir: 1 | -1) => {
    const c = scroller.current;
    if (!c) return;
    const top0 = c.getBoundingClientRect().top;
    const tops = [...c.querySelectorAll<HTMLElement>("[data-q]")].map((el) => el.getBoundingClientRect().top - top0 + c.scrollTop - 16);
    const target = dir < 0 ? [...tops].reverse().find((y) => y < c.scrollTop - 8) : tops.find((y) => y > c.scrollTop + 8);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (target !== undefined) c.scrollTo({ top: Math.max(0, target), behavior: reduce ? "auto" : "smooth" });
    else c.scrollTo({ top: dir < 0 ? 0 : c.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  };

  const changeMode = async (m: TalkMode) => {
    if (m === mode) return;
    const prev = mode;
    setMode(m);
    try {
      await api<Talk>(base, { method: "PATCH", json: { mode: m } });
      toast.success(t("toast.modeChanged"));
    } catch (e) {
      setMode(prev);
      toast.error(errorText(e, t));
    }
  };

  const remove = async () => {
    try {
      await api(base, { method: "DELETE" });
      toast.success(t("toast.talkDeleted"));
      router.push(back);
    } catch (e) {
      toast.error(errorText(e, t));
      setConfirmDelete(false);
    }
  };

  const empty = messages.length === 0 && thinking.length === 0;
  const busy = sending || auto;
  const title = talk.title || t("talk.untitled");

  const inputCard = (
    <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-end">
      <div className="min-w-0 flex-1 rounded-[22px] bg-surface p-3 focus-within:outline focus-within:outline-2 focus-within:outline-ink">
        <label htmlFor="talk-input" className="sr-only">{t("talk.placeholder")}</label>
        <div className="flex items-end gap-2">
          <textarea
            ref={textarea} id="talk-input" rows={2} value={draft} autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onCompositionStart={() => { composing.current = true; }}
            onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing) { e.preventDefault(); submit(draft); }
            }}
            placeholder={t("talk.placeholder")}
            className="min-h-[52px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] placeholder:text-mute/70 focus-visible:shadow-none focus-visible:outline-none"
          />
          <button
            type="button" onClick={() => submit(draft)} disabled={!draft.trim() || busy} aria-label={t("talk.send")}
            className="grid size-10 shrink-0 place-items-center rounded-full bg-ink text-lime disabled:opacity-30"
          >
            <ArrowUp size={18} aria-hidden />
          </button>
        </div>
        <ul className="mt-2 flex gap-2 overflow-x-auto border-t border-line pb-0.5 pt-2.5 [scrollbar-width:thin]">
          {CHIPS.map((k) => (
            <li key={k} className="shrink-0">
              <button
                type="button" disabled={busy} onClick={() => submit(t(k))}
                className="rounded-full border border-line px-3.5 py-1.5 text-[13px] hover:border-ink disabled:opacity-40"
              >
                {t(k)}
              </button>
            </li>
          ))}
        </ul>
      </div>
      {!empty && <Button
        variant="outline" size="lg" className="shrink-0 self-stretch sm:self-end"
        disabled={auto ? false : busy || !suggestion}
        onClick={() => (auto ? (stopAuto.current = true) : void runAuto())}
        aria-pressed={auto}
      >
        {auto ? <><Square size={14} aria-hidden fill="currentColor" /> {t("talk.stop")}</> : <><Play size={14} aria-hidden /> {t("talk.auto")}</>}
      </Button>}
    </div>
  );

  return (
    <section aria-label={title} className="fixed inset-0 z-50 flex flex-col bg-canvas">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface px-4 sm:px-6">
        <div className="min-w-0">
          {solo ? (
            <div className="flex min-w-0 items-center gap-3">
              <Avatar src={solo.avatar_url} name={solo.name} color={solo.color} rounded="rounded-full" eager className="size-9 shrink-0" />
              <div className="min-w-0 leading-tight">
                <p className="truncate text-[11px] text-mute">{meta(solo)}</p>
                <p className="truncate text-sm font-bold">{solo.name}</p>
              </div>
            </div>
          ) : (
            <div ref={membersWrap} className="relative">
              <button
                type="button" aria-expanded={members} onClick={() => setMembers((m) => !m)}
                className="flex items-center gap-2.5 rounded-full py-1 pl-1 pr-3 hover:bg-canvas"
              >
                <span className="grid size-9 place-items-center rounded-full bg-ink text-lime"><Users size={16} aria-hidden /></span>
                <span className="text-sm font-bold">{t("talk.viewersN", { n: people.length })}</span>
                <ChevronDown size={14} aria-hidden className={cx("text-mute transition-transform", members && "rotate-180")} />
              </button>
              {members && (
                <div className="absolute left-0 top-12 z-10 max-h-[60vh] w-72 overflow-y-auto rounded-card border border-line bg-surface p-2">
                  <p className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("talk.members")}</p>
                  <ul>
                    {people.map((p) => (
                      <li key={p.id} className="flex items-center gap-3 rounded-xl px-3 py-2">
                        <Avatar src={p.avatar_url} name={p.name} color={p.color} rounded="rounded-full" className="size-9 shrink-0" />
                        <div className="min-w-0 leading-tight">
                          <p className="truncate text-sm font-bold">{p.name}</p>
                          <p className="truncate text-[11px] text-mute">{meta(p)}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setSettings(true)}>
            <Settings2 size={14} aria-hidden /> <span className="hidden sm:inline">{t("talk.settings")}</span>
            <span className="sr-only sm:hidden">{t("talk.settings")}</span>
          </Button>
          <button
            type="button" onClick={() => router.push(back)} aria-label={t("talk.close")}
            className="grid size-9 place-items-center rounded-full hover:bg-canvas"
          >
            <X size={18} aria-hidden />
          </button>
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scroller}
          onScroll={(e) => { const el = e.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 160; }}
          className="h-full overflow-y-auto overscroll-contain px-4 sm:px-6"
        >
          <div className={cx("mx-auto flex min-h-full w-full max-w-4xl flex-col", empty ? "justify-center" : "justify-start py-6")}>
            {empty ? (
              <h1 className="mb-6 text-center text-2xl font-bold sm:text-3xl">{t("talk.empty")}</h1>
            ) : (
              <div role="log" aria-label={t("talk.log")} aria-live="polite" className="space-y-5">
                {blocks.map((b) =>
                  b.kind === "user" ? (
                    <div key={b.key} data-q className="flex justify-end">
                      <p className="max-w-[82%] whitespace-pre-wrap rounded-[20px] bg-[#e4e4e8] px-4 py-2.5 text-[15px]">{b.m.content}</p>
                    </div>
                  ) : (
                    <div key={b.key} className={cx(mode === "qa" ? "grid grid-cols-1 gap-3 md:grid-cols-2" : "flex flex-col gap-3")}>
                      {b.items.map((r) => {
                        const id = r.kind === "msg" ? r.m.persona_id : r.id;
                        const p = byId.get(id);
                        if (!p) return null;
                        return <ReplyCard key={r.kind === "msg" ? `${id}-${r.m.at}` : `t-${id}`} p={p} text={r.kind === "msg" ? r.m.content : undefined} wide={mode === "conversation"} />;
                      })}
                    </div>
                  ),
                )}
                {sending && thinking.length === 0 && (
                  <div className="fade-in flex w-fit items-center gap-3 rounded-[18px] bg-surface px-4 py-2">
                    <Users size={16} aria-hidden className="text-mute" />
                    <Typing label={t("talk.waiting")} />
                  </div>
                )}
              </div>
            )}
            {empty && <div className="mx-auto w-full max-w-3xl">{inputCard}</div>}
          </div>
        </div>
        {!empty && blocks.filter((b) => b.kind === "user").length > 1 && (
          <div className="absolute bottom-3 right-3 flex flex-col gap-1.5 sm:right-5">
            <button type="button" onClick={() => jump(-1)} aria-label={t("talk.jumpUp")} className="grid size-9 place-items-center rounded-full border border-line bg-surface hover:border-ink"><ChevronUp size={16} aria-hidden /></button>
            <button type="button" onClick={() => jump(1)} aria-label={t("talk.jumpDown")} className="grid size-9 place-items-center rounded-full border border-line bg-surface hover:border-ink"><ChevronDown size={16} aria-hidden /></button>
          </div>
        )}
      </div>

      {!empty && (
        <footer className="shrink-0 px-4 pb-4 pt-2 sm:px-6">
          <div className="mx-auto w-full max-w-4xl">
            {suggestion && !busy && (
              <button
                type="button" onClick={() => submit(suggestion)} aria-label={t("talk.suggestion", { q: suggestion })}
                className="mb-2 inline-flex max-w-full items-center gap-2 rounded-full border border-dashed border-ink/30 px-3.5 py-1.5 text-[13px] text-mute hover:border-ink hover:text-ink"
              >
                <Sparkles size={14} aria-hidden className="shrink-0" /> <span className="truncate">{suggestion}</span>
              </button>
            )}
            {inputCard}
          </div>
        </footer>
      )}

      <Dialog open={settings} onClose={() => setSettings(false)} label={t("talk.settings")}>
        <h2 className="pr-8 text-lg font-bold">{t("talk.settings")}</h2>
        {!solo && (
          <fieldset className="mt-5">
            <legend className="text-sm font-medium">{t("talk.mode")}</legend>
            <div className="mt-2 space-y-2">
              {MODES.map((m) => (
                <label key={m} className={cx("block cursor-pointer rounded-xl border p-3", mode === m ? "border-ink" : "border-line")}>
                  <input type="radio" name="talk-mode" className="sr-only" checked={mode === m} onChange={() => void changeMode(m)} />
                  <span className="block text-sm font-bold">{m === "conversation" ? t("talk.modeConv") : t("talk.modeQa")}</span>
                  <span className="block text-xs text-mute">{m === "conversation" ? t("talk.modeConvDesc") : t("talk.modeQaDesc")}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <Button variant="outline" className="mt-5 w-full" onClick={() => { setSettings(false); setConfirmDelete(true); }}>
          <Trash2 size={14} aria-hidden /> {t("talk.delete")}
        </Button>
      </Dialog>

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} label={t("talk.delete")}>
        <h2 className="pr-8 text-lg font-bold">{t("talk.delete")}</h2>
        <p className="mt-2 text-sm text-mute">{t("talk.deleteBody")}</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setConfirmDelete(false)}>{t("common.cancel")}</Button>
          <Button onClick={remove}>{t("common.delete")}</Button>
        </div>
      </Dialog>
    </section>
  );
}
