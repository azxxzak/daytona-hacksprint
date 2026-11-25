"use client";

import { useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from "react";
import { Pause, Play, Volume2, VolumeX } from "lucide-react";
import { fmtTime, inSegment, thoughtOf, type SegmentKey } from "@/lib/format";
import type { Gaze, Persona, Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { EvidenceLabel } from "../evidence";
import { cx } from "../ui";

export type PlayerHandle = { seek: (t: number) => void };

const JUMP_S = 0.22;     // a viewer's eyes jump to the next keyframe spot this fast (saccade-like), then hold
const FOLLOW_CELLS = 7;  // between keyframes a face follows the attention hotspot nearest its spot (grid cells)
const SNAP_MS = 70;      // time constant of that follow: quick hops, not a slow drift
const SEGMENTS: { key: SegmentKey; label: "pl.all" | "pl.u25" | "pl.a25" | "pl.a35" | "pl.a45" | "pl.women" | "pl.men" }[] = [
  { key: "all", label: "pl.all" },
  { key: "a1", label: "pl.u25" },
  { key: "a2", label: "pl.a25" },
  { key: "a3", label: "pl.a35" },
  { key: "a4", label: "pl.a45" },
  { key: "F", label: "pl.women" },
  { key: "M", label: "pl.men" },
];

// jet colour ramp, precomputed once: index 0..255 -> r,g,b
const JET = (() => {
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const v = i / 255;
    const c = (o: number) => Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - o))) * 255;
    lut[i * 3] = c(3);
    lut[i * 3 + 1] = c(2);
    lut[i * 3 + 2] = c(1);
  }
  return lut;
})();

type Pt = { x: number; y: number; interest: number; cur: Gaze };

function gazeAt(track: Gaze[], t: number, out: Pt): Pt {
  // hold each keyframe's spot, then jump to the next one quickly (eyes do not glide)
  let i = -1;
  for (let k = 0; k < track.length && track[k].t <= t; k++) i = k;
  if (i < 0) i = 0;
  const cur = track[i];
  out.cur = cur; out.interest = cur.interest;
  if (i > 0 && t - cur.t < JUMP_S) {
    const prev = track[i - 1], k = 1 - (1 - (t - cur.t) / JUMP_S) ** 3;
    out.x = prev.x + (cur.x - prev.x) * k; out.y = prev.y + (cur.y - prev.y) * k;
  } else {
    out.x = cur.x; out.y = cur.y;
  }
  return out;
}

/** Strongest separate peaks of one heat frame, normalised coordinates. */
function peaks(heat: number[], GW: number, GH: number): [number, number][] {
  const work = Float32Array.from(heat);
  let top = 0;
  for (const v of work) if (v > top) top = v;
  const out: [number, number][] = [];
  for (let n = 0; n < 6 && top > 0; n++) {
    let bi = 0;
    for (let i = 1; i < work.length; i++) if (work[i] > work[bi]) bi = i;
    if (work[bi] < 0.35 * top) break;
    const bx = bi % GW, by = (bi - bx) / GW;
    out.push([(bx + 0.5) / GW, (by + 0.5) / GH]);
    for (let y = Math.max(0, by - 4); y <= Math.min(GH - 1, by + 4); y++)
      for (let x = Math.max(0, bx - 4); x <= Math.min(GW - 1, bx + 4); x++) work[y * GW + x] = 0;
  }
  return out;
}

type Row = { p: Persona; g: Gaze };

