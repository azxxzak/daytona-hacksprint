"use client";

import type { ReactNode } from "react";
import { Check, Info, MessageCircle } from "lucide-react";
import type { Persona } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { Avatar, Button, cx } from "./ui";

export function usePersonaMeta() {
  const { t, lang } = useI18n();
  return (p: Persona) => {
    const decade = Math.floor(p.age / 10) * 10;
    const parts = [t("age.decade", { n: decade }), t(`gender.${p.gender}` as "gender.Female"), p.occupation].filter(Boolean);
    return parts.join(lang === "ja" ? "/" : " / ");
  };
}

/** Portrait on top (slightly taller than square), tiny meta line, bold short title. */
export function PersonaCard({
  persona,
  title,
  meta: metaOverride,
  badge,
  onDetails,
  onTalk,
  actionLabel,
  selecting,
  selected,
  onToggle,
  eager,
}: {
  persona: Persona;
  title?: string;
  meta?: string;
  badge?: ReactNode;
  onDetails?: () => void;
  onTalk?: () => void;
  actionLabel?: string;
  selecting?: boolean;
  selected?: boolean;
  onToggle?: () => void;
  eager?: boolean;
}) {
  const { t } = useI18n();
  const computedMeta = usePersonaMeta()(persona);
  const meta = metaOverride ?? computedMeta;
  const interactive = !selecting && !!(onDetails || onTalk);

  return (
    <div className="group min-w-0">
      <div className="relative overflow-hidden rounded-card bg-surface shadow-card">
        <Avatar
          src={persona.avatar_url}
          name={persona.name}
          color={persona.color}
          eager={eager}
          className={cx("aspect-[4/5] w-full", interactive && "transition duration-300 group-hover:scale-[1.03] group-hover:blur-[3px] group-hover:brightness-75 group-focus-within:blur-[3px] group-focus-within:brightness-75 motion-reduce:transition-none")}
        />
        {badge && <div className="absolute bottom-2 left-2">{badge}</div>}
        {selecting && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={!!selected}
            aria-label={t("vw.selectToggle", { name: persona.name })}
            className={cx("absolute inset-0 rounded-card", selected && "ring-2 ring-inset ring-ink")}
          >
            <span
              aria-hidden
              className={cx(
                "absolute right-2.5 top-2.5 grid size-7 place-items-center rounded-full border-2 transition-colors",
                selected ? "border-ink bg-lime text-ink" : "border-white bg-black/10 text-transparent",
              )}
            >
              <Check size={15} strokeWidth={3} />
            </span>
          </button>
        )}
        {selecting && onDetails && (
          <button
            type="button" onClick={onDetails} aria-label={`${t("vw.details")}: ${persona.name}`}
            className="absolute bottom-2 left-2 inline-flex h-7 items-center gap-1 rounded-full bg-ink/80 px-2.5 text-[11px] font-medium text-white backdrop-blur hover:bg-ink"
          >
            <Info size={12} aria-hidden /> {t("vw.details")}
          </button>
        )}
        {!selecting && onDetails && (
          <button
            type="button"
            onClick={onDetails}
            aria-label={t("vw.openAria", { name: persona.name })}
            className="absolute inset-0 [@media(hover:hover)]:pointer-events-none"
            tabIndex={-1}
          />
        )}
        {interactive && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 opacity-0 transition-opacity duration-200 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
            {onDetails && (
              <Button variant="dark" size="sm" onClick={onDetails} aria-label={`${t("vw.details")}: ${persona.name}`}>
                <Info size={14} aria-hidden /> {t("vw.details")}
              </Button>
            )}
            {onTalk && (
              <Button variant="dark" size="sm" onClick={onTalk} aria-label={`${actionLabel ?? t("vw.talk")}: ${persona.name}`}>
                <MessageCircle size={14} aria-hidden /> {actionLabel ?? t("vw.talk")}
              </Button>
            )}
          </div>
        )}
      </div>
      <p className="mt-2 truncate text-[11px] text-mute">{meta}</p>
      <p className="line-clamp-2 text-sm font-bold leading-snug">{title ?? persona.name}</p>
    </div>
  );
}
