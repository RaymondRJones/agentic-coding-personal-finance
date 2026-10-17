import { useEffect, useState } from "react";
import { longDate, monthLabel, parseDate, toIso } from "../lib/format";
import type { Filters, Meta } from "../lib/types";

type Preset = "all" | "6m" | "3m" | "30d";

const PRESETS: { value: Preset; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "6m", label: "6 months" },
  { value: "3m", label: "3 months" },
  { value: "30d", label: "30 days" },
];

/** Presets are relative to the data's last day, not today — the dataset may be historical. */
export function presetRange(preset: Preset, lastDate: string): [string | null, string | null] {
  if (preset === "all") return [null, null];
  const end = parseDate(lastDate);
  if (preset === "30d") return [toIso(new Date(end.getFullYear(), end.getMonth(), end.getDate() - 29)), lastDate];
  const months = preset === "6m" ? 6 : 3;
  return [toIso(new Date(end.getFullYear(), end.getMonth() - months + 1, 1)), lastDate];
}

function activePreset(filters: Filters, lastDate: string): Preset | null {
  for (const { value } of PRESETS) {
    const [start, end] = presetRange(value, lastDate);
    if (filters.start === start && filters.end === end) return value;
  }
  return null;
}

/** One row above everything it scopes: date range first, then dimensions. */
export function FilterBar({ meta, filters, onChange }: {
  meta: Meta;
  filters: Filters;
  onChange: (patch: Partial<Filters>) => void;
}) {
  const preset = activePreset(filters, meta.last_date);
  const [merchant, setMerchant] = useState(filters.merchant);

  // Debounce typing so every keystroke doesn't refetch the whole dashboard.
  useEffect(() => {
    if (merchant === filters.merchant) return;
    const id = setTimeout(() => onChange({ merchant }), 250);
    return () => clearTimeout(id);
  }, [merchant, filters.merchant, onChange]);
  useEffect(() => setMerchant(filters.merchant), [filters.merchant]);

  const toggleAccount = (id: string) =>
    onChange({
      accounts: filters.accounts.includes(id) ? filters.accounts.filter((a) => a !== id) : [...filters.accounts, id],
    });

  const customLabel =
    preset === null && filters.start && filters.end ? rangeLabel(filters.start, filters.end) : null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
      <div role="radiogroup" aria-label="Date range" className="inline-flex rounded-lg bg-surface p-0.5 shadow-card">
        {PRESETS.map((p) => {
          const selected = preset === p.value;
          return (
            <button
              key={p.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => {
                const [start, end] = presetRange(p.value, meta.last_date);
                onChange({ start, end });
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                selected ? "bg-accent-soft text-accent-ink" : "text-ink-2 hover:bg-sunken hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          );
        })}
        {customLabel && (
          <span className="rounded-md bg-accent-soft px-3 py-1.5 text-sm font-medium text-accent-ink">{customLabel}</span>
        )}
      </div>

      <div className="inline-flex items-center gap-2 rounded-lg bg-surface px-3 py-1.5 shadow-card">
        <label className="sr-only" htmlFor="start">Start date</label>
        <input
          id="start"
          type="date"
          value={filters.start ?? ""}
          min={meta.first_date}
          max={filters.end ?? meta.last_date}
          onChange={(e) => onChange({ start: e.target.value || null })}
          className="num bg-transparent text-sm text-ink outline-none"
        />
        <span className="text-muted">–</span>
        <label className="sr-only" htmlFor="end">End date</label>
        <input
          id="end"
          type="date"
          value={filters.end ?? ""}
          min={filters.start ?? meta.first_date}
          max={meta.last_date}
          onChange={(e) => onChange({ end: e.target.value || null })}
          className="num bg-transparent text-sm text-ink outline-none"
        />
      </div>

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Accounts">
        {meta.accounts.map((account) => {
          const on = filters.accounts.includes(account.id);
          return (
            <button
              key={account.id}
              type="button"
              aria-pressed={on}
              onClick={() => toggleAccount(account.id)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                on ? "bg-ink text-surface" : "bg-surface text-ink-2 shadow-card hover:text-ink"
              }`}
            >
              {account.name}
            </button>
          );
        })}
      </div>

      <select
        aria-label="Category"
        value={filters.category ?? ""}
        onChange={(e) => onChange({ category: e.target.value || null })}
        className="rounded-lg bg-surface px-3 py-1.5 text-sm text-ink shadow-card outline-none"
      >
        <option value="">All categories</option>
        {meta.categories.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      <input
        type="search"
        aria-label="Search merchants"
        placeholder="Search merchants"
        value={merchant}
        onChange={(e) => setMerchant(e.target.value)}
        className="w-44 rounded-lg bg-surface px-3 py-1.5 text-sm text-ink shadow-card outline-none placeholder:text-muted"
      />

      <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-ink-2">
        <input
          type="checkbox"
          checked={filters.dropDuplicates}
          onChange={(e) => onChange({ dropDuplicates: e.target.checked })}
          className="size-4 accent-[var(--accent)]"
        />
        Exclude likely duplicates
      </label>
    </div>
  );
}

function rangeLabel(start: string, end: string): string {
  const [sy, sm, sd] = start.split("-");
  const lastDay = new Date(Number(sy), Number(sm), 0).getDate();
  if (sd === "01" && end === `${sy}-${sm}-${String(lastDay).padStart(2, "0")}`) {
    return monthLabel(`${sy}-${sm}`, true);
  }
  return `${longDate(start)} – ${longDate(end)}`;
}
