"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Key } from "@/lib/i18n";
import type { Message, Persona, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { usePersonaMeta } from "../persona-card";
import { Avatar, Card, ErrorNote, cx } from "../ui";

const SUGGESTIONS: Key[] = ["iv.s1", "iv.s2", "iv.s3", "iv.s4"];

function InputCard({ persona, value, onChange, onSend, busy, showChips }: {
  persona: Persona; value: string; onChange: (v: string) => void; onSend: (text: string) => void; busy: boolean; showChips: boolean;
}) {
  const { t } = useI18n();
  const id = useId();
  const ref = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const submit = () => { if (value.trim() && !busy) onSend(value.trim()); };
  return (
    <Card className="p-3 focus-within:outline focus-within:outline-2 focus-within:outline-ink sm:p-4">
      <label htmlFor={id} className="sr-only">{t("iv.placeholder", { name: persona.name })}</label>
      <div className="flex items-end gap-2">
        <textarea
          ref={ref} id={id} rows={2} value={value}
          onChange={(e) => onChange(e.target.value)}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter is a newline; never send while an IME is composing Japanese
            if (e.key === "Enter" && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
          }}
          placeholder={t("iv.placeholder", { name: persona.name })}
          className="min-h-[56px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] placeholder:text-mute/70 focus-visible:shadow-none focus-visible:outline-none"
        />
        <button
          type="button" onClick={submit} disabled={!value.trim() || busy} aria-label={t("iv.send")}
          className="grid size-10 shrink-0 place-items-center rounded-full bg-ink text-lime disabled:opacity-30"
        >
          <ArrowUp size={18} aria-hidden />
        </button>
      </div>
      {showChips && (
        <ul className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
          {SUGGESTIONS.map((k) => (
            <li key={k}>
              <button
                type="button" onClick={() => { onChange(t(k)); ref.current?.focus(); }}
                className="rounded-full border border-line px-3.5 py-1.5 text-[13px] hover:border-ink"
              >
                {t(k)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Interview({ test, persona, onSelect }: { test: Test; persona: Persona; onSelect: (p: Persona) => void }) {
  const { t } = useI18n();
  const meta = usePersonaMeta();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const base = `/api/tests/${test.id}/interviews/${persona.id}`;

  useEffect(() => {
    let cancelled = false;
        api<{ messages: Message[] }>(base)
      .then((d) => { if (!cancelled) { setMessages(d.messages); setLoaded(true); } })
      .catch((e) => { if (!cancelled) { setLoadError(errorText(e, t)); setLoaded(true); } });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the viewer changes
  }, [base]);

  const scrollNext = useRef(false);
  useEffect(() => {
    if (!scrollNext.current) return;
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    if (!busy) scrollNext.current = false;
  }, [messages.length, busy]);

  const send = async (text: string) => {
    setBusy(true); setSendError(null);
    scrollNext.current = true;
    const before = messages;
    setMessages([...before, { role: "user", content: text }]); // optimistic
    setDraft("");
    try {
      const r = await api<{ reply: string; messages: Message[] }>(base, { method: "POST", json: { message: text } });
      setMessages(r.messages?.length ? r.messages : [...before, { role: "user", content: text }, { role: "assistant", content: r.reply }]);
    } catch (e) {
      setMessages(before); // rollback, keep the words so the user can resend
      setDraft(text);
      setSendError(`${t("iv.sendError")} ${errorText(e, t)}`);
    } finally {
      setBusy(false);
    }
  };

  const empty = loaded && !loadError && messages.length === 0 && !busy;

  return (
    <div className="mx-auto max-w-3xl">
      <header className="flex flex-wrap items-center gap-4 border-b-2 border-ink pb-4">
        <Avatar src={persona.avatar_url} name={persona.name} color={persona.color} rounded="rounded-full" eager className="size-14 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("iv.label")}</p>
          <h2 className="truncate text-xl font-bold leading-tight">{persona.name}</h2>
          <p className="truncate text-xs text-mute">{meta(persona)}{persona.region ? ` · ${persona.region}` : ""}</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-mute">
          {t("iv.switch")}
          <select
            value={persona.id} onChange={(e) => { const p = test.personas.find((x) => x.id === e.target.value); if (p) onSelect(p); }}
            className="h-9 max-w-[180px] rounded-full border border-line bg-surface px-3 text-sm text-ink"
          >
            {test.personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      </header>

      {loadError && <div className="mt-6"><ErrorNote>{t("iv.loadError")} {loadError}</ErrorNote></div>}

      {!loaded && <p className="pulse py-24 text-center text-sm text-mute" role="status">{t("common.loading")}</p>}

      {empty && (
        <div className="py-12 text-center sm:py-20">
          <h3 className="text-2xl font-bold">{t("iv.startTitle")}</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-mute">{t("iv.startBody", { name: persona.name })}</p>
          <div className="mx-auto mt-8 max-w-2xl text-left">
            <InputCard persona={persona} value={draft} onChange={setDraft} onSend={send} busy={busy} showChips />
          </div>
        </div>
      )}

      {loaded && !empty && (
        <>
          <div role="log" aria-label={t("iv.log")} aria-live="polite" className="space-y-4 py-6">
            {messages.map((m, i) => (
              <div key={i} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start gap-3")}>
                {m.role === "assistant" && <Avatar src={persona.avatar_url} name={persona.name} rounded="rounded-full" className="mt-1 size-8 shrink-0" />}
                <p className={cx("max-w-[82%] whitespace-pre-wrap rounded-[18px] px-4 py-2.5 text-[15px] leading-relaxed",
                  m.role === "user" ? "rounded-br-md bg-ink text-white" : "rounded-bl-md bg-surface")}>
                  <span className="sr-only">{m.role === "user" ? t("iv.you") : persona.name}: </span>{m.content}
                </p>
              </div>
            ))}
            {busy && (
              <div className="flex items-center gap-3" role="status" aria-label={t("iv.typing", { name: persona.name })}>
                <Avatar src={persona.avatar_url} name={persona.name} rounded="rounded-full" className="size-8 shrink-0" />
                <div className="flex gap-1.5 rounded-[18px] rounded-bl-md bg-surface px-4 py-3.5" aria-hidden>
                  {[0, 1, 2].map((i) => <span key={i} className="dot-bounce size-1.5 rounded-full bg-mute" style={{ animationDelay: `${i * 0.15}s` }} />)}
                </div>
              </div>
            )}
            <div ref={endRef} className="scroll-mb-40" />
          </div>
          {sendError && <div className="mb-3"><ErrorNote>{sendError}</ErrorNote></div>}
          <div className="sticky bottom-4">
            <InputCard persona={persona} value={draft} onChange={setDraft} onSend={send} busy={busy} showChips={false} />
          </div>
        </>
      )}
      {empty && sendError && <div className="mx-auto mt-3 max-w-2xl"><ErrorNote>{sendError}</ErrorNote></div>}
    </div>
  );
}
