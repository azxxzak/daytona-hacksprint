"use client";

import type { ReactNode } from "react";
import { Info, MessageCircle } from "lucide-react";
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
  badge,
  onDetails,
  onInterview,
  eager,
}: {
  persona: Persona;
  title?: string;
  badge?: ReactNode;
  onDetails?: () => void;
  onInterview?: () => void;
  eager?: boolean;
}) {
  const { t } = useI18n();
  const meta = usePersonaMeta()(persona);
  const interactive = !!(onDetails || onInterview);

  return (
    <div className="group min-w-0">
      <div className="relative overflow-hidden rounded-card bg-surface">
        <Avatar
          src={persona.avatar_url}
          name={persona.name}
          color={persona.color}
          eager={eager}
          className={cx("aspect-[4/5] w-full", interactive && "transition duration-300 group-hover:scale-[1.03] group-hover:blur-[3px] group-hover:brightness-75 group-focus-within:blur-[3px] group-focus-within:brightness-75 motion-reduce:transition-none")}
        />
        {badge && <div className="absolute bottom-2 left-2">{badge}</div>}
        {onDetails && (
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
            {onInterview && (
              <Button variant="dark" size="sm" onClick={onInterview} aria-label={`${t("vw.interview")}: ${persona.name}`}>
                <MessageCircle size={14} aria-hidden /> {t("vw.interview")}
              </Button>
            )}
          </div>
        )}
      </div>
      <p className="mt-2 truncate text-[11px] text-mute">{meta}</p>
      <p className="truncate text-sm font-bold">{title ?? persona.name}</p>
    </div>
  );
}
