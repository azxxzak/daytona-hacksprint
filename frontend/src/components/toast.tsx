"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertCircle, Check } from "lucide-react";

type Toast = { id: number; kind: "success" | "error"; text: string };
type Ctx = { success: (t: string) => void; error: (t: string) => void };
const ToastContext = createContext<Ctx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++seq.current;
    setItems((x) => [...x.slice(-2), { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "error" ? 6000 : 3500);
  }, []);
  const value = useMemo<Ctx>(() => ({ success: (t) => push("success", t), error: (t) => push("error", t) }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[70] flex flex-col items-center gap-2 px-4">
        {items.map((i) => (
          <div
            key={i.id}
            role={i.kind === "error" ? "alert" : "status"}
            className="toast-in pointer-events-auto flex max-w-[min(92vw,460px)] items-center gap-2.5 rounded-full bg-ink/95 py-2 pl-2 pr-5 text-sm text-white shadow-pop backdrop-blur"
          >
            <span aria-hidden className={i.kind === "success" ? "grid size-6 shrink-0 place-items-center rounded-full bg-lime text-ink" : "grid size-6 shrink-0 place-items-center rounded-full bg-[#ff6b5e] text-white"}>
              {i.kind === "success" ? <Check size={14} strokeWidth={3} /> : <AlertCircle size={14} strokeWidth={2.5} />}
            </span>
            <span>{i.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Ctx {
  const c = useContext(ToastContext);
  if (!c) throw new Error("useToast needs ToastProvider");
  return c;
}
