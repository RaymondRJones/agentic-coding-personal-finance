import { money, moneyWhole, shortDate } from "../lib/format";
import type { RecurringCharge } from "../lib/types";
import { Alert, ArrowUp, Badge, Card, EmptyState } from "./ui";

export function RecurringCharges({ charges }: { charges: RecurringCharge[] }) {
  const active = charges.filter((c) => c.active);
  const annual = active.reduce((sum, c) => sum + c.annualized_cost, 0);

  return (
    <Card
      title="Recurring charges"
      description={
        active.length > 0 ? (
          <>
            {active.length} active, costing <span className="font-medium text-ink">{moneyWhole(annual)}</span> a year
          </>
        ) : undefined
      }
    >
      {charges.length === 0 ? (
        <EmptyState title="No recurring charges found">Try a wider date range or fewer filters.</EmptyState>
      ) : (
        <div className="-mx-5 overflow-x-auto sm:-mx-6">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="px-5 pb-2 font-medium sm:px-6">Merchant</th>
                <th className="pb-2 font-medium">Every</th>
                <th className="pb-2 text-right font-medium">Amount</th>
                <th className="pb-2 pl-6 font-medium">Next charge</th>
                <th className="px-5 pb-2 text-right font-medium sm:px-6">Per year</th>
              </tr>
            </thead>
            <tbody>
              {charges.map((c) => {
                const lastChange = c.price_changes[c.price_changes.length - 1];
                return (
                  <tr key={c.merchant} className={`border-t border-hairline ${c.active ? "" : "text-muted"}`}>
                    <td className="px-5 py-3 sm:px-6">
                      <p className={`font-medium ${c.active ? "text-ink" : ""}`}>{c.merchant}</p>
                      <p className="text-xs text-muted">{c.category}</p>
                    </td>
                    <td className="py-3 capitalize">{c.cadence}</td>
                    <td className="num py-3 text-right">
                      <span className={c.active ? "font-medium text-ink" : ""}>{money(c.current_amount)}</span>
                      {lastChange && lastChange.to > lastChange.from && (
                        <p className="mt-0.5">
                          <Badge tone="warning" icon={<ArrowUp />}>
                            from {money(lastChange.from)}
                          </Badge>
                        </p>
                      )}
                    </td>
                    <td className="py-3 pl-6">
                      {c.active ? (
                        <span className="num text-ink-2">{shortDate(c.next_expected)}</span>
                      ) : (
                        <Badge icon={<Alert />}>Stopped after {shortDate(c.last_date)}</Badge>
                      )}
                    </td>
                    <td className="num px-5 py-3 text-right sm:px-6">{c.active ? moneyWhole(c.annualized_cost) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
