"""Personal finance analytics engine (Python standard library only)."""

from .analytics import (
    cash_flow,
    monthly_cash_flow,
    rolling_spending_average,
    spending_by_category,
    top_merchants,
)
from .duplicates import find_probable_duplicates
from .filters import TransactionFilter, filter_transactions
from .ledger import Ledger, build_ledger, load_ledger
from .report import build_summary, to_json
from .subscriptions import detect_recurring

__all__ = [
    "Ledger", "TransactionFilter", "build_ledger", "build_summary", "cash_flow", "detect_recurring",
    "filter_transactions", "find_probable_duplicates", "load_ledger", "monthly_cash_flow",
    "rolling_spending_average", "spending_by_category", "to_json", "top_merchants",
]
