"""Core domain types shared across the engine."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

CENT = Decimal("0.01")
ZERO = Decimal("0")
UNCATEGORIZED = "Uncategorized"
TRANSFER_CATEGORY = "Transfer"


class TxType(StrEnum):
    """The `type` field as supplied in the input data."""

    PURCHASE = "purchase"
    INCOME = "income"
    REFUND = "refund"
    TRANSFER = "transfer"
    PAYMENT = "payment"
    FEE = "fee"


class Kind(StrEnum):
    """How a transaction is treated by aggregation. Derived, never read from input."""

    INCOME = "income"
    EXPENSE = "expense"
    REFUND = "refund"
    INTERNAL_TRANSFER = "internal_transfer"
    UNMATCHED_TRANSFER = "unmatched_transfer"


SPENDING_KINDS = frozenset({Kind.EXPENSE, Kind.REFUND})
TRANSFER_KINDS = frozenset({Kind.INTERNAL_TRANSFER, Kind.UNMATCHED_TRANSFER})


@dataclass(frozen=True)
class Account:
    id: str
    type: str
    name: str | None = None


@dataclass(eq=False)
class Transaction:
    id: str
    account_id: str
    date: date
    merchant: str
    amount: Decimal
    type: TxType
    category: str | None
    transfer_id: str | None = None
    counterparty_account_id: str | None = None
    source_index: int = -1

    # Populated by the ledger pipeline (see ledger.build_ledger).
    kind: Kind | None = None
    effective_category: str = UNCATEGORIZED
    category_inferred: bool = False
    transfer_group: str | None = None

    @property
    def merchant_key(self) -> str:
        return normalize_merchant(self.merchant)

    @property
    def month(self) -> str:
        return f"{self.date.year:04d}-{self.date.month:02d}"

    @property
    def spend(self) -> Decimal:
        """Contribution to spending: positive for expenses, negative for refunds, else zero.

        Amounts are signed from the account's perspective (money out is negative),
        so negating works for both purchases and refunds.
        """
        if self.kind in SPENDING_KINDS:
            return -self.amount
        return ZERO

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "date": self.date,
            "merchant": self.merchant,
            "amount": self.amount,
            "type": self.type.value,
            "category": self.category,
            "effective_category": self.effective_category,
            "category_inferred": self.category_inferred,
            "kind": self.kind.value if self.kind else None,
            "transfer_group": self.transfer_group,
        }


_STORE_SUFFIX = re.compile(r"[*#].*$")
_DOMAIN = re.compile(r"\.(com|net|org)\b")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_LONG_NUMBER = re.compile(r"\b\d{3,}\b")


@lru_cache(maxsize=4096)
def normalize_merchant(name: str) -> str:
    """Collapse processor noise so 'UBER *TRIP' and 'Uber' group together."""
    s = name.casefold()
    s = _STORE_SUFFIX.sub("", s)
    s = _DOMAIN.sub("", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _LONG_NUMBER.sub(" ", s)
    s = " ".join(s.split())
    return s or name.casefold().strip()


def display_name(variants: Counter) -> str:
    """Pick a human-looking spelling ("Whole Foods") over processor noise ("WHOLE FOODS #10234")."""
    def noisy(name: str) -> bool:
        return any(c in name for c in "*#") or name.isupper()
    return min(variants, key=lambda name: (noisy(name), -variants[name], name))


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT)
