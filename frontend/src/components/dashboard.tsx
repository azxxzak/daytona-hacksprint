"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, Film, Image as ImageIcon, Sparkles, Users, Upload, MessageCircle, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { useApi, usePolled, isActive } from "@/lib/hooks";
import type { Test, TestSummary } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { ProgressBar } from "./progress-bar";
import { useToast } from "./toast";
import { Button, Dialog, ErrorNote, SectionHeader, Skeleton, buttonClass, cx, useDocTitle } from "./ui";

type Progress = Test["progress"];

function StatusChip({ status }: { status: TestSummary["status"] }) {
  const { t } = useI18n();
  const map = {
    queued: ["dash.queued", "bg-white/90 text-ink"],
    running: ["dash.running", "bg-ink/85 text-white"],
    done: ["dash.done", "bg-white/90 text-ink"],
    failed: ["dash.failed", "bg-[#fdeceb] text-danger"],
  } as const;
  const [k, cls] = map[status];
  return (
    <span className={cx("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-semibold shadow-[0_2px_8px_rgb(0_0_0/0.12)] backdrop-blur", cls)}>
      {status === "running" && <span aria-hidden className="size-1.5 rounded-full bg-lime pulse" />}
      {status === "failed" && <AlertTriangle size={11} aria-hidden />}
      {t(k)}
    </span>
  );
}

/** Engaged share as a short lime bar, with average interest beside it. */
function EngagedMeter({ engaged, total, avg }: { engaged: number; total: number; avg: number | null }) {
  const { t } = useI18n();
  const pct = total ? Math.round((engaged / total) * 100) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="tnum font-semibold">{t("dash.engaged", { n: engaged, total })}</span>
        {avg != null && <span className="tnum text-xs text-mute">{t("dash.interest", { v: avg.toFixed(1) })}</span>}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-canvas" aria-hidden>
        <div className="h-full rounded-full bg-ink" style={{ width: `${Math.max(pct, 2)}%` }}>
          <div className="ml-auto h-full w-1.5 rounded-full bg-lime" />
        </div>
      </div>
    </div>
  );
}

function CardMenu({ name, onRename, onDelete }: { name: string; onRename: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", down); document.removeEventListener("keydown", key); };
  }, [open]);
  const item = "flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm hover:bg-canvas";
  return (
    <div ref={wrap} className="absolute right-3 top-3 z-10">
      <button
        ref={btn} type="button" aria-haspopup="menu" aria-expanded={open} aria-label={`${t("common.more")}: ${name}`}
        onClick={() => setOpen((o) => !o)}
        className={cx("grid size-8 place-items-center rounded-full bg-white/90 text-ink shadow-[0_2px_8px_rgb(0_0_0/0.12)] backdrop-blur transition-opacity focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100", open ? "opacity-100" : "opacity-0")}
      >
        <MoreHorizontal size={16} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="pop absolute right-0 top-10 w-44 origin-top-right rounded-2xl bg-surface p-1.5 shadow-pop">
          <button type="button" role="menuitem" autoFocus className={item} onClick={() => { setOpen(false); onRename(); }}><Pencil size={14} aria-hidden /> {t("common.rename")}</button>
          <button type="button" role="menuitem" className={cx(item, "text-danger")} onClick={() => { setOpen(false); onDelete(); }}><Trash2 size={14} aria-hidden /> {t("common.delete")}</button>
        </div>
      )}
    </div>
  );
}

