"use client";

import { useState } from "react";
import { Check, Copy, Link2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import type { Test } from "@/lib/types";
import { useI18n } from "../i18n-provider";
import { useToast } from "../toast";
import { Button, Dialog } from "../ui";

/** Owner-only: create, copy or turn off the read-only link to this report. */
export function ShareDialog({ test, open, onClose, onChanged }: { test: Test; open: boolean; onClose: () => void; onChanged: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const [token, setToken] = useState<string | null>(test.share_token ?? null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const url = token && typeof window !== "undefined" ? `${window.location.origin}/share/${token}` : "";

  const create = async () => {
    setBusy(true);
    try {
      const r = await api<{ share_token: string }>(`/api/tests/${test.id}/share`, { method: "POST" });
      setToken(r.share_token);
      onChanged();
    } catch (e) {
      toast.error(errorText(e, t));
    } finally {
      setBusy(false);
    }
  };
  const revoke = async () => {
    setBusy(true);
    try {
      await api(`/api/tests/${test.id}/share`, { method: "DELETE" });
      setToken(null);
      onChanged();
      toast.success(t("share.revoked"));
    } catch (e) {
      toast.error(errorText(e, t));
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t("share.copyError"));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} label={t("share.title")}>
      <div className="flex items-center gap-2 pr-10">
        <span aria-hidden className="grid size-8 place-items-center rounded-full bg-ink text-lime"><Link2 size={16} /></span>
        <h2 className="text-xl font-bold">{t("share.title")}</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-mute">{t("share.body")}</p>
      {token ? (
        <div className="mt-5 space-y-3">
          <div className="flex gap-2">
            <label htmlFor="share-url" className="sr-only">{t("share.link")}</label>
            <input
              id="share-url" readOnly value={url} onFocus={(e) => e.currentTarget.select()}
              className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3 text-sm"
            />
            <Button onClick={copy}>{copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />} {copied ? t("share.copied") : t("share.copy")}</Button>
          </div>
          <p className="text-xs leading-relaxed text-mute">{t("share.includes")}</p>
          <Button variant="outline" size="sm" onClick={revoke} disabled={busy}>{t("share.revoke")}</Button>
        </div>
      ) : (
        <Button className="mt-5" onClick={create} disabled={busy}>
          {busy ? <Loader2 size={15} className="motion-safe:animate-spin" aria-hidden /> : <Link2 size={15} aria-hidden />} {t("share.create")}
        </Button>
      )}
    </Dialog>
  );
}
