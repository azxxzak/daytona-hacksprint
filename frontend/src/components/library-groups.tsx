"use client";

import type { LibraryGroup, Persona } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { PersonaCard } from "./persona-card";
import { Button, SectionHeader } from "./ui";

export function groupName(g: LibraryGroup, lang: "en" | "ja") {
  return lang === "en" ? g.name_en || g.name : g.name;
}

export function LibraryGroupSection({
  group, selecting, picked, onToggle, onDetails, onUse, onUseGroup, headingAs,
}: {
  group: LibraryGroup;
  selecting: boolean;
  picked: Set<string>;
  onToggle: (p: Persona) => void;
  onDetails?: (p: Persona) => void;
  onUse?: (p: Persona) => void;
  onUseGroup?: (g: LibraryGroup) => void;
  headingAs?: "h2" | "h3";
}) {
  const { t, lang } = useI18n();
  return (
    <section aria-label={groupName(group, lang)}>
      <SectionHeader
        as={headingAs ?? "h2"}
        label={t("lib.group")}
        title={groupName(group, lang)}
        action={onUseGroup ? <Button variant="outline" size="sm" onClick={() => onUseGroup(group)}>{t("lib.usePanel")}</Button> : undefined}
      />
      {group.description && <p className="mt-2 max-w-3xl text-sm text-mute">{group.description}</p>}
      <ul className="mt-5 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {group.personas.map((p, i) => (
          <li key={p.id}>
            <PersonaCard
              persona={p}
              eager={i < 6}
              meta={p.profile?.meta}
              title={p.profile?.headline || p.name}
              selecting={selecting}
              selected={picked.has(p.id)}
              onToggle={() => onToggle(p)}
              onDetails={onDetails ? () => onDetails(p) : undefined}
              onTalk={onUse ? () => onUse(p) : undefined}
              actionLabel={onUse ? t("lib.use") : undefined}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