function TestCard({ test, onDelete, onRename }: { test: TestSummary & { progress?: Progress }; onDelete: () => void; onRename: () => void }) {
  const { t, lang } = useI18n();
  const date = new Intl.DateTimeFormat(lang === "ja" ? "ja-JP" : "en-GB", { dateStyle: "medium" }).format(new Date(test.created_at));
  const active = isActive(test);
  const Icon = test.media_kind === "video" ? Film : ImageIcon;

  return (
    <article className="group relative flex h-full flex-col overflow-hidden rounded-[18px] bg-surface shadow-card transition-[box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-lift">
      <div className="relative aspect-[16/10] overflow-hidden bg-canvas">
        {test.thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated API thumbnail
          <img
            src={test.thumb_url}
            alt=""
            loading="lazy"
            width={640}
            height={400}
            className={cx("h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]", active && "opacity-60", test.status === "failed" && "grayscale")}
          />
        ) : (
          <div className="dots-ink grid h-full place-items-center bg-[#ececef]">
            <span className="grid size-12 place-items-center rounded-2xl bg-surface text-mute shadow-card">
              <Icon size={22} aria-hidden />
            </span>
          </div>
        )}
        {test.thumb_url && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/45 to-transparent" />}
        <span className={cx("absolute bottom-2.5 left-3 inline-flex items-center gap-1.5 text-[11px] font-semibold", test.thumb_url ? "text-white" : "text-mute")}>
          <Icon size={12} aria-hidden /> {test.media_kind === "video" ? t("dash.video") : t("dash.image")}
        </span>
        {test.status !== "done" && (
          <div className="absolute left-3 top-3">
            <StatusChip status={test.status} />
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col p-4 pt-3.5">
        <h2 className="truncate text-[15px] font-bold tracking-[-0.01em]" title={test.name}>
          <Link href={`/tests/${test.id}`} className="after:absolute after:inset-0 after:content-['']">
            {test.name}
          </Link>
        </h2>
        <p className="mt-0.5 text-xs text-mute">
          <span className="tnum">{date}</span> · {t("dash.viewers", { n: test.viewers })}
        </p>
        <div className="mt-auto pt-4 text-sm">
          {test.status === "done" && test.engaged != null && <EngagedMeter engaged={test.engaged} total={test.viewers} avg={test.avg_interest} />}
          {test.status === "failed" && <p className="text-[13px] text-danger">{t("dash.failedHint")}</p>}
          {active && (
            <div className="space-y-1.5">
              <p className="truncate text-xs text-mute">{test.progress?.message || t("dash.queued")}</p>
              <ProgressBar percent={test.progress?.percent ?? 0} label={t("dash.running")} />
            </div>
          )}
        </div>
      </div>
      <CardMenu name={test.name} onRename={onRename} onDelete={onDelete} />
    </article>
  );
}

function Stats({ tests }: { tests: TestSummary[] }) {
  const { t } = useI18n();
  const done = tests.filter((x) => x.status === "done" && x.engaged != null);
  const seen = done.reduce((a, x) => a + x.viewers, 0);
  const engaged = done.reduce((a, x) => a + (x.engaged ?? 0), 0);
  const running = tests.filter(isActive).length;
  const items = [
    { k: t("dash.statTests"), v: String(tests.length) },
    { k: t("dash.statRunning"), v: String(running), live: running > 0 },
    { k: t("dash.statViewers"), v: tests.reduce((a, x) => a + x.viewers, 0).toLocaleString() },
    { k: t("dash.statEngaged"), v: seen ? `${Math.round((engaged / seen) * 100)}%` : "–", hint: t("dash.statEngagedHint") },
  ];
  return (
    <dl className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {items.map((x) => (
        <div key={x.k} className="rounded-[18px] bg-surface px-4 py-3.5 shadow-card sm:px-5 sm:py-4">
          <dt className="flex items-center gap-1.5 text-xs font-medium text-mute">
            {x.live && <span aria-hidden className="pulse size-1.5 rounded-full bg-lime ring-1 ring-ink/70" />}
            {x.k}
          </dt>
          <dd className="tnum mt-1.5 text-2xl font-bold leading-none tracking-[-0.02em] sm:text-[28px]">{x.v}</dd>
          {x.hint && <dd className="mt-1.5 text-[11px] text-mute">{x.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

function FirstRun({ sample }: { sample: boolean }) {
  const { t } = useI18n();
  const steps = [
    { Icon: Users, title: t("dash.s1t"), body: t("dash.s1d") },
    { Icon: Upload, title: t("dash.s2t"), body: t("dash.s2d") },
    { Icon: MessageCircle, title: t("dash.s3t"), body: t("dash.s3d") },
  ];
  return (
    <div className="relative mt-4 overflow-hidden rounded-[24px] bg-surface p-6 shadow-card sm:p-10">
      <div aria-hidden className="dots-ink absolute inset-y-0 right-0 hidden w-1/2 [mask-image:linear-gradient(to_left,black,transparent)] md:block" />
      <div aria-hidden className="absolute -right-24 -top-24 size-72 rounded-full bg-lime/30 blur-3xl" />
      <h2 className="relative max-w-2xl text-balance text-2xl font-bold leading-snug tracking-[-0.02em] sm:text-[40px] sm:leading-[1.15]">{t("dash.howTitle")}</h2>
      <p className="relative mt-3 max-w-2xl text-[15px] leading-relaxed text-mute">{t("dash.howSub")}</p>
      <ol className="relative mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="rise rounded-[18px] border border-line bg-surface/80 p-5 backdrop-blur" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="flex items-center gap-3">
              <span className="tnum grid size-8 place-items-center rounded-full bg-ink text-sm font-bold text-lime" aria-hidden>{i + 1}</span>
              <s.Icon size={18} className="text-mute" aria-hidden />
            </div>
            <h3 className="mt-4 text-base font-bold">{s.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-mute">{s.body}</p>
          </li>
        ))}
      </ol>
      <div className="relative mt-8 flex flex-wrap gap-3">
        <Link href="/tests/new" className={buttonClass("primary", "lg")}>
          <Plus size={18} aria-hidden /> {t("dash.start")}
        </Link>
        {sample && (
          <Link href="/share/sample" className={buttonClass("outline", "lg")}>
            <Sparkles size={16} aria-hidden /> {t("dash.sampleOpen")}
          </Link>
        )}
      </div>
    </div>
  );
}

export function Dashboard() {
  const { t } = useI18n();
  const { data, error, loading, reload } = usePolled<{ tests: (TestSummary & { progress?: Progress })[] }>(
    "/api/tests",
    (d) => d.tests.some(isActive),
    3000,
  );
  const [pendingDelete, setPendingDelete] = useState<TestSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const toast = useToast();
  useDocTitle(t("dash.title"));
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "running" | "done" | "failed">("all");
  const [renaming, setRenaming] = useState<TestSummary | null>(null);
  const [newName, setNewName] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const all = data?.tests ?? [];
  const sampleApi = useApi<{ available: boolean }>("/api/share/sample/available");
  const hasSample = !!sampleApi.data?.available;
  const sample = all.length <= 4 && hasSample;
  const tests = all.filter((x) => {
    const okStatus = filter === "all" || (filter === "running" ? isActive(x) : x.status === filter);
    return okStatus && x.name.toLowerCase().includes(query.trim().toLowerCase());
  });

  const saveRename = async () => {
    const name = newName.trim();
    if (!renaming || !name) return;
    setRenameBusy(true);
    try {
      await api(`/api/tests/${renaming.id}`, { method: "PATCH", json: { name } });
      toast.success(t("toast.renamed"));
      setRenaming(null);
      reload();
    } catch (e) {
      toast.error(errorText(e, t));
    } finally {
      setRenameBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api(`/api/tests/${pendingDelete.id}`, { method: "DELETE" });
      setPendingDelete(null);
      toast.success(t("toast.deleted"));
      reload();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? errorText(e, t) : t("err.generic"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <SectionHeader
        as="h1"
        label={t("dash.label")}
        title={t("dash.title")}
        action={all.length > 0 && <span className="hidden sm:block"><Link href="/tests/new" className={buttonClass("primary", "md")}><Plus size={17} aria-hidden /> {t("dash.new")}</Link></span>}
      />

      {all.length > 0 && <Stats tests={all} />}

      {all.length > 0 && (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full sm:w-72">
            <Search size={15} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-mute" />
            <label htmlFor="test-search" className="sr-only">{t("dash.search")}</label>
            <input
              id="test-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("dash.search")}
              className="h-10 w-full rounded-full border border-line bg-surface pl-10 pr-4 text-sm shadow-[0_1px_2px_rgb(17_17_17/0.04)] transition-colors placeholder:text-mute/70 hover:border-[#cfcfd4] focus:border-ink"
            />
          </div>
          <div role="group" aria-label={t("dash.filter")} className="flex max-w-full gap-0.5 overflow-x-auto rounded-full bg-[#e7e7ea] p-1">
            {(["all", "running", "done", "failed"] as const).map((f) => {
              const n = f === "all" ? all.length : all.filter((x) => (f === "running" ? isActive(x) : x.status === f)).length;
              return (
                <button
                  key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
                  className={cx("flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-[color,background-color,box-shadow]", filter === f ? "bg-surface text-ink shadow-[0_1px_3px_rgb(17_17_17/0.14)]" : "text-mute hover:text-ink")}
                >
                  {t(({ all: "dash.fAll", running: "dash.fRunning", done: "dash.fDone", failed: "dash.fFailed" } as const)[f])}
                  <span className={cx("tnum text-[11px]", filter === f ? "text-mute" : "text-mute/70")}>{n}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-6">
        {error && !data && (
          <ErrorNote action={<Button variant="outline" size="sm" onClick={reload}>{t("common.retry")}</Button>}>
            {t("dash.loadError")} {errorText(error, t)}
          </ErrorNote>
        )}

        {loading && !data && !error && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[300px] rounded-[18px]" />
            ))}
          </div>
        )}

        {data && all.length === 0 && (
          <FirstRun sample={hasSample} />
        )}

        {all.length > 0 && tests.length === 0 && (
          <div className="grid place-items-center gap-3 rounded-[18px] border border-dashed border-line py-14 text-center">
            <span className="grid size-11 place-items-center rounded-full bg-surface text-mute shadow-card"><Search size={18} aria-hidden /></span>
            <p className="text-sm text-mute">{t("dash.noMatch")}</p>
          </div>
        )}

        {tests.length > 0 && (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:gap-5">
            {sample && query === "" && filter === "all" && (
              <li>
                <Link href="/share/sample" className="group relative flex h-full min-h-[200px] flex-col justify-between overflow-hidden rounded-[18px] bg-ink p-5 text-white shadow-card transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-lift">
                  <span aria-hidden className="dots absolute inset-0" />
                  <span aria-hidden className="absolute -right-16 -top-16 size-48 rounded-full bg-lime/25 blur-2xl" />
                  <span className="relative inline-flex w-fit items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium"><Sparkles size={12} className="text-lime" aria-hidden /> {t("dash.sample")}</span>
                  <span className="relative">
                    <span className="block text-lg font-bold leading-snug">{t("dash.sampleD")}</span>
                    <span className="mt-3 inline-flex items-center gap-1.5 text-sm text-lime">{t("dash.open")} <ArrowRight size={14} aria-hidden /></span>
                  </span>
                </Link>
              </li>
            )}
            {tests.map((x) => (
              <li key={x.id}>
                <TestCard test={x} onDelete={() => setPendingDelete(x)} onRename={() => { setNewName(x.name); setRenaming(x); }} />
              </li>
            ))}
          </ul>
        )}
      </div>

      {all.length > 0 && <div className="pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center sm:hidden">
        <Link href="/tests/new" className={buttonClass("primary", "lg", "pointer-events-auto pl-5 shadow-pop")}>
          <Plus size={18} aria-hidden /> {t("dash.new")}
        </Link>
      </div>}

      <Dialog open={!!renaming} onClose={() => !renameBusy && setRenaming(null)} label={t("rename.title")}>
        <form onSubmit={(e) => { e.preventDefault(); void saveRename(); }}>
          <h2 className="pr-8 text-lg font-bold">{t("rename.title")}</h2>
          <label htmlFor="rename-input" className="mt-4 block text-sm font-medium">{t("rename.label")}</label>
          <input
            id="rename-input" value={newName} maxLength={120} autoFocus onChange={(e) => setNewName(e.target.value)}
            className="mt-1.5 h-11 w-full rounded-xl border border-line bg-canvas px-3.5 text-[15px] transition-colors focus:border-ink focus:bg-white"
          />
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRenaming(null)} disabled={renameBusy}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={renameBusy || !newName.trim()}>{t("common.save")}</Button>
          </div>
        </form>
      </Dialog>

      <Dialog open={!!pendingDelete} onClose={() => !deleting && setPendingDelete(null)} label={t("dash.deleteTitle")}>
        <h2 className="pr-8 text-lg font-bold">{t("dash.deleteTitle")}</h2>
        <p className="mt-2 text-sm text-mute">{t("dash.deleteBody", { name: pendingDelete?.name ?? "" })}</p>
        {deleteError && <p role="alert" className="mt-3 text-sm text-danger">{deleteError}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setPendingDelete(null)} disabled={deleting}>{t("common.cancel")}</Button>
          <Button onClick={confirmDelete} disabled={deleting}>{t("common.delete")}</Button>
        </div>
      </Dialog>
    </>
  );
}
