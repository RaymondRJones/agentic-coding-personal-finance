import { useEffect, useState } from "react";
import { apiUrl, filterParams, useApi } from "../lib/api";
import { count, money, shortDate } from "../lib/format";
import type { Account, Filters, Kind, TransactionPage } from "../lib/types";
import { Badge, Card, EmptyState, Segmented } from "./ui";

const PAGE_SIZE = 25;

type KindFilter = "all" | "spending" | "income" | "transfers";
const KIND_PARAMS: Record<KindFilter, Kind[]> = {
  all: [],
  spending: ["expense", "refund"],
  income: ["income"],
  transfers: ["internal_transfer", "unmatched_transfer"],
};

const KIND_BADGE: Record<Kind, { label: string; tone: "neutral" | "accent" | "good" | "warning" } | null> = {
  expense: null,
  income: { label: "Income", tone: "good" },
  refund: { label: "Refund", tone: "accent" },
  internal_transfer: { label: "Transfer", tone: "neutral" },
  unmatched_transfer: { label: "Unmatched transfer", tone: "warning" },
};

export function TransactionsTable({ filters, accounts }: { filters: Filters; accounts: Account[] }) {
  const [kind, setKind] = useState<KindFilter>("all");
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [filters, kind]);

  const params = filterParams(filters);
  for (const k of KIND_PARAMS[kind]) params.append("kind", k);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(offset));
  const { data, loading } = useApi<TransactionPage>(apiUrl("transactions", params));

  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? id;

  return (
    <Card
      title="Transactions"
      actions={
        <Segmented
          label="Transaction type"
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: "All" },
            { value: "spending", label: "Spending" },
            { value: "income", label: "Income" },
            { value: "transfers", label: "Transfers" },
          ]}
        />
      }
    >
      <div className={`-mx-5 overflow-x-auto transition-opacity sm:-mx-6 ${loading ? "opacity-50" : ""}`}>
        {data && data.items.length === 0 ? (
          <EmptyState title="No transactions match">Clear a filter or widen the date range.</EmptyState>
        ) : (
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="px-5 pb-2 font-medium sm:px-6">Date</th>
                <th className="pb-2 font-medium">Merchant</th>
                <th className="pb-2 font-medium">Account</th>
                <th className="px-5 pb-2 text-right font-medium sm:px-6">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((t) => {
                const badge = KIND_BADGE[t.kind];
                return (
                  <tr key={t.id} className="border-t border-hairline">
                    <td className="num px-5 py-3 whitespace-nowrap text-ink-2 sm:px-6">{shortDate(t.date)}</td>
                    <td className="py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink">{t.merchant || "—"}</span>
                        {badge && <Badge tone={badge.tone}>{badge.label}</Badge>}
                        {t.probable_duplicate && <Badge tone="warning">Likely duplicate</Badge>}
                      </div>
                      <p className="mt-0.5 text-xs text-muted">
                        {t.effective_category}
                        {t.category_inferred && <span title="Category was missing and inferred from the merchant"> · inferred</span>}
                      </p>
                    </td>
                    <td className="py-3 text-ink-2">{accountName(t.account_id)}</td>
                    <td
                      className={`num px-5 py-3 text-right font-medium whitespace-nowrap sm:px-6 ${
                        t.amount > 0 ? "text-good-ink" : "text-ink"
                      }`}
                    >
                      {t.amount > 0 ? `+${money(t.amount)}` : money(t.amount).replace("-", "−")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {data && data.total > 0 && (
        <footer className="mt-4 flex items-center justify-between text-sm">
          <p className="num text-muted">
            {count(offset + 1)}–{count(Math.min(offset + PAGE_SIZE, data.total))} of {count(data.total)}
          </p>
          <div className="flex gap-2">
            <PageButton disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </PageButton>
            <PageButton disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </PageButton>
          </div>
        </footer>
      )}
    </Card>
  );
}

function PageButton({ disabled, onClick, children }: { disabled: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg bg-surface px-3 py-1.5 font-medium text-ink shadow-card hover:bg-sunken disabled:cursor-not-allowed disabled:text-muted disabled:shadow-none"
    >
      {children}
    </button>
  );
}
