/** Black track, lime fill: the one place the accent gets a bit of room. */
export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(p)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-ink"
    >
      <div className="h-full rounded-full bg-lime transition-[width] duration-700 ease-out" style={{ width: `${p}%` }} />
    </div>
  );
}
