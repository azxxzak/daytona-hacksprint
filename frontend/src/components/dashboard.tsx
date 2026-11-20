"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Film, Image as ImageIcon, Sparkles, Users, Upload, MessageCircle, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { usePolled, isActive } from "@/lib/hooks";
import type { Test, TestSummary } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { ProgressBar } from "./progress-bar";
import { useToast } from "./toast";
import { Button, Dialog, ErrorNote, SectionHeader, Skeleton, buttonClass, cx, useDocTitle } from "./ui";

type Progress = Test["progress"];

function StatusChip({ status }: { status: TestSummary["status"] }) {
  const { t } = useI18n();
  const map = {
    queued: ["dash.queued", "bg-canvas text-mute"],
    running: ["dash.running", "bg-ink text-white"],
    done: ["dash.done", "bg-canvas text-ink"],
    failed: ["dash.failed", "bg-danger/10 text-danger"],
  } as const;
  const [k, cls] = map[status];
  return (
    <span className={cx("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium", cls)}>
      {status === "running" && <span aria-hidden className="size-1.5 rounded-full bg-lime pulse" />}
      {t(k)}
    </span>
  );
}

function CardMenu({ name, onRename, onDelete }: { name: string; onRename: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open]);
  const item = "flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm hover:bg-canvas";
  return (
    <div ref={wrap} className="absolute right-3 top-3 z-10">
      <button
        ref={btn} type="button" aria-haspopup="menu" aria-expanded={open} aria-label={`${t("common.more")}: ${name}`}
        onClick={() => setOpen((o) => !o)}
        className={cx("grid size-8 place-items-center rounded-full bg-surface/90 text-mute transition-opacity hover:text-ink focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100", open ? "opacity-100" : "opacity-0")}
      >
        <MoreHorizontal size={16} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-10 w-40 rounded-card border border-line bg-surface p-1.5">
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
    <article className="group relative flex flex-col overflow-hidden rounded-card bg-surface transition-colors hover:bg-white">
      <div className="relative aspect-[16/10] overflow-hidden bg-[#e9e9ec]">
        {test.thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated API thumbnail
          <img
            src={test.thumb_url}
            alt=""
            loading="lazy"
            width={640}
            height={400}
            className={cx("h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]", active && "opacity-60")}
          />
        ) : (
          <div className="grid h-full place-items-center text-mute/60">
            <Icon size={28} aria-hidden />
          </div>
        )}
        <div className="absolute left-3 top-3">
          <StatusChip status={test.status} />
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">
        <h2 className="truncate text-[15px] font-bold" title={test.name}>
          <Link href={`/tests/${test.id}`} className="after:absolute after:inset-0 after:content-['']">
            {test.name}
          </Link>
        </h2>
        <p className="text-xs text-mute">
          <span className="tnum">{date}</span> · {t("dash.viewers", { n: test.viewers })} ·{" "}
          {test.media_kind === "video" ? t("dash.video") : t("dash.image")}
        </p>
        <div className="mt-2 min-h-5 text-sm">
          {test.status === "done" && test.engaged != null && (
            <p className="tnum font-medium">{t("dash.engaged", { n: test.engaged, total: test.viewers })}</p>
          )}
          {test.status === "failed" && <p className="text-danger">{t("dash.failedHint")}</p>}
          {active && (
            <div className="space-y-1.5">
              <ProgressBar percent={test.progress?.percent ?? 0} label={t("dash.running")} />
              <p className="truncate text-xs text-mute">{test.progress?.message || t("dash.queued")}</p>
            </div>
          )}
        </div>
      </div>
      <CardMenu name={test.name} onRename={onRename} onDelete={onDelete} />
    </article>
  );
}

function FirstRun() {
  const { t } = useI18n();
  const steps = [
    { Icon: Users, title: t("dash.s1t"), body: t("dash.s1d") },
    { Icon: Upload, title: t("dash.s2t"), body: t("dash.s2d") },
    { Icon: MessageCircle, title: t("dash.s3t"), body: t("dash.s3d") },
  ];
  return (
    <div className="mt-4 rounded-[20px] bg-surface p-6 sm:p-10">
      <h2 className="max-w-2xl text-balance text-2xl font-bold leading-snug tracking-tight sm:text-4xl">{t("dash.howTitle")}</h2>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-mute">{t("dash.howSub")}</p>
      <ol className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="rounded-card bg-canvas p-5">
            <div className="flex items-center gap-3">
              <span className="tnum grid size-8 place-items-center rounded-full bg-ink text-sm font-bold text-lime" aria-hidden>{i + 1}</span>
              <s.Icon size={18} className="text-mute" aria-hidden />
            </div>
            <h3 className="mt-4 text-base font-bold">{s.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-mute">{s.body}</p>
          </li>
        ))}
      </ol>
      <Link href="/tests/new" className={buttonClass("primary", "lg", "mt-8")}>
        <Plus size={18} aria-hidden /> {t("dash.start")}
      </Link>
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
  const sample = all.length <= 4 ? all.find((x) => x.status === "done") : undefined;
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
      <SectionHeader as="h1" label={t("dash.label")} title={t("dash.title")} />

      {all.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-72">
            <Search size={15} aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-mute" />
            <label htmlFor="test-search" className="sr-only">{t("dash.search")}</label>
            <input
              id="test-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("dash.search")}
              className="h-10 w-full rounded-full border border-line bg-surface pl-10 pr-4 text-sm"
            />
          </div>
          <div role="group" aria-label={t("dash.filter")} className="flex flex-wrap gap-1.5">
            {(["all", "running", "done", "failed"] as const).map((f) => (
              <button
                key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
                className={cx("h-9 rounded-full border px-4 text-[13px] font-medium transition-colors", filter === f ? "border-ink bg-ink text-white" : "border-line bg-surface text-mute hover:text-ink")}
              >
                {t(({ all: "dash.fAll", running: "dash.fRunning", done: "dash.fDone", failed: "dash.fFailed" } as const)[f])}
              </button>
            ))}
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
              <Skeleton key={i} className="h-[268px] bg-surface" />
            ))}
          </div>
        )}

        {data && all.length === 0 && (
          <FirstRun />
        )}

        {all.length > 0 && tests.length === 0 && <p className="py-10 text-center text-sm text-mute">{t("dash.noMatch")}</p>}

        {tests.length > 0 && (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sample && query === "" && filter === "all" && (
              <li>
                <Link href={`/tests/${sample.id}`} className="group relative flex h-full min-h-[200px] flex-col justify-between overflow-hidden rounded-card bg-ink p-5 text-white transition-transform hover:-translate-y-0.5">
                  <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium"><Sparkles size={12} className="text-lime" aria-hidden /> {t("dash.sample")}</span>
                  <span>
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

      {all.length > 0 && <div className="pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center">
        <Link href="/tests/new" className={buttonClass("primary", "lg", "pointer-events-auto pl-5")}>
          <Plus size={18} aria-hidden /> {t("dash.new")}
        </Link>
      </div>}

      <Dialog open={!!renaming} onClose={() => !renameBusy && setRenaming(null)} label={t("rename.title")}>
        <form onSubmit={(e) => { e.preventDefault(); void saveRename(); }}>
          <h2 className="pr-8 text-lg font-bold">{t("rename.title")}</h2>
          <label htmlFor="rename-input" className="mt-4 block text-sm font-medium">{t("rename.label")}</label>
          <input
            id="rename-input" value={newName} maxLength={120} autoFocus onChange={(e) => setNewName(e.target.value)}
            className="mt-1.5 h-11 w-full rounded-xl border border-line bg-canvas px-3.5 text-[15px] focus:bg-white"
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
