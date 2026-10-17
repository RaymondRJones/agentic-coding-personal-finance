"""Recurring-charge (subscription) detection.

A merchant is recurring when its charges:
  * occur at least `min_occurrences` times,
  * land on a recognizable cadence (most intervals within the cadence's range), and
  * have stable amounts *between consecutive charges* — comparing neighbours rather
    than the overall median lets a one-time price increase (Netflix $15.49 -> $17.99)
    through while still rejecting variable bills like electricity.
"""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from statistics import median

from .models import Kind, Transaction, display_name, money


@dataclass(frozen=True)
class Cadence:
    name: str
    min_days: int
    max_days: int
    per_year: int
    months: int = 0  # >0 means "advance by calendar months" for next-date prediction
    days: int = 0


CADENCES = (
    Cadence("weekly", 5, 9, 52, days=7),
    Cadence("biweekly", 12, 16, 26, days=14),
    Cadence("monthly", 26, 35, 12, months=1),
    Cadence("quarterly", 84, 98, 4, months=3),
    Cadence("annual", 350, 380, 1, months=12),
)


@dataclass(frozen=True)
class RecurringCharge:
    merchant: str
    category: str
    cadence: str
    current_amount: Decimal
    occurrences: int
    first_date: date
    last_date: date
    next_expected: date
    annualized_cost: Decimal
    account_ids: tuple[str, ...]
    active: bool
    price_changes: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "category": self.category,
            "cadence": self.cadence,
            "current_amount": money(self.current_amount),
            "occurrences": self.occurrences,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "next_expected": self.next_expected,
            "annualized_cost": money(self.annualized_cost),
            "accounts": list(self.account_ids),
            "active": self.active,
            "price_changes": list(self.price_changes),
        }


def detect_recurring(
    transactions: Iterable[Transaction],
    *,
    min_occurrences: int = 3,
    amount_tolerance: Decimal = Decimal("0.10"),
    regularity: float = 0.8,
    as_of: date | None = None,
) -> list[RecurringCharge]:
    txs = [t for t in transactions if t.kind is Kind.EXPENSE]
    if not txs:
        return []
    as_of = as_of or max(t.date for t in txs)

    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for tx in txs:
        by_merchant[tx.merchant_key].append(tx)

    found: list[RecurringCharge] = []
    for group in by_merchant.values():
        charge = _evaluate(group, min_occurrences, amount_tolerance, regularity, as_of)
        if charge:
            found.append(charge)
    found.sort(key=lambda c: (not c.active, -c.annualized_cost, c.merchant))
    return found


def _evaluate(
    group: list[Transaction], min_occurrences: int, tolerance: Decimal, regularity: float, as_of: date
) -> RecurringCharge | None:
    # One charge per day: same-day repeats are duplicates or multi-purchases, not cadence.
    by_day: dict[date, Transaction] = {}
    for tx in sorted(group, key=lambda t: (t.date, t.source_index)):
        by_day.setdefault(tx.date, tx)
    charges = list(by_day.values())
    if len(charges) < min_occurrences:
        return None

    intervals = [(b.date - a.date).days for a, b in pairwise(charges)]
    typical = median(intervals)
    cadence = next((c for c in CADENCES if c.min_days <= typical <= c.max_days), None)
    if cadence is None:
        return None
    on_cadence = sum(cadence.min_days <= i <= cadence.max_days for i in intervals)
    if on_cadence / len(intervals) < regularity:
        return None

    amounts = [-t.amount for t in charges]
    stable_steps = 0
    price_changes = []
    for (prev, cur), tx in zip(pairwise(amounts), charges[1:], strict=True):
        if abs(cur - prev) <= prev * tolerance:
            stable_steps += 1
        if cur != prev:
            price_changes.append({"date": tx.date, "from": money(prev), "to": money(cur)})
    if stable_steps / (len(amounts) - 1) < regularity:
        return None
    if len(price_changes) > max(1, len(amounts) // 4):
        return None  # amount drifts constantly; not a fixed-price subscription

    last = charges[-1]
    next_expected = _advance(last.date, cadence)
    # Still "active" if the next charge is only a little overdue (late posting, short months).
    grace = timedelta(days=(cadence.max_days - cadence.min_days) // 2 + 3)
    names = Counter(tx.merchant for tx in charges)
    categories = Counter(tx.effective_category for tx in charges)

    return RecurringCharge(
        merchant=display_name(names),
        category=categories.most_common(1)[0][0],
        cadence=cadence.name,
        current_amount=amounts[-1],
        occurrences=len(charges),
        first_date=charges[0].date,
        last_date=last.date,
        next_expected=next_expected,
        annualized_cost=amounts[-1] * cadence.per_year,
        account_ids=tuple(sorted({t.account_id for t in charges})),
        active=next_expected + grace >= as_of,
        price_changes=tuple(price_changes),
    )


def _advance(day: date, cadence: Cadence) -> date:
    if cadence.days:
        return day + timedelta(days=cadence.days)
    month_index = day.month - 1 + cadence.months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
