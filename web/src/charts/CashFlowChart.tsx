import { useState } from "react";
import { money, moneyCompact, monthLabel, moneyWhole, signedMoney } from "../lib/format";
import type { MonthSummary } from "../lib/types";
import { Legend, Tooltip, columnPath, linearScale, niceTicks, useWidth } from "./primitives";

const HEIGHT = 240;
const MARGIN = { top: 8, right: 0, bottom: 28, left: 48 };
const MAX_BAR = 24;
const BAR_GAP = 2;

interface Props {
  months: MonthSummary[];
  selectedMonth: string | null;
  onSelectMonth: (month: string) => void;
}

/** Grouped columns: income vs spending per month. One $ axis — net lives in the tooltip and table. */
export function CashFlowChart({ months, selectedMonth, onSelectMonth }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const ticks = niceTicks(Math.max(1, ...months.flatMap((m) => [m.income, m.expenses])));
  const top = ticks[ticks.length - 1];
  const plotW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const baseline = HEIGHT - MARGIN.bottom;
  const y = linearScale(top, baseline, MARGIN.top);
  const band = months.length ? plotW / months.length : 0;
  const bar = Math.min(MAX_BAR, Math.max(4, (band * 0.6 - BAR_GAP) / 2));
  const showEveryLabel = band >= 36;

  const hovered = hover !== null ? months[hover] : null;

  return (
    <div>
      <Legend
        items={[
          { label: "Income", color: "var(--series-1)" },
          { label: "Spending", color: "var(--series-2)" },
        ]}
      />
      <div ref={ref} className="relative mt-4" onPointerLeave={() => setHover(null)}>
        {width > 0 && (
          <svg width={width} height={HEIGHT} role="img" aria-label="Monthly income and spending">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={MARGIN.left} x2={width} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
                <text x={MARGIN.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-muted text-[11px]">
                  {moneyCompact(t)}
                </text>
              </g>
            ))}
            {months.map((m, i) => {
              const cx = MARGIN.left + band * i + band / 2;
              const dimmed = selectedMonth !== null && selectedMonth !== m.month;
              return (
                <g
                  key={m.month}
                  tabIndex={0}
                  role="button"
                  aria-label={`${monthLabel(m.month, true)}: income ${money(m.income)}, spending ${money(m.expenses)}`}
                  className="cursor-pointer outline-none"
                  onPointerEnter={() => setHover(i)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  onClick={() => onSelectMonth(m.month)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelectMonth(m.month)}
                  opacity={dimmed ? 0.35 : 1}
                >
                  {/* Hit target is the whole month band, not just the painted bars. */}
                  <rect
                    x={MARGIN.left + band * i}
                    y={MARGIN.top}
                    width={band}
                    height={baseline - MARGIN.top}
                    fill={hover === i ? "var(--surface-sunken)" : "transparent"}
                  />
                  <path d={columnPath(cx - bar - BAR_GAP / 2, y(m.income), bar, baseline)} fill="var(--series-1)" />
                  <path d={columnPath(cx + BAR_GAP / 2, y(Math.max(0, m.expenses)), bar, baseline)} fill="var(--series-2)" />
                  {(showEveryLabel || i % 2 === 0) && (
                    <text x={cx} y={baseline + 18} textAnchor="middle" className="fill-muted text-[11px]">
                      {monthLabel(m.month)}
                    </text>
                  )}
                </g>
              );
            })}
            <line x1={MARGIN.left} x2={width} y1={baseline} y2={baseline} stroke="var(--axis)" />
          </svg>
        )}
        {hovered && hover !== null && (
          <Tooltip
            x={MARGIN.left + band * hover + band / 2}
            y={MARGIN.top}
            containerWidth={width}
            title={monthLabel(hovered.month, true)}
            rows={[
              { label: "Income", value: moneyWhole(hovered.income), color: "var(--series-1)" },
              { label: "Spending", value: moneyWhole(hovered.expenses), color: "var(--series-2)" },
              { label: "Net", value: signedMoney(hovered.net_cash_flow) },
            ]}
          />
        )}
      </div>
    </div>
  );
}

/** The same data as a table — the chart's accessible, tooltip-free view. */
export function CashFlowTable({ months }: { months: MonthSummary[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted">
          <th className="py-2 font-medium">Month</th>
          <th className="py-2 text-right font-medium">Income</th>
          <th className="py-2 text-right font-medium">Spending</th>
          <th className="py-2 text-right font-medium">Net</th>
          <th className="py-2 text-right font-medium">Saved</th>
        </tr>
      </thead>
      <tbody className="num">
        {months.map((m) => (
          <tr key={m.month} className="border-t border-hairline">
            <td className="py-2 text-ink-2">{monthLabel(m.month, true)}</td>
            <td className="py-2 text-right">{money(m.income)}</td>
            <td className="py-2 text-right">{money(m.expenses)}</td>
            <td className={`py-2 text-right font-medium ${m.net_cash_flow < 0 ? "text-critical-ink" : "text-ink"}`}>
              {signedMoney(m.net_cash_flow)}
            </td>
            <td className="py-2 text-right text-ink-2">
              {m.savings_rate === null ? "—" : `${(m.savings_rate * 100).toFixed(1)}%`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
