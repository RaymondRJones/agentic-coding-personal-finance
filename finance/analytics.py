"""Aggregations: cash flow, category/merchant breakdowns, top merchants, rolling averages.

All functions expect transactions that have been through the ledger pipeline
(i.e. `kind` and `effective_category` are set). Definitions:

  income        sum of INCOME amounts
  gross_spend   sum of EXPENSE outflows (purchases + fees), as a positive number
  refunds       sum of REFUND amounts, as a positive number
  expenses      gross_spend - refunds
  net_cash_flow income - expenses

Internal transfers (including credit-card payments) never touch any of these.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .models import SPENDING_KINDS, ZERO, Kind, Transaction, display_name, money


@dataclass(frozen=True)
class CashFlow:
    income: Decimal = ZERO
    gross_spend: Decimal = ZERO
    refunds: Decimal = ZERO
    internal_transfers: Decimal = ZERO  # volume excluded from income/expenses
    unmatched_transfers: Decimal = ZERO
    transaction_count: int = 0

    @property
    def expenses(self) -> Decimal:
        return self.gross_spend - self.refunds

    @property
    def net_cash_flow(self) -> Decimal:
        return self.income - self.expenses

    @property
    def savings_rate(self) -> Decimal | None:
        if self.income <= 0:
            return None
        return (self.net_cash_flow / self.income).quantize(Decimal("0.0001"))

    def to_dict(self) -> dict:
        return {
            "income": money(self.income),
            "gross_spend": money(self.gross_spend),
            "refunds": money(self.refunds),
            "expenses": money(self.expenses),
            "net_cash_flow": money(self.net_cash_flow),
            "savings_rate": self.savings_rate,
            "internal_transfers_excluded": money(self.internal_transfers),
            "unmatched_transfers_excluded": money(self.unmatched_transfers),
            "transaction_count": self.transaction_count,
        }


def cash_flow(transactions: Iterable[Transaction]) -> CashFlow:
    income = gross = refunds = internal = unmatched = ZERO
    count = 0
    for tx in transactions:
        count += 1
        if tx.kind is Kind.INCOME:
            income += tx.amount
        elif tx.kind is Kind.EXPENSE:
            gross -= tx.amount
        elif tx.kind is Kind.REFUND:
            refunds += tx.amount
        elif tx.kind is Kind.INTERNAL_TRANSFER:
            if tx.amount < 0:  # count each transfer once, by its outflow leg
                internal -= tx.amount
        elif tx.kind is Kind.UNMATCHED_TRANSFER:
            unmatched += abs(tx.amount)
    return CashFlow(income, gross, refunds, internal, unmatched, count)


def monthly_cash_flow(transactions: Iterable[Transaction]) -> dict[str, CashFlow]:
    """Cash flow per YYYY-MM. Months with no activity between the first and last are included."""
    by_month: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        by_month[tx.month].append(tx)
    if not by_month:
        return {}
    return {month: cash_flow(by_month.get(month, ())) for month in month_range(min(by_month), max(by_month))}


def spending_by_category(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for tx in transactions:
        if tx.kind in SPENDING_KINDS:
            totals[tx.effective_category] += tx.amount
    return dict(sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])))


@dataclass(frozen=True)
class MerchantSpend:
    merchant: str
    merchant_key: str
    total: Decimal
    purchases: int
    refunds: int

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "total": money(self.total),
            "purchases": self.purchases,
            "refunds": self.refunds,
        }


def spending_by_merchant(transactions: Iterable[Transaction]) -> list[MerchantSpend]:
    """Net spend per normalized merchant, largest first."""
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    names: dict[str, Counter] = defaultdict(Counter)
    purchases: Counter = Counter()
    refunds: Counter = Counter()
    for tx in transactions:
        if tx.kind not in SPENDING_KINDS:
            continue
        key = tx.merchant_key
        totals[key] += tx.spend
        names[key][tx.merchant] += 1
        (purchases if tx.kind is Kind.EXPENSE else refunds)[key] += 1
    result = [
        MerchantSpend(display_name(names[k]), k, total, purchases[k], refunds[k])
        for k, total in totals.items()
    ]
    result.sort(key=lambda m: (-m.total, m.merchant_key))
    return result



def top_merchants(transactions: Iterable[Transaction], n: int = 10) -> list[MerchantSpend]:
    if n < 0:
        raise ValueError("n must be non-negative")
    return [m for m in spending_by_merchant(transactions) if m.total > 0][:n]


@dataclass(frozen=True)
class RollingPoint:
    date: date
    window_total: Decimal
    daily_average: Decimal
    complete_window: bool  # False while fewer than `window_days` of history exist

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "window_total": money(self.window_total),
            "daily_average": money(self.daily_average),
            "complete_window": self.complete_window,
        }


def rolling_spending_average(
    transactions: Iterable[Transaction],
    *,
    start: date | None = None,
    end: date | None = None,
    window_days: int = 30,
) -> list[RollingPoint]:
    """Trailing `window_days` net spend divided by `window_days`, for each calendar day.

    Days without spending count as zero. History before `start` feeds the early
    windows, so pass unfiltered-by-date transactions and bound the output with start/end.
    """
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    daily: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for tx in transactions:
        if tx.kind is SPENDING_KINDS:
            daily[tx.date] += tx.spend
    if not daily:
        return []

    history_start = min(daily)
    start = start or history_start
    end = end or max(daily)
    points: list[RollingPoint] = []
    running = ZERO
    day = min(history_start, start)
    while day <= end:
        running += daily.get(day, ZERO)
        running -= daily.get(day - timedelta(days=window_days), ZERO)
        if day >= start:
            complete = (day - history_start).days >= window_days - 1
            points.append(RollingPoint(day, running, running / window_days, complete))
        day += timedelta(days=1)
    return points


def month_range(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    end_year, end_month = map(int, last.split("-"))
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months
