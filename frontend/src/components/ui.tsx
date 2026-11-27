"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { X } from "lucide-react";
import { useI18n } from "./i18n-provider";

export function cx(...a: (string | false | null | undefined)[]): string {
  return a.filter(Boolean).join(" ");
}

type Variant = "primary" | "outline" | "dark" | "ghost" | "lime";

const base =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap select-none transition-[color,background-color,border-color,box-shadow,transform] duration-150 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100";
const variants: Record<Variant, string> = {
  primary: "bg-ink text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_1px_2px_rgb(17_17_17/0.2)] hover:bg-black hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_6px_16px_-6px_rgb(17_17_17/0.45)] [&_svg]:text-lime",
  dark: "bg-ink/80 text-white backdrop-blur-sm hover:bg-ink [&_svg]:text-lime",
  outline: "bg-surface text-ink border border-line shadow-[0_1px_2px_rgb(17_17_17/0.05)] hover:border-ink/40 hover:shadow-[0_4px_12px_-6px_rgb(17_17_17/0.25)]",
  ghost: "text-ink hover:bg-ink/5",
  lime: "bg-lime text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.5),0_1px_2px_rgb(17_17_17/0.2)] hover:bg-[#d3f74a] hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.5),0_8px_20px_-8px_rgb(200_240_49/0.7)] disabled:bg-white/15 disabled:text-white/50 disabled:shadow-none",
};
const sizes = { sm: "h-8 px-3.5 text-[13px]", md: "h-10 px-5 text-sm", lg: "h-12 px-7 text-[15px]" };

export function buttonClass(variant: Variant = "primary", size: keyof typeof sizes = "md", extra?: string) {
  return cx(base, variants[variant], sizes[size], extra);
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof sizes }) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}

export function LinkButton({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: keyof typeof sizes;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

/** Small eyebrow with a lime tick, large title, hairline rule, optional action on the right. */
export function SectionHeader({
  label,
  title,
  action,
  as: H = "h2",
}: {
  label?: string;
  title: string;
  action?: ReactNode;
  as?: "h1" | "h2" | "h3";
}) {
  const big = H === "h1";
  return (
    <div className={cx("flex items-end justify-between gap-4 border-b border-line", big ? "pb-5" : "pb-3")}>
      <div className="min-w-0">
        {label && (
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-mute">
            <span aria-hidden className="h-2.5 w-1 rounded-full bg-lime ring-1 ring-ink/80" />
            {label}
          </p>
        )}
        <H
          className={cx(
            "font-bold leading-tight tracking-[-0.02em]",
            label && "mt-1.5",
            big ? "text-[30px] sm:text-[40px]" : H === "h2" ? "text-[22px] sm:text-[26px]" : "text-lg sm:text-xl",
          )}
        >
          {title}
        </H>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Wordmark: a black tile holding a lime "lens", then the name. */
export function Logo({ className, name = "AdLens", compact }: { className?: string; name?: string; compact?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2 text-[17px] font-bold tracking-[-0.02em]", className)}>
      <span aria-hidden className="relative grid size-7 place-items-center rounded-[9px] bg-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.15)]">
        <span className="size-3.5 rounded-full border-[2.5px] border-lime" />
        <span className="absolute right-[7px] top-[7px] size-1 rounded-full bg-white" />
      </span>
      <span className={cx(compact && "max-sm:sr-only")}>{name}</span>
    </span>
  );
}

/** Segmented control: a grey track with the chosen item lifted onto a white chip. */
export const segTrack = "flex gap-0.5 rounded-full bg-[#e7e7ea] p-1";
export function segItem(on: boolean, extra?: string) {
  return cx(
    "rounded-full px-3.5 text-[13px] font-medium transition-[color,background-color,box-shadow]",
    on ? "bg-surface text-ink shadow-[0_1px_3px_rgb(17_17_17/0.14)]" : "text-mute hover:text-ink",
    extra,
  );
}

/** Text input / textarea look shared by forms. */
export const fieldClass =
  "w-full rounded-xl border border-line bg-surface text-sm shadow-[0_1px_2px_rgb(17_17_17/0.04)] transition-[border-color,box-shadow] placeholder:text-mute/60 hover:border-[#cfcfd4] focus:border-ink";

export function Card({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("rounded-card bg-surface shadow-card", className)} {...rest} />;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-block size-4 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin", className)}
    />
  );
}

/** Soft portrait with a calm placeholder until the (possibly slow, first-time generated) image arrives. */
export function Avatar({
  src,
  name,
  color,
  className,
  rounded = "rounded-none",
  eager,
}: {
  src: string;
  name: string;
  color?: string;
  className?: string;
  rounded?: string;
  eager?: boolean;
}) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el?.complete && el.naturalWidth > 0) setState("ok");
  }, []);

  useEffect(() => {
    if (state !== "error" || attempt >= 2) return;
    const id = setTimeout(() => {
      setAttempt((a) => a + 1);
      setState("loading");
    }, 4000);
    return () => clearTimeout(id);
  }, [state, attempt]);

  const url = attempt ? `${src}${src.includes("?") ? "&" : "?"}r=${attempt}` : src;
  return (
    <div className={cx("relative overflow-hidden bg-[#e9e9ec]", rounded, className)}>
      {state !== "ok" && (
        <div
          aria-hidden
          className={cx("absolute inset-0 grid place-items-center text-lg font-medium text-mute/70", state === "loading" && "pulse")}
          style={color ? { background: `${color}14` } : undefined}
        >
          {name.slice(0, 1)}
        </div>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element -- portraits are generated by the API; next/image would re-proxy them */}
      <img
        ref={ref}
        src={url}
        alt={name}
        loading={eager ? "eager" : "lazy"}
        decoding="async"
        onLoad={() => setState("ok")}
        onError={() => setState("error")}
        className={cx("absolute inset-0 h-full w-full object-cover transition-opacity duration-500", state === "ok" ? "opacity-100" : "opacity-0")}
      />
    </div>
  );
}

/** Native <dialog>: focus trap, Escape and focus restore come from the platform. */
export function Dialog({
  open,
  onClose,
  label,
  side,
  wide,
  xl,
  children,
}: {
  open: boolean;
  onClose: () => void;
  label: string;
  side?: boolean;
  wide?: boolean;
  xl?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useI18n();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-label={label}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className={cx(
        "max-h-none bg-transparent p-0 text-ink",
        side ? cx("m-0 ml-auto h-dvh w-full", xl ? "max-w-[860px]" : "max-w-[480px]") : cx("m-auto max-w-none", wide ? "w-[min(94vw,760px)]" : "w-[min(92vw,420px)]"),
      )}
    >
      {open && (
        <div
          className={cx(
            "relative bg-surface",
            side ? "sheet h-full overflow-y-auto rounded-l-[20px] p-6 sm:p-8" : "fade-in rounded-card p-6",
          )}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="absolute right-4 top-4 grid size-9 place-items-center rounded-full text-mute hover:bg-ink/5 hover:text-ink"
          >
            <X size={18} aria-hidden />
          </button>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function ErrorNote({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-card border border-danger/25 bg-[#fdf3f2] px-4 py-3 text-sm text-danger">
      <span className="min-w-0 flex-1">{children}</span>
      {action}
    </div>
  );
}

export function useDocTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · AdLens`;
  }, [title]);
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("shimmer rounded-card", className)} />;
}
