import type { ReactNode } from "react";
import { count, money, shortDate } from "../lib/format";
import type { DataQuality as DataQualityT, DuplicateGroup } from "../lib/types";
import { Alert, Badge, Card, Check } from "./ui";

/** What the engine cleaned up before the numbers above were computed. */
export function DataQuality({ quality, duplicates, dropDuplicates }: {
  quality: DataQualityT;
  duplicates: DuplicateGroup[];
  dropDuplicates: boolean;
}) {
  const matched = quality.internal_transfer_pairs_by_method.matched ?? 0;
  return (
    <Card
      title="Data quality"
      description={`${count(quality.valid_transactions)} of ${count(quality.total_records)} records used`}
    >
      <ul className="divide-y divide-hairline">
        <Row
          tone={quality.rejected_records ? "critical" : "good"}
          value={count(quality.rejected_records)}
          label="Invalid records rejected"
          hint="Missing fields, impossible dates, wrong signs, or unknown accounts."
        >
          {quality.issues.length > 0 && (
            <ul className="space-y-1.5 text-xs">
              {quality.issues.map((issue) => (
                <li key={issue.index} className="flex gap-2">
                  <span className="num w-20 shrink-0 text-muted">{issue.id ?? `row ${issue.index}`}</span>
                  <span className="text-ink-2">
                    <span className="font-medium text-ink">{issue.field}</span> {issue.message}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Row>
        <Row
          tone="good"
          value={count(quality.exact_duplicates_removed)}
          label="Exact duplicates removed"
          hint="Same id and identical content: the feed sent the record twice."
        />
        <Row
          tone={duplicates.length ? "warning" : "good"}
          value={count(duplicates.length)}
          label={dropDuplicates ? "Likely duplicates excluded" : "Likely duplicates (still counted)"}
          hint="Different ids, but same account, merchant, amount and day."
        >
          {duplicates.length > 0 && (
            <ul className="space-y-1.5 text-xs">
              {duplicates.map((g) => (
                <li key={g.ids.join()} className="flex justify-between gap-3">
                  <span className="text-ink-2">
                    <span className="font-medium text-ink">{g.merchant}</span> · {shortDate(g.dates[0])} · {g.ids.length}×
                  </span>
                  <span className="num text-ink-2">{money(Math.abs(g.amount))}</span>
                </li>
              ))}
            </ul>
          )}
        </Row>
        <Row
          tone="good"
          value={count(quality.categories_inferred)}
          label="Missing categories filled in"
          hint="From each merchant's usual category, so refunds land in the right bucket."
        />
        <Row
          tone="good"
          value={count(quality.internal_transfer_pairs)}
          label="Transfers between your accounts"
          hint={`Paired and excluded from income and spending${matched ? `, ${matched} found without a transfer id` : ""}.`}
        />
        <Row
          tone={quality.unmatched_transfers.length ? "warning" : "good"}
          value={count(quality.unmatched_transfers.length)}
          label="Transfers with no matching side"
          hint="Excluded from totals. Review: these may be money leaving the household."
        >
          {quality.unmatched_transfers.length > 0 && (
            <ul className="space-y-1.5 text-xs">
              {quality.unmatched_transfers.map((t) => (
                <li key={t.id} className="flex justify-between gap-3">
                  <span className="text-ink-2">
                    <span className="font-medium text-ink">{t.merchant}</span> · {shortDate(t.date)}
                  </span>
                  <span className="num text-ink-2">{money(Math.abs(t.amount))}</span>
                </li>
              ))}
            </ul>
          )}
        </Row>
      </ul>
    </Card>
  );
}

function Row({ tone, value, label, hint, children }: {
  tone: "good" | "warning" | "critical";
  value: string;
  label: string;
  hint: string;
  children?: ReactNode;
}) {
  const icon = tone === "good" ? <Check /> : <Alert />;
  const summary = (
    <div className="flex items-start gap-3 py-3">
      <Badge tone={tone} icon={icon}>{value}</Badge>
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="mt-0.5 text-xs text-muted">{hint}</p>
      </div>
    </div>
  );
  if (!children) return <li>{summary}</li>;
  return (
    <li>
      <details className="group">
        <summary className="cursor-pointer list-none rounded-lg hover:bg-sunken [&::-webkit-details-marker]:hidden">
          {summary}
        </summary>
        <div className="mb-3 ml-3 max-h-56 overflow-y-auto rounded-lg bg-sunken p-3">{children}</div>
      </details>
    </li>
  );
}
