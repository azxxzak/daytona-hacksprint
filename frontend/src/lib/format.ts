import type { Gaze, Persona, Test } from "./types";

/** Base path of a test's report/market/media endpoints (owner or shared link). */
export function apiBase(test: Pick<Test, "id" | "api_base">): string {
  return test.api_base ?? `/api/tests/${test.id}`;
}
import type { Lang } from "./i18n";

export function fmtTime(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** English view shows thought_en when present, otherwise falls back to the Japanese thought. */
export function thoughtOf(g: Pick<Gaze, "thought" | "thought_en">, lang: Lang): string {
  if (lang === "en") return g.thought_en || g.thought;
  return g.thought || g.thought_en;
}

export type SegmentKey = "all" | "a1" | "a2" | "a3" | "a4" | "F" | "M";

export function inSegment(p: Pick<Persona, "age" | "gender">, seg: SegmentKey): boolean {
  const a = Number(p.age);
  const g = String(p.gender ?? "").toLowerCase();
  switch (seg) {
    case "all":
      return true;
    case "a1":
      return a < 25;
    case "a2":
      return a >= 25 && a < 35;
    case "a3":
      return a >= 35 && a < 45;
    case "a4":
      return a >= 45;
    case "F":
      return g.startsWith("f");
    case "M":
      return g.startsWith("m");
  }
}

export const AGE_GROUPS: { key: SegmentKey; label: "pl.u25" | "pl.a25" | "pl.a35" | "pl.a45"; color: string }[] = [
  { key: "a1", label: "pl.u25", color: "#3b6fd4" },
  { key: "a2", label: "pl.a25", color: "#d9822b" },
  { key: "a3", label: "pl.a35", color: "#2e9e7a" },
  { key: "a4", label: "pl.a45", color: "#8a5cc2" },
];

export function mean(xs: number[]): number | null {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}
