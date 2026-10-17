import { moneyWhole } from "../lib/format";

export interface BarItem {
  key: string;
  label: string;
  value: number;
  detail?: string;
}

/**
 * Ranked horizontal bars, one series color. Bars grow from a square baseline to a 4px
 * rounded tip with the value right after it. The longest bar stops at 75% of the
 * track so its value label always has room.
 */
export function BarList({ items, total, selected, onSelect }: {
  items: BarItem[];
  total: number;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const share = total > 0 ? item.value / total : 0;
        const dimmed = selected != null && selected !== item.key;
        const content = (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-sm font-medium text-ink">{item.label}</span>
              <span className="num shrink-0 text-xs text-muted">
                {item.detail ?? `${(share * 100).toFixed(1)}%`}
              </span>
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <span
                className="h-2.5 rounded-r-[4px] bg-series-1"
                style={{ width: `${Math.max(0.5, (item.value / max) * 75)}%` }}
              />
              <span className="num text-xs font-medium text-ink-2">{moneyWhole(item.value)}</span>
            </div>
          </>
        );
        return (
          <li key={item.key} className={`transition-opacity ${dimmed ? "opacity-40" : ""}`}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(item.key)}
                aria-pressed={selected === item.key}
                className="-mx-2 block w-[calc(100%+1rem)] rounded-lg px-2 py-1 text-left hover:bg-sunken"
              >
                {content}
              </button>
            ) : (
              <div className="py-1">{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