export function Player({ test, ref }: { test: Test; ref?: Ref<PlayerHandle> }) {
  const { t, lang } = useI18n();
  const isVideo = test.media_kind === "video";
  // trained attention model (benchmarked against real eye-tracking) vs the old contrast map of earlier tests
  const trained = test.heat_model === "unisal";
  const [heatOn, setHeatOn] = useState(true);
  const [seg, setSeg] = useState<SegmentKey>("all");
  const [faces, setFaces] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [cur, setCur] = useState(0);
  const [dur, setDur] = useState(test.duration || 0);
  const [rows, setRows] = useState<Row[]>([]);
  const [caption, setCaption] = useState("");
  const [mediaError, setMediaError] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const mediaRef = useRef<HTMLVideoElement & HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const live = useRef({ heatOn, seg, faces });
  const dirty = useRef(true);

  useEffect(() => {
    live.current = { heatOn, seg, faces };
    dirty.current = true;
  }, [heatOn, seg, faces]);

  useImperativeHandle(ref, () => ({
    seek(sec: number) {
      const v = mediaRef.current;
      if (!v || !isVideo) return;
      v.currentTime = sec;
      void v.play().catch(() => undefined);
      stageRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
  }), [isVideo]);

  const { tracks } = useMemo(() => {
    const byId = new Map(test.personas.map((p) => [p.id, p]));
    const m = new Map<string, Gaze[]>();
    for (const g of test.gaze) {
      const a = m.get(g.id);
      if (a) a.push(g); else m.set(g.id, [g]);
    }
    const tracks: { p: Persona; pts: Gaze[] }[] = [];
    for (const [id, pts] of m) {
      const p = byId.get(id);
      if (!p) continue;
      pts.sort((a, b) => a.t - b.t);
      tracks.push({ p, pts });
    }
    return { tracks };
  }, [test.personas, test.gaze]);

  useEffect(() => {
    const [GW, GH] = test.grid;
    const media = mediaRef.current;
    const canvas = canvasRef.current;
    if (!media || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const off = document.createElement("canvas");
    off.width = GW; off.height = GH;
    const octx = off.getContext("2d")!;
    const img = octx.createImageData(GW, GH);
    const frames = test.frames;
    const peakCache = new Map<number, [number, number][]>();
    const shown = new Map<string, { x: number; y: number }>();   // where each face is drawn now
    let lastNow = 0, lastSec = 0;

    // portraits for the moving faces: pre-rendered as small circles once they load
    const bubbles = new Map<string, HTMLCanvasElement>();
    for (const { p } of tracks) {
      const im = new Image();
      im.decoding = "async";
      im.onload = () => {
        const c = document.createElement("canvas");
        c.width = c.height = 64;
        const cc = c.getContext("2d")!;
        cc.beginPath(); cc.arc(32, 32, 32, 0, Math.PI * 2); cc.clip();
        const s = Math.min(im.naturalWidth, im.naturalHeight);
        cc.drawImage(im, (im.naturalWidth - s) / 2, (im.naturalHeight - s) / 4, s, s, 0, 0, 64, 64);
        bubbles.set(p.id, c);
        dirty.current = true;
      };
      im.src = p.avatar_url;
    }

    const scratch: Pt = { x: 0, y: 0, interest: 0, cur: tracks[0]?.pts[0] as Gaze };
    let raf = 0;
    let lastT = -1;
    let lastTick = 0;
    let lastCaption = "";
    let cw = 0, ch = 0;

    const frameIdx = (sec: number) => {
      let lo = 0, hi = frames.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (frames[mid].t <= sec) lo = mid; else hi = mid - 1;
      }
      return lo;
    };
    const nearest = (pts: [number, number][], x: number, y: number, cells: number) => {
      let best: [number, number] | null = null, bd = cells * cells;
      for (const q of pts) {
        const d2 = ((q[0] - x) * GW) ** 2 + ((q[1] - y) * GH) ** 2;
        if (d2 < bd) { bd = d2; best = q; }
      }
      return best;
    };
    const peaksAt = (idx: number) => {
      let p = peakCache.get(idx);
      if (!p) { p = peaks(frames[idx].heat, GW, GH); peakCache.set(idx, p); }
      return p;
    };

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const sec = isVideo ? media.currentTime || 0 : 0;
      const playingNow = isVideo && !media.paused && !media.ended;
      if (!playingNow && !dirty.current && sec === lastT) return;
      dirty.current = false;
      lastT = sec;

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = media.clientWidth, h = media.clientHeight;
      if (w === 0 || h === 0) return;
      if (cw !== w || ch !== h) {
        cw = w; ch = h;
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const { heatOn: heatShown, seg: sg, faces: showFaces } = live.current;
      const fi = frames.length ? frameIdx(sec) : -1;
      const hot = fi >= 0 ? peaksAt(fi) : [];
      const seeked = Math.abs(sec - lastSec) > 0.6 || now - lastNow > 400;
      const kSnap = seeked ? 1 : 1 - Math.exp(-(now - lastNow) / SNAP_MS);
      lastNow = now; lastSec = sec;
      let moving = false;
      const active: { p: Persona; pt: Pt; x: number; y: number }[] = [];
      for (const { p, pts } of tracks) {
        if (!inSegment(p, sg)) continue;
        const pt = gazeAt(pts, sec, { ...scratch });
        // between keyframes the face moves with what it looks at: take the model hotspot nearest the persona's
        // spot at its keyframe, find where that hotspot is now, and shift the persona's own spot by the same amount
        let tx = pt.x, ty = pt.y;
        const h0 = nearest(fi >= 0 ? peaksAt(frameIdx(pt.cur.t)) : [], pt.x, pt.y, FOLLOW_CELLS);
        if (h0) {
          const h1 = nearest(hot, h0[0], h0[1], FOLLOW_CELLS);
          if (h1) { tx = Math.min(1, Math.max(0, pt.x + h1[0] - h0[0])); ty = Math.min(1, Math.max(0, pt.y + h1[1] - h0[1])); }
        }
        const s0 = shown.get(p.id) ?? { x: tx, y: ty };
        const nx = s0.x + (tx - s0.x) * kSnap, ny = s0.y + (ty - s0.y) * kSnap;
        if (Math.abs(nx - tx) + Math.abs(ny - ty) > 0.002) moving = true;
        shown.set(p.id, { x: nx, y: ny });
        active.push({ p, pt, x: nx, y: ny });
      }
      if (moving) dirty.current = true;

      if (heatShown && fi >= 0) {
        const heat = frames[fi].heat;
        const d = img.data;
        for (let i = 0; i < GW * GH; i++) {
          const v = ((heat[i] ?? 0) / 255) ** 0.7;   // display only: the model's map is peaky, lift its shoulders
          const k = Math.min(255, Math.max(0, Math.round(v * 255))) * 3;
          d[i * 4] = JET[k]; d[i * 4 + 1] = JET[k + 1]; d[i * 4 + 2] = JET[k + 2];
          d[i * 4 + 3] = v > 0.35 ? v * 170 : 0;
        }
        octx.putImageData(img, 0, 0);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(off, 0, 0, w, h);
      }

      if (showFaces) {
        const R = Math.max(10, Math.min(19, w / 42));
        for (const a of active) {
          const cx = a.x * w, cy = a.y * h;
          const b = bubbles.get(a.p.id);
          if (b) ctx.drawImage(b, cx - R, cy - R, R * 2, R * 2);
          else { ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fillStyle = a.p.color; ctx.fill(); }
          ctx.beginPath(); ctx.arc(cx, cy, R + 1, 0, Math.PI * 2);
          ctx.lineWidth = 4.5; ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.stroke();
          ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2);
          ctx.lineWidth = 3; ctx.strokeStyle = a.p.color; ctx.stroke();
        }
      }

      // caption + side list only need ~5 Hz; React renders are kept off the frame path
      const seg = test.transcript.find((s) => sec >= s.start && sec <= s.end)?.text ?? "";
      if (seg !== lastCaption) { lastCaption = seg; setCaption(seg); }
      if (now - lastTick > 200 || !playingNow) {
        lastTick = now;
        const next = active.map((a) => ({ p: a.p, g: a.pt.cur })).sort((x, y) => y.g.interest - x.g.interest);
        setRows(next);
        setCur(sec);
      }
    };

    raf = requestAnimationFrame(draw);
    const wake = () => { dirty.current = true; };
    media.addEventListener("seeked", wake);
    media.addEventListener("loadeddata", wake);
    media.addEventListener("load", wake);
    window.addEventListener("resize", wake);
    return () => {
      cancelAnimationFrame(raf);
      media.removeEventListener("seeked", wake);
      media.removeEventListener("loadeddata", wake);
      media.removeEventListener("load", wake);
      window.removeEventListener("resize", wake);
    };
  }, [test.grid, test.frames, test.transcript, tracks, isVideo]);

  const avg = rows.length ? rows.reduce((s, r) => s + r.g.interest, 0) / rows.length : 0;
  const ratio = test.width && test.height ? test.width / test.height : 16 / 9;
  const toggle = () => {
    const v = mediaRef.current;
    if (!v) return;
    if (v.paused) void v.play().catch(() => undefined); else v.pause();
  };

  const sel = "h-9 rounded-full border border-line bg-surface px-3 text-[13px] font-medium";

  return (
    <section aria-label={t("pl.stage")}>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px]">
        <span className="flex items-center gap-2">
          <button
            type="button" aria-pressed={heatOn} onClick={() => setHeatOn((v) => !v)}
            className={cx("h-9 rounded-full border px-4 font-medium transition-colors", heatOn ? "border-ink bg-ink text-white" : "border-line bg-surface text-mute hover:text-ink")}
          >
            {t("pl.heat")}
          </button>
          <span
            tabIndex={0} role="img" aria-label={trained ? t("pl.heatInfoModel") : t("pl.heatInfoOld")} title={trained ? t("pl.heatInfoModel") : t("pl.heatInfoOld")}
            className="grid size-5 cursor-help place-items-center rounded-full border border-line text-[11px] font-semibold text-mute"
          >i</span>
        </span>
        <label className="flex items-center gap-2 text-mute">
          {t("pl.who")}
          <select value={seg} onChange={(e) => setSeg(e.target.value as SegmentKey)} className={cx(sel, "text-ink")}>
            {SEGMENTS.map((s) => <option key={s.key} value={s.key}>{t(s.label)}</option>)}
          </select>
        </label>
        <button
          type="button" aria-pressed={faces} onClick={() => setFaces((f) => !f)}
          className={cx("h-9 rounded-full border px-4 font-medium transition-colors", faces ? "border-ink bg-ink text-white" : "border-line bg-surface text-mute hover:text-ink")}
        >
          {t("pl.faces")}
        </button>
        <p className="tnum ml-auto text-mute" aria-live="off">
          {rows.length ? t("pl.avg", { n: rows.length, a: avg.toFixed(1) }) : t("pl.none")}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="on-dark overflow-hidden rounded-card bg-ink">
          <div className="grid place-items-center p-2 sm:p-3">
            <div
              ref={stageRef}
              className="relative max-w-full overflow-hidden rounded-lg bg-black"
              style={{ aspectRatio: ratio, width: `min(100%, calc(68vh * ${ratio}))` }}
            >
              {isVideo ? (
                <video
                  ref={mediaRef} src={test.media_url} playsInline preload="auto"
                  muted={muted}
                  onClick={toggle}
                  onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
                  onLoadedMetadata={(e) => setDur(e.currentTarget.duration || test.duration)}
                  onError={() => setMediaError(true)}
                  className="absolute inset-0 h-full w-full cursor-pointer object-contain"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- authenticated API media
                <img ref={mediaRef} src={test.media_url} alt="" onError={() => setMediaError(true)} className="absolute inset-0 h-full w-full object-contain" />
              )}
              <canvas ref={canvasRef} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />
              {caption && (
                <p className="pointer-events-none absolute inset-x-3 bottom-3 mx-auto w-fit max-w-[92%] rounded-md bg-black/70 px-3 py-1 text-center text-[13px] font-medium leading-snug text-white sm:text-base">
                  {caption}
                </p>
              )}
              {mediaError && <p role="alert" className="absolute inset-0 grid place-items-center text-sm text-white/80">{t("pl.mediaError")}</p>}
            </div>
          </div>
          {isVideo && (
            <div className="flex items-center gap-3 px-3 pb-3 text-white sm:px-4">
              <button
                type="button" onClick={toggle} aria-label={playing ? t("pl.pause") : t("pl.play")}
                className="grid size-9 shrink-0 place-items-center rounded-full bg-white/10 text-lime hover:bg-white/20"
              >
                {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
              </button>
              <input
                type="range" className="range min-w-0 flex-1 accent-lime" min={0} max={dur || 0} step={0.1} value={Math.min(cur, dur || 0)}
                aria-label={t("pl.seek")} aria-valuetext={`${fmtTime(cur)} / ${fmtTime(dur)}`}
                onChange={(e) => { const v = mediaRef.current; if (v) { v.currentTime = Number(e.target.value); dirty.current = true; setCur(Number(e.target.value)); } }}
                style={{ ["--track" as string]: "rgba(255,255,255,.25)" }}
              />
              <span className="tnum shrink-0 text-xs text-white/70">{fmtTime(cur)} / {fmtTime(dur)}</span>
              <button
                type="button" onClick={() => setMuted((m) => !m)} aria-label={muted ? t("pl.unmute") : t("pl.mute")} aria-pressed={muted}
                className="grid size-9 shrink-0 place-items-center rounded-full text-white/80 hover:bg-white/10"
              >
                {muted ? <VolumeX size={16} aria-hidden /> : <Volume2 size={16} aria-hidden />}
              </button>
            </div>
          )}
        </div>

        {/* The list never sets the row height: on desktop it fills the player's height and scrolls inside
            (a 60-viewer panel would otherwise stretch the page by ~9,000px); on mobile it is capped. */}
        <div className="relative min-h-[320px] lg:min-h-[360px]">
        <aside
          aria-label={t("pl.thoughts")}
          className="flex max-h-[440px] flex-col overflow-hidden rounded-card bg-surface lg:absolute lg:inset-0 lg:max-h-none"
        >
          <h3 className="shrink-0 border-b border-line px-4 py-3 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">{t("pl.thoughts")}</h3>
          <ul className="min-h-0 flex-1 divide-y divide-line overflow-y-auto overscroll-contain">
            {rows.map(({ p, g }) => (
              <li key={p.id} className="flex gap-3 px-4 py-3">
                {/* eslint-disable-next-line @next/next/no-img-element -- avatar from API */}
                <img src={p.avatar_url} alt="" width={36} height={36} className="size-9 shrink-0 rounded-full object-cover" style={{ border: `2px solid ${p.color}` }} />
                <div className="min-w-0 flex-1 text-[13px]">
                  <p className="truncate"><b>{p.name}</b> <span className="text-mute">{p.age}, {p.occupation}</span></p>
                  <p className="truncate text-xs text-mute">{t("pl.looking")}: {g.looking_at}</p>
                  <p className="mt-1 leading-snug">{thoughtOf(g, test.lang ?? lang)}</p>
                  <EvidenceLabel basis={g.basis} because={g.because} className="mt-1" />
                  <div className="mt-2 h-[3px] rounded bg-line" role="img" aria-label={`${g.interest} / 5`}>
                    <div className="h-full rounded bg-ink" style={{ width: `${g.interest * 20}%` }} />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </aside>
        </div>
      </div>
    </section>
  );
}
