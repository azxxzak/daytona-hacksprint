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
            className="fade-in pointer-events-auto flex max-w-[min(92vw,460px)] items-center gap-2.5 rounded-full bg-ink py-2.5 pl-3.5 pr-5 text-sm text-white"
          >
            {i.kind === "success" ? <Check size={16} className="shrink-0 text-lime" aria-hidden /> : <AlertCircle size={16} className="shrink-0 text-lime" aria-hidden />}
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
