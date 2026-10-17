import { useCallback, useEffect, useState } from "react";
import { CashFlowChart, CashFlowTable } from "./charts/CashFlowChart";
import { ChartFrame } from "./charts/primitives";
import { RollingChart } from "./charts/RollingChart";
import { BarList } from "./components/BarList";
import { DataQuality } from "./components/DataQuality";
import { FilterBar } from "./components/FilterBar";
import { RecurringCharges } from "./components/RecurringCharges";
import { TransactionsTable } from "./components/TransactionsTable";
import { ArrowDown, ArrowUp, Badge, Card, EmptyState, Segmented, Stat } from "./components/ui";
import { apiUrl, filterParams, useApi } from "./lib/api";
import { longDate, money, monthBounds, monthLabel, moneyWhole, pct } from "./lib/format";
import type { Filters, Meta, Rolling, Summary } from "./lib/types";

const DEFAULT_FILTERS: Filters = {
  start: null,
  end: null,
  accounts: [],
  category: null,
  merchant: "",
  dropDuplicates: true,
};

/** Filters live in the URL so any view can be bookmarked or shared. */
function readFilters(): Filters {
  const q = new URLSearchParams(window.location.search);
  return {
    start: q.get("start"),
    end: q.get("end"),
    accounts: q.getAll("account"),
    category: q.get("category"),
    merchant: q.get("merchant") ?? "",
    dropDuplicates: q.get("drop_duplicates") !== "false",
  };
}

