"""Monthly financial summary as a JSON-ready dict."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from .analytics import (
    cash_flow,
    monthly_cash_flow,
    rolling_spending_average,
    spending_by_category,
    top_merchants,
)
from .duplicates import drop_duplicates, find_probable_duplicates
from .filters import TransactionFilter
from .ledger import Ledger
from .models import money
from .subscriptions import detect_recurring

REPORT_VERSION = 1


def build_summary(
    ledger: Ledger,
    flt: TransactionFilter | None = None,
    *,
    top_n: int = 5,
    drop_probable_duplicates: bool = False,
    rolling_window_days: int = 30,
    as_of: date | None = None,
) -> dict:
    flt = flt or TransactionFilter()
    duplicate_groups = find_probable_duplicates(ledger.transactions)
    working = ledger.transactions
    if drop_probable_duplicates:
        working = drop_duplicates(working, duplicate_groups)

    in_scope = flt.apply(working)
    # Rolling windows and cadence detection need history outside the date range.
    history = flt.without_dates().apply(working)

    rolling = rolling_spending_average(history, start=flt.start, end=flt.end, window_days=rolling_window_days)
    rolling_at_month_end = {}
    for point in rolling:  # points are in date order, so the last write per month wins
        rolling_at_month_end[point.date.strftime("%Y-%m")] = point

    by_month: dict[str, list] = defaultdict(list)
    for tx in in_scope:
        by_month[tx.month].append(tx)

    months = []
    for month, flow in monthly_cash_flow(in_scope).items():
        txs = by_month.get(month, [])
        point = rolling_at_month_end.get(month)
        months.append({
            "month": month,
            **flow.to_dict(),
            "spending_by_category": {k: money(v) for k, v in spending_by_category(txs).items()},
            "top_merchants": [m.to_dict() for m in top_merchants(txs, top_n)],
            f"rolling_{rolling_window_days}_day_daily_average_at_month_end": (
                money(point.daily_average) if point else None
            ),
        })

    return {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0),
        "filters": flt.to_dict(),
        "options": {
            "top_n": top_n,
            "drop_probable_duplicates": drop_probable_duplicates,
            "rolling_window_days": rolling_window_days,
        },
        "totals": {
            **cash_flow(in_scope).to_dict(),
            "spending_by_category": {k: money(v) for k, v in spending_by_category(in_scope).items()},
            "top_merchants": [m.to_dict() for m in top_merchants(in_scope, top_n)],
        },
        "months": months,
        "recurring_charges": [c.to_dict() for c in detect_recurring(history, as_of=as_of or ledger.as_of)],
        "probable_duplicates": [g.to_dict() for g in duplicate_groups if any(flt.matches(t) for t in g.transactions)],
        "data_quality": ledger.data_quality(),
    }


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Exact Decimals internally, already quantized to cents; JSON numbers on the way out.
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_json(data: Any, *, indent: int | None = 2) -> str:
    return json.dumps(data, default=json_default, indent=indent)
