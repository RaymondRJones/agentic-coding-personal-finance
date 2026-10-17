const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const wholeCurrency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

/** $1,234.56 */
export const money = (value: number) => currency.format(value);
/** $1,235 — for large summary figures where cents are noise. */
export const moneyWhole = (value: number) => wholeCurrency.format(value);
/** $12.9K — for axis ticks. */
export const moneyCompact = (value: number) => compactCurrency.format(value);
/** +$12.50 / −$12.50 with a true minus sign. */
export const signedMoney = (value: number) => `${value < 0 ? "−" : "+"}${currency.format(Math.abs(value))}`;
export const count = (value: number) => integer.format(value);
export const pct = (value: number) => percent.format(value);

/** ISO dates are calendar dates; parse as local so they never shift a day across time zones. */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function toIso(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export const shortDate = (iso: string) =>
  parseDate(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
export const longDate = (iso: string) =>
  parseDate(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

/** "2026-03" -> "Mar" (or "Mar 2026" with year). */
export function monthLabel(month: string, withYear = false): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-US", withYear ? { month: "short", year: "numeric" } : { month: "short" });
}

/** First and last calendar day of a YYYY-MM month, as ISO dates. */
export function monthBounds(month: string): [string, string] {
  const [y, m] = month.split("-").map(Number);
  return [toIso(new Date(y, m - 1, 1)), toIso(new Date(y, m, 0))];
}
