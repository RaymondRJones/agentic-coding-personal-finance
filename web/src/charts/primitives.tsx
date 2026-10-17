import { type ReactNode, useCallback, useRef, useState } from "react";

/** Round a max value up to a clean axis top and return evenly spaced ticks (0, 5K, 10K…). */
export function niceTicks(max: number, target = 4): number[] {
  if (max <= 0) return [0];
  const rough = max / target;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const ticks: number[] = [];
  for (let t = 0; t <= max + step * 0.001; t += step) ticks.push(t);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

export function linearScale(domainMax: number, rangeStart: number, rangeEnd: number) {
  return (value: number) => rangeStart + (value / (domainMax || 1)) * (rangeEnd - rangeStart);
}

/**
 * Track an element's content width so SVG charts can lay out in real pixels.
 * A callback ref (not useRef + effect) so it still works when the element mounts
 * on a later render, e.g. after an early "no data" return.
 */
export function useWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el) return;
    setWidth(Math.floor(el.getBoundingClientRect().width));
    observer.current = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.current.observe(el);
  }, []);
  return [ref, width] as const;
}

/**
 * Column path with a 4px rounded data-end and a square baseline.
 * `y` is the top of the column, `baseline` its bottom.
 */
export function columnPath(x: number, y: number, width: number, baseline: number, radius = 4): string {
  const h = baseline - y;
  if (h <= 0) return "";
  const r = Math.min(radius, width / 2, h);
  return [
    `M${x},${baseline}`,
    `V${y + r}`,
    `Q${x},${y} ${x + r},${y}`,
    `H${x + width - r}`,
    `Q${x + width},${y} ${x + width},${y + r}`,
    `V${baseline}`,
    "Z",
  ].join(" ");
}

export interface TooltipRow {
  label: string;
  value: string;
  color?: string; // line-key color; omit for derived rows (e.g. net)
}

/** Values lead, labels follow; rows are keyed with a short line in the series color. */
export function Tooltip({ x, y, title, rows, containerWidth }: {
  x: number;
  y: number;
  title: string;
  rows: TooltipRow[];
  containerWidth: number;
}) {
  const flip = x > containerWidth - 200;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 min-w-40 rounded-lg bg-surface px-3 py-2.5 shadow-pop"
      style={{ left: flip ? undefined : x + 12, right: flip ? containerWidth - x + 12 : undefined, top: y }}
    >
      <p className="text-xs font-medium text-muted">{title}</p>
      <dl className="mt-1.5 space-y-1">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-2">
            <span
              aria-hidden
              className="h-0.5 w-3 rounded-full"
              style={{ background: row.color ?? "transparent" }}
            />
            <dd className="num text-sm font-semibold text-ink">{row.value}</dd>
            <dt className="text-xs text-ink-2">{row.label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "rect" | "line" }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-xs text-ink-2">
          <span
            aria-hidden
            className={item.shape === "line" ? "h-0.5 w-3 rounded-full" : "size-2.5 rounded-sm"}
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function ChartFrame({ loading, children }: { loading: boolean; children: ReactNode }) {
  return <div className={`transition-opacity duration-200 ${loading ? "opacity-50" : ""}`}>{children}</div>;
}
