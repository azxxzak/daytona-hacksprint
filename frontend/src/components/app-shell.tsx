"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, LogOut, User } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LANGS, type Lang } from "@/lib/i18n";
import { useI18n } from "./i18n-provider";
import { Logo, cx } from "./ui";

type Me = { email: string; name: string };
const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  const labels: Record<Lang, string> = { en: "EN", ja: "日本語" };
  return (
    <div role="group" aria-label={t("nav.language")} className={cx("flex items-center rounded-full bg-canvas p-0.5", className)}>
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={lang === l}
          onClick={() => setLang(l)}
          className={cx(
            "h-7 whitespace-nowrap rounded-full px-2.5 text-xs font-medium transition-colors sm:px-3",
            lang === l ? "bg-surface text-ink shadow-[0_1px_3px_rgb(17_17_17/0.12)]" : "text-mute hover:text-ink",
          )}
        >
          {l === "ja" ? <><span className="sm:hidden" aria-hidden>JA</span><span className="max-sm:sr-only">{labels[l]}</span></> : labels[l]}
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
    const onDown = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
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
        className={cx("flex h-9 items-center gap-1.5 rounded-full border bg-surface pl-1 pr-1 text-mute transition-colors hover:text-ink sm:pr-2", open ? "border-ink" : "border-line")}
      >
        <span aria-hidden className="grid size-7 place-items-center rounded-full bg-ink text-[12px] font-bold uppercase text-lime">
          {(me.name || me.email).trim().slice(0, 1) || <User size={14} />}
        </span>
        <ChevronDown size={14} aria-hidden className={cx("transition-transform duration-200 max-sm:hidden", open && "rotate-180")} />
      </button>
      {open && (
        <div role="menu" className="pop absolute right-0 top-11 z-40 w-64 origin-top-right rounded-2xl bg-surface p-1.5 shadow-pop">
          <div className="px-3 pb-2.5 pt-2">
            {me.name && <p className="truncate text-sm font-semibold">{me.name}</p>}
            <p className="truncate text-xs text-mute" title={me.email}>{me.email}</p>
          </div>
          {usage.data && (
            <p className="tnum mx-1.5 mb-1.5 flex items-center justify-between rounded-xl bg-canvas px-3 py-2 text-xs text-mute">
              {t("nav.usage", { v: "$" + usage.data.month_usd.toFixed(2) })}
            </p>
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
      <header className="sticky top-0 z-30 border-b border-line/70 bg-surface/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between gap-2 px-4 sm:px-8">
          <div className="flex items-center gap-3 sm:gap-8">
            <Link href="/" aria-label={t("app.name")} className="rounded-lg">
              <Logo name={t("app.name")} compact />
            </Link>
            <nav aria-label={t("nav.main")} className="flex items-center gap-0.5 rounded-full bg-canvas p-0.5">
              {[
                { href: "/", label: t("nav.tests"), on: path === "/" || path.startsWith("/tests") },
                { href: "/library", label: t("nav.library"), on: path.startsWith("/library") },
              ].map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={n.on ? "page" : undefined}
                  className={cx("whitespace-nowrap rounded-full px-3 py-1 text-[13px] font-medium transition-colors sm:px-3.5", n.on ? "bg-surface text-ink shadow-[0_1px_3px_rgb(17_17_17/0.12)]" : "text-mute hover:text-ink")}
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
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-32 pt-8 sm:px-8 sm:pt-10">{children}</main>
      ) : (
        <div className="grid h-[60vh] place-items-center text-mute" role="status" aria-label={t("common.loading")}>
          <span className="flex items-center gap-2.5 text-sm">
            <span aria-hidden className="flex gap-1">
              {[0, 1, 2].map((i) => <span key={i} className="dot-bounce size-1.5 rounded-full bg-ink" style={{ animationDelay: `${i * 0.15}s` }} />)}
            </span>
            {t("common.loading")}
          </span>
        </div>
      )}
    </MeContext.Provider>
  );
}
