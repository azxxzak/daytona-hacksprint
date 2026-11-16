"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, LogOut, User } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LANGS, type Lang } from "@/lib/i18n";
import { useI18n } from "./i18n-provider";
import { cx } from "./ui";

type Me = { email: string; name: string };
const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  const labels: Record<Lang, string> = { en: "EN", ja: "日本語" };
  return (
    <div role="group" aria-label={t("nav.language")} className={cx("flex items-center rounded-full border border-line bg-surface p-0.5", className)}>
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={lang === l}
          onClick={() => setLang(l)}
          className={cx(
            "h-7 rounded-full px-3 text-xs font-medium transition-colors",
            lang === l ? "bg-ink text-white" : "text-mute hover:text-ink",
          )}
        >
          {labels[l]}
        </button>
      ))}
    </div>
  );
}

function AccountMenu({ me }: { me: Me }) {
  const { t } = useI18n();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const usage = useApi<{ month_usd: number }>(open ? "/api/usage" : null);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const signOut = async () => {
    try {
      await api("/api/auth/logout", { method: "POST", noRedirect: true });
    } catch {
      /* leaving anyway */
    }
    router.replace("/login");
  };

  return (
    <div ref={wrap} className="relative">
      <button
        ref={btn}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("nav.account")}
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 items-center gap-1 rounded-full border border-line bg-surface pl-2.5 pr-2 text-mute hover:text-ink"
      >
        <User size={16} aria-hidden />
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-11 z-40 w-64 rounded-card border border-line bg-surface p-2">
          <p className="truncate px-3 py-2 text-sm text-mute" title={me.email}>
            {me.email}
          </p>
          {usage.data && (
            <p className="tnum px-3 pb-2 text-sm">{t("nav.usage", { v: "$" + usage.data.month_usd.toFixed(2) })}</p>
          )}
          <button
            type="button"
            role="menuitem"
            autoFocus
            onClick={signOut}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm hover:bg-canvas"
          >
            <LogOut size={16} aria-hidden /> {t("nav.signOut")}
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { data: me } = useApi<Me>("/api/auth/me");
  const path = usePathname();

  return (
    <MeContext.Provider value={me}>
      <header className="sticky top-0 z-30 border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-4 sm:px-8">
          <div className="flex items-center gap-5 sm:gap-8">
            <Link href="/" className="text-[17px] font-bold tracking-tight">
              {t("app.name")}
            </Link>
            <nav aria-label={t("nav.main")} className="flex items-center gap-1">
              {[
                { href: "/", label: t("nav.tests"), on: path === "/" || path.startsWith("/tests") },
                { href: "/library", label: t("nav.library"), on: path.startsWith("/library") },
              ].map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={n.on ? "page" : undefined}
                  className={cx("rounded-full px-3 py-1 text-sm font-medium transition-colors", n.on ? "bg-ink text-white" : "text-mute hover:text-ink")}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <LangSwitch />
            {me && <AccountMenu me={me} />}
          </div>
        </div>
      </header>
      {me ? (
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-32 pt-8 sm:px-8">{children}</main>
      ) : (
        <div className="grid h-[60vh] place-items-center text-mute" role="status" aria-label={t("common.loading")}>
          <span className="pulse text-sm">{t("common.loading")}</span>
        </div>
      )}
    </MeContext.Provider>
  );
}
