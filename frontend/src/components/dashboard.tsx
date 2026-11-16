"use client";

import Link from "next/link";
import { useState } from "react";
import { Film, Image as ImageIcon, Plus, Trash2 } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { usePolled, isActive } from "@/lib/hooks";
import type { Test, TestSummary } from "@/lib/types";
import { useI18n } from "./i18n-provider";
import { ProgressBar } from "./progress-bar";
import { Button, Dialog, ErrorNote, SectionHeader, buttonClass, cx } from "./ui";

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

function TestCard({ test, onDelete }: { test: TestSummary & { progress?: Progress }; onDelete: () => void }) {
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
      <button
        type="button"
        onClick={onDelete}
        aria-label={t("dash.deleteAria", { name: test.name })}
        className="absolute right-3 top-3 z-10 grid size-8 place-items-center rounded-full bg-surface/90 text-mute opacity-0 transition-opacity hover:text-danger focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
      >
        <Trash2 size={15} aria-hidden />
      </button>
    </article>
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
  const tests = data?.tests ?? [];

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api(`/api/tests/${pendingDelete.id}`, { method: "DELETE" });
      setPendingDelete(null);
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

      <div className="mt-6">
        {error && !data && (
          <ErrorNote action={<Button variant="outline" size="sm" onClick={reload}>{t("common.retry")}</Button>}>
            {t("dash.loadError")} {errorText(error, t)}
          </ErrorNote>
        )}

        {loading && !data && !error && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="pulse h-[268px] rounded-card bg-surface" />
            ))}
          </div>
        )}

        {data && tests.length === 0 && (
          <div className="mx-auto mt-10 max-w-md rounded-[18px] bg-surface px-8 py-14 text-center">
            <div className="mx-auto grid size-12 place-items-center rounded-full bg-ink text-lime">
              <Plus size={22} aria-hidden />
            </div>
            <h2 className="mt-5 text-xl font-bold">{t("dash.emptyTitle")}</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm text-mute">{t("dash.emptyBody")}</p>
          </div>
        )}

        {tests.length > 0 && (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {tests.map((x) => (
              <li key={x.id}>
                <TestCard test={x} onDelete={() => setPendingDelete(x)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-20 flex justify-center">
        <Link href="/tests/new" className={buttonClass("primary", "lg", "pointer-events-auto pl-5")}>
          <Plus size={18} aria-hidden /> {t("dash.new")}
        </Link>
      </div>

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
