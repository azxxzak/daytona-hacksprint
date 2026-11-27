"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, Info } from "lucide-react";
import { cx } from "./ui";

export type SelectOption = { value: string; label: string; hint?: string; disabled?: boolean };

const triggers = {
  pill: "h-9 rounded-full border border-line bg-surface pl-3.5 pr-2.5 text-[13px] font-medium hover:border-[#cfcfd4]",
  field: "h-10 w-full rounded-xl border border-line bg-canvas pl-3 pr-2.5 text-sm hover:border-[#cfcfd4]",
};

/** Styled single-choice listbox (replaces the native <select>, which renders as an OS menu).
    Keyboard: arrows / Home / End move, Enter or Space picks, Escape closes, typing jumps to a matching item. */
export function Select({
  value,
  options,
  onChange,
  label,
  placeholder,
  variant = "pill",
  className,
  align = "start",
}: {
  value: string;
  options: SelectOption[];
  onChange: (v: string) => void;
  /** accessible name when there is no visible <label> pointing at the trigger */
  label?: string;
  placeholder?: string;
  variant?: keyof typeof triggers;
  className?: string;
  align?: "start" | "end";
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [up, setUp] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const typed = useRef({ s: "", at: 0 });
  const current = options.find((o) => o.value === value);

  const enabled = (i: number) => i >= 0 && i < options.length && !options[i].disabled;
  const step = (from: number, dir: 1 | -1) => {
    for (let i = from + dir, n = 0; n < options.length; i += dir, n++) {
      const j = (i + options.length) % options.length;
      if (enabled(j)) return j;
    }
    return from;
  };
  const show = (at?: number) => {
    const sel = options.findIndex((o) => o.value === value);
    setActive(at ?? (enabled(sel) ? sel : step(-1, 1)));
    setOpen(true);
  };
  const close = (focus = true) => {
    setOpen(false);
    if (focus) btn.current?.focus();
  };
  const pick = (i: number) => {
    if (!enabled(i)) return;
    if (options[i].value !== value) onChange(options[i].value);
    close();
  };

  // open upward when there is no room below
  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const r = btn.current.getBoundingClientRect();
    const h = Math.min(288, options.length * 40 + 8);
    setUp(window.innerHeight - r.bottom < h + 12 && r.top > h + 12);
    list.current?.focus({ preventScroll: true });
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) close(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  useEffect(() => {
    if (open && active >= 0) list.current?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const onListKey = (e: React.KeyboardEvent) => {
    const k = e.key;
    if (k === "ArrowDown") setActive((a) => step(a, 1));
    else if (k === "ArrowUp") setActive((a) => step(a, -1));
    else if (k === "Home") setActive(step(-1, 1));
    else if (k === "End") setActive(step(options.length, -1));
    else if (k === "Enter" || k === " ") pick(active);
    else if (k === "Escape") close();
    else if (k === "Tab") { setOpen(false); return; }
    else if (k.length === 1 && !e.metaKey && !e.ctrlKey) {
      const now = Date.now();
      typed.current = { s: (now - typed.current.at < 700 ? typed.current.s : "") + k.toLowerCase(), at: now };
      const i = options.findIndex((o, j) => enabled(j) && o.label.toLowerCase().startsWith(typed.current.s));
      if (i >= 0) setActive(i);
    } else return;
    e.preventDefault();
  };

  return (
    <div ref={wrap} className={cx("relative", variant === "field" && "min-w-0 flex-1", className)}>
      <button
        ref={btn}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        aria-label={label ? `${label}: ${current?.label ?? placeholder ?? ""}` : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); show(); }
        }}
        className={cx("flex items-center gap-2 text-left transition-colors", triggers[variant], open && "border-ink")}
      >
        <span className={cx("min-w-0 flex-1 truncate", !current && "text-mute")}>{current?.label ?? placeholder}</span>
        <ChevronDown size={15} aria-hidden className={cx("shrink-0 text-mute transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <ul
          ref={list}
          id={`${id}-list`}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
          onKeyDown={onListKey}
          className={cx(
            "pop absolute z-40 max-h-72 min-w-full overflow-y-auto overscroll-contain rounded-2xl bg-surface p-1 shadow-pop outline-none",
            up ? "bottom-full mb-1.5 origin-bottom" : "top-full mt-1.5 origin-top",
            align === "end" ? "right-0" : "left-0",
            variant === "pill" && "w-max max-w-[min(20rem,calc(100vw-2rem))]",
          )}
        >
          {options.map((o, i) => {
            const selected = o.value === value;
            return (
              <li
                key={o.value}
                id={`${id}-${i}`}
                data-i={i}
                role="option"
                aria-selected={selected}
                aria-disabled={o.disabled || undefined}
                onPointerMove={() => enabled(i) && active !== i && setActive(i)}
                onClick={() => pick(i)}
                className={cx(
                  "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-[13px] leading-snug",
                  i === active && "bg-canvas",
                  selected && "font-semibold",
                  o.disabled && "cursor-not-allowed opacity-40",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{o.label}</span>
                  {o.hint && <span className="block truncate text-xs font-normal text-mute">{o.hint}</span>}
                </span>
                <Check size={15} aria-hidden className={cx("shrink-0", selected ? "text-ink" : "invisible")} />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Small "i" that explains something: shows on hover or focus, toggles on tap (touch has no hover). */
export function InfoTip({ children, label, align = "start" }: { children: ReactNode; label: string; align?: "start" | "end" }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const wrap = useRef<HTMLSpanElement>(null);
  const later = (v: boolean) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(v), v ? 120 : 160);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const away = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", esc);
    document.addEventListener("pointerdown", away);
    return () => { document.removeEventListener("keydown", esc); document.removeEventListener("pointerdown", away); };
  }, [open]);
  return (
    <span ref={wrap} className="relative inline-flex" onPointerEnter={(e) => e.pointerType === "mouse" && later(true)} onPointerLeave={(e) => e.pointerType === "mouse" && later(false)}>
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onFocus={() => later(true)}
        onBlur={() => later(false)}
        className={cx("grid size-7 place-items-center rounded-full text-mute transition-colors hover:bg-surface hover:text-ink", open && "bg-surface text-ink")}
      >
        <Info size={15} aria-hidden />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={cx(
            "pop absolute top-full z-40 mt-1.5 w-[min(20rem,calc(100vw-2rem))] origin-top rounded-xl bg-ink px-3.5 py-3 text-xs leading-relaxed text-white shadow-pop",
            align === "start" ? "left-0" : "right-0",
          )}
        >
          {children}
        </span>
      )}
    </span>
  );
}
