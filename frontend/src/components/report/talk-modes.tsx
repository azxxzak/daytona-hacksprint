"use client";

import type { TalkMode } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { cx } from "../ui";

const bar = "h-1.5 rounded-full bg-ink/15";

function ConversationPreview() {
  const rows = [
    { c: "#3b6fd4", w: "w-24", align: "" },
    { c: "#d9822b", w: "w-20", align: "ml-6" },
    { c: "#2e9e7a", w: "w-28", align: "ml-2" },
  ];
  return (
    <div aria-hidden className="flex h-full flex-col justify-center gap-2.5 px-5">
      <div className="ml-auto w-24 rounded-full bg-ink/10 px-3 py-2"><div className={cx(bar, "w-full")} /></div>
      {rows.map((r, i) => (
        <div key={i} className={cx("flex items-center gap-2", r.align)}>
          <span className="size-5 shrink-0 rounded-full" style={{ background: r.c }} />
          <div className={cx("rounded-full bg-white px-3 py-2", r.w)}><div className={cx(bar, "w-full")} /></div>
        </div>
      ))}
    </div>
  );
}

function QaPreview() {
  const cols = ["#3b6fd4", "#d9822b", "#2e9e7a", "#8a5cc2"];
  return (
    <div aria-hidden className="flex h-full flex-col justify-center gap-2.5 px-5">
      <div className="ml-auto w-24 rounded-full bg-ink/10 px-3 py-2"><div className={cx(bar, "w-full")} /></div>
      <div className="grid grid-cols-2 gap-2">
        {cols.map((c) => (
          <div key={c} className="flex items-center gap-1.5 rounded-xl bg-white p-1.5">
            <span className="size-4 shrink-0 rounded-full" style={{ background: c }} />
            <div className="min-w-0 flex-1 space-y-1"><div className={cx(bar, "w-full")} /><div className={cx(bar, "w-2/3")} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ModeCard({ mode, onChoose, selected, label }: { mode: TalkMode; onChoose: () => void; selected?: boolean; label?: string }) {
  const { t } = useI18n();
  const conv = mode === "conversation";
  return (
    <div className={cx("flex flex-col rounded-card border p-4", selected ? "border-ink" : "border-line")}>
      <div className="h-32 overflow-hidden rounded-xl bg-canvas">{conv ? <ConversationPreview /> : <QaPreview />}</div>
      <h3 className="mt-4 text-[15px] font-bold">{conv ? t("talk.modeConv") : t("talk.modeQa")}</h3>
      <p className="mt-1 flex-1 text-[13px] leading-snug text-mute">{conv ? t("talk.modeConvDesc") : t("talk.modeQaDesc")}</p>
      <button
        type="button"
        onClick={onChoose}
        aria-pressed={selected}
        className="mt-4 inline-flex h-10 items-center justify-center rounded-full bg-ink px-5 text-sm font-medium text-white hover:bg-black"
      >
        {label ?? t("talk.continue")}
      </button>
    </div>
  );
}

export const MODES: TalkMode[] = ["conversation", "qa"];