export default function App() {
  const meta = useApi<Meta>(apiUrl("meta"));
  const [filters, setFilters] = useState<Filters>(readFilters);
  const [view, setView] = useState<"chart" | "table">("chart");
  const update = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), []);

  useEffect(() => {
    const params = filterParams(filters);
    if (filters.dropDuplicates) params.delete("drop_duplicates");
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, [filters]);

  const params = filterParams(filters);
  const ready = meta.data !== null;
  const summaryParams = new URLSearchParams(params);
  summaryParams.set("top", "8");
  const summary = useApi<Summary>(ready ? apiUrl("summary", summaryParams) : null);
  const rolling = useApi<Rolling>(ready ? apiUrl("rolling", params) : null);

  if (meta.error) return <ApiDown message={meta.error} />;
  if (!meta.data || !summary.data) return <Loading />;

  const s = summary.data;
  const t = s.totals;
  const selectedMonth =
    s.months.find((m) => {
      const [start, end] = monthBounds(m.month);
      return filters.start === start && filters.end === end;
    })?.month ?? null;

  const selectMonth = (month: string) => {
    if (month === selectedMonth) return update({ start: null, end: null });
    const [start, end] = monthBounds(month);
    update({ start, end });
  };

  const categories = Object.entries(t.spending_by_category)
    .filter(([, v]) => v !== 0) // a category can net negative when refunds exceed purchases
    .map(([k, v]) => ({ key: k, label: k, value: v }));
  const merchants = t.top_merchants.map((m) => ({
    key: m.merchant,
    label: m.merchant,
    value: m.total,
    detail: `${plural(m.purchases, "purchase")}${m.refunds ? ` · ${plural(m.refunds, "refund")}` : ""}`,
  }));
  const lastRolling = rolling.data?.points.at(-1);
  const naiveSpending = t.gross_spend + t.internal_transfers_excluded + t.unmatched_transfers_excluded;
  const filtered = JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS);
  const rangeText = `${longDate(filters.start ?? meta.data.first_date)} – ${longDate(filters.end ?? meta.data.last_date)}`;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Household finances</h1>
          <p className="mt-1 text-sm text-ink-2">
            {rangeText} · {filters.accounts.length || meta.data.accounts.length} of {meta.data.accounts.length} accounts
          </p>
        </div>
        {filtered && (
          <button
            type="button"
            onClick={() => setFilters(DEFAULT_FILTERS)}
            className="text-sm font-medium text-accent-ink hover:underline"
          >
            Clear filters
          </button>
        )}
      </header>

      <div className="sticky top-0 z-20 -mx-4 mb-6 bg-page/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <FilterBar meta={meta.data} filters={filters} onChange={update} />
      </div>

      {summary.error && (
        <p className="mb-6 rounded-lg bg-critical-soft px-4 py-3 text-sm text-critical-ink">{summary.error}</p>
      )}

      <div className={`grid items-start gap-6 transition-opacity lg:grid-cols-3 ${summary.loading ? "opacity-60" : ""}`}>
        <Card className="lg:col-span-2">
          <p className="text-sm text-ink-2">Net cash flow</p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <p className="text-5xl font-semibold tracking-tight text-ink">
              {t.net_cash_flow < 0 ? "−" : ""}
              {moneyWhole(Math.abs(t.net_cash_flow))}
            </p>
            {t.savings_rate !== null &&
              (t.savings_rate >= 0 ? (
                <Badge tone="good" icon={<ArrowUp />}>Saved {pct(t.savings_rate)} of income</Badge>
              ) : (
                <Badge tone="critical" icon={<ArrowDown />}>Spent {pct(-t.savings_rate)} more than earned</Badge>
              ))}
          </div>
          <div className="mt-8 grid gap-6 border-t border-hairline pt-6 sm:grid-cols-3">
            <Stat label="Income" value={moneyWhole(t.income)} />
            <Stat
              label="Spending"
              value={moneyWhole(t.expenses)}
              detail={t.refunds > 0 ? `${moneyWhole(t.gross_spend)} purchases − ${moneyWhole(t.refunds)} refunds` : undefined}
            />
            <Stat
              label="Daily spending, last 30 days"
              value={lastRolling ? money(lastRolling.daily_average) : "—"}
              detail={lastRolling ? `as of ${longDate(lastRolling.date)}` : undefined}
            />
          </div>
        </Card>

        <Card className="border-l-4 border-accent">
          <p className="text-sm font-semibold text-ink">Not double counted</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-ink">{moneyWhole(t.internal_transfers_excluded)}</p>
          <p className="mt-1 text-sm text-ink-2">moved between your own accounts</p>
          {t.internal_transfers_excluded > 0 ? (
            <p className="mt-4 text-sm leading-relaxed text-ink-2">
              Credit card payments and savings transfers aren't spending. The purchases on the card already are.
              Adding up every outflow would have reported{" "}
              <span className="font-medium text-ink">{moneyWhole(naiveSpending)}</span> of spending instead of{" "}
              <span className="font-medium text-ink">{moneyWhole(t.expenses)}</span>.
            </p>
          ) : (
            <p className="mt-4 text-sm leading-relaxed text-ink-2">
              No transfers between your accounts in this view, so there was nothing to exclude.
            </p>
          )}
        </Card>

        <Card
          className="lg:col-span-2"
          title="Cash flow by month"
          description="Select a month to focus the dashboard on it."
          actions={
            <Segmented
              label="View"
              value={view}
              onChange={setView}
              options={[
                { value: "chart", label: "Chart" },
                { value: "table", label: "Table" },
              ]}
            />
          }
        >
          {s.months.length === 0 ? (
            <EmptyState title="No activity in this range" />
          ) : view === "chart" ? (
            <CashFlowChart months={s.months} selectedMonth={selectedMonth} onSelectMonth={selectMonth} />
          ) : (
            <CashFlowTable months={s.months} />
          )}
        </Card>

        <Card
          title="Spending by category"
          description={filters.category ? "Select the category again to clear." : "Select a category to filter."}
        >
          {categories.length === 0 ? (
            <EmptyState title="No spending in this range" />
          ) : (
            <BarList
              items={categories}
              total={t.expenses}
              selected={filters.category}
              onSelect={(c) => update({ category: filters.category === c ? null : c })}
            />
          )}
        </Card>

        <Card
          className="lg:col-span-2"
          title={`Daily spending, ${rolling.data?.window_days ?? 30}-day average`}
          description="Each point averages the 30 days before it. Faded at the start while the first window fills."
        >
          <ChartFrame loading={rolling.loading}>
            <RollingChart points={rolling.data?.points ?? []} />
          </ChartFrame>
        </Card>

        <Card title="Top merchants" description="Net of refunds.">
          {merchants.length === 0 ? (
            <EmptyState title="No merchants in this range" />
          ) : (
            <BarList
              items={merchants}
              total={t.expenses}
              selected={filters.merchant || null}
              onSelect={(m) => update({ merchant: filters.merchant === m ? "" : m })}
            />
          )}
        </Card>

        <div className="lg:col-span-2">
          <RecurringCharges charges={s.recurring_charges} />
        </div>

        <DataQuality quality={s.data_quality} duplicates={s.probable_duplicates} dropDuplicates={filters.dropDuplicates} />

        <div className="lg:col-span-3">
          <TransactionsTable filters={filters} accounts={meta.data.accounts} />
        </div>
      </div>

      <footer className="mt-10 text-center text-xs text-muted">
        {s.months.length > 0 && `${monthLabel(s.months[0].month, true)} – ${monthLabel(s.months.at(-1)!.month, true)} · `}
        Computed by the Python engine; this page only displays it.
      </footer>
    </div>
  );
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted">Loading your finances…</p>
    </div>
  );
}

function ApiDown({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md rounded-xl bg-surface p-6 shadow-card">
        <h1 className="text-base font-semibold text-ink">Can't reach the finance API</h1>
        <p className="mt-2 text-sm text-ink-2">Start it from the project root, then reload:</p>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-sunken px-3 py-2 text-xs text-ink">
          python3 -m finance serve data/transactions.json
        </pre>
        <p className="mt-3 text-xs text-muted">{message}</p>
      </div>
    </div>
  );
}
