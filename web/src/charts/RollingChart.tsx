import { useMemo, useState } from "react";
import { longDate, money, moneyCompact, parseDate } from "../lib/format";
import type { RollingPoint } from "../lib/types";
import { Tooltip, linearScale, niceTicks, useWidth } from "./primitives";

const HEIGHT = 200;
const MARGIN = { top: 12, right: 56, bottom: 28, left: 48 };

/** Single series: trailing-window daily average. Crosshair snaps to the nearest day. */
export function RollingChart({ points }: { points: RollingPoint[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const geometry = useMemo(() => {
    const plotW = Math.max(0, width - MARGIN.left - MARGIN.right);
    const baseline = HEIGHT - MARGIN.bottom;
    const ticks = niceTicks(Math.max(1, ...points.map((p) => p.daily_average)));
    const y = linearScale(ticks[ticks.length - 1], baseline, MARGIN.top);
    const x = (i: number) => MARGIN.left + (points.length > 1 ? (i / (points.length - 1)) * plotW : plotW / 2);
    const coords = points.map((p, i) => [x(i), y(p.daily_average)] as const);
    const toPath = (pts: (readonly [number, number])[]) =>
      pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
    // Days before a full window exists are drawn faintly: the average is still warming up.
    const firstComplete = Math.max(0, points.findIndex((p) => p.complete_window));
    const warmup = coords.slice(0, firstComplete + 1);
    const steady = coords.slice(firstComplete);
    const area = steady.length
      ? `${toPath(steady)}L${steady[steady.length - 1][0]},${baseline}L${steady[0][0]},${baseline}Z`
      : "";
    const monthTicks = points
      .map((p, i) => ({ i, d: parseDate(p.date) }))
      .filter(({ d }) => d.getDate() === 1);
    return { plotW, baseline, ticks, y, x, coords, warmupPath: toPath(warmup), steadyPath: toPath(steady), area, monthTicks };
  }, [points, width]);

  if (!points.length) return <p className="py-12 text-center text-sm text-muted">No spending in this range.</p>;

  const { baseline, ticks, y, x, coords, warmupPath, steadyPath, area, monthTicks } = geometry;
  const last = points[points.length - 1];
  const [lastX, lastY] = coords[coords.length - 1] ?? [0, 0];
  const everyOther = monthTicks.length > 8;

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    setHover(Math.round(Math.min(1, Math.max(0, ratio)) * (points.length - 1)));
  }

  const hovered = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-label="Rolling average daily spending">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
              <text x={MARGIN.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-muted text-[11px]">
                {moneyCompact(t)}
              </text>
            </g>
          ))}
          {monthTicks.map(({ i, d }, n) =>
            everyOther && n % 2 ? null : (
              <text key={i} x={x(i)} y={baseline + 18} textAnchor="middle" className="fill-muted text-[11px]">
                {d.toLocaleDateString("en-US", { month: "short" })}
              </text>
            ),
          )}
          <line x1={MARGIN.left} x2={width - MARGIN.right} y1={baseline} y2={baseline} stroke="var(--axis)" />
          <path d={area} fill="var(--series-1)" opacity={0.1} />
          <path d={warmupPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" opacity={0.35} />
          <path d={steadyPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {/* Direct label on the endpoint only. */}
          <circle cx={lastX} cy={lastY} r={4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
          <text x={lastX + 8} y={lastY} dy="0.32em" className="num fill-ink text-xs font-semibold">
            {moneyCompact(last.daily_average)}
          </text>
          {hovered && hover !== null && (
            <g pointerEvents="none">
              <line x1={coords[hover][0]} x2={coords[hover][0]} y1={MARGIN.top} y2={baseline} stroke="var(--axis)" />
              <circle cx={coords[hover][0]} cy={coords[hover][1]} r={4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
            </g>
          )}
          <rect
            x={MARGIN.left}
            y={MARGIN.top}
            width={Math.max(0, width - MARGIN.left - MARGIN.right)}
            height={baseline - MARGIN.top}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
      )}
      {hovered && hover !== null && (
        <Tooltip
          x={coords[hover][0]}
          y={MARGIN.top}
          containerWidth={width}
          title={longDate(hovered.date)}
          rows={[
            { label: "per day", value: money(hovered.daily_average), color: "var(--series-1)" },
            { label: "in window", value: money(hovered.window_total) },
          ]}
        />
      )}
    </div>
  );
}
