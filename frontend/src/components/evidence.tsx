"use client";

import type { Basis } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { cx } from "./ui";

/** Tiny evidence label; `because` shows on hover/focus via the title and an sr-only hint. */
export function EvidenceLabel({ basis, because, className }: { basis?: Basis; because?: string; className?: string }) {
  const { t } = useI18n();
  if (!basis) return null;
  const text = t(`ev.${basis}` as "ev.profile");
  return (
    <span
      title={because || undefined}
      tabIndex={because ? 0 : undefined}
      className={cx(
        "inline-flex items-center rounded-full px-2 py-px text-[10px] font-medium leading-4",
        basis === "invented" ? "bg-[#fff1d6] text-[#8a5a00]" : "bg-canvas text-mute",
        className,
      )}
    >
      {text}
      {because && <span className="sr-only">: {because}</span>}
    </span>
  );
}
