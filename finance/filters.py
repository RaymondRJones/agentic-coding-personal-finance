"""Transaction filtering. Apply *after* the ledger is built (see ledger.py)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from .models import Transaction, normalize_merchant


@dataclass(frozen=True)
class TransactionFilter:
    start: date | None = None  # inclusive
    end: date | None = None  # inclusive
    accounts: frozenset[str] = field(default_factory=frozenset)
    categories: frozenset[str] = field(default_factory=frozenset)  # matched case-insensitively
    merchant: str | None = None  # case-insensitive substring of the raw or normalized name

    def __post_init__(self) -> None:
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")
        object.__setattr__(self, "accounts", frozenset(self.accounts))
        object.__setattr__(self, "categories", frozenset(c.casefold() for c in self.categories))

    def matches(self, tx: Transaction) -> bool:
        if self.start and tx.date < self.start:
            return False
        if self.end and tx.date > self.end:
            return False
        if self.accounts and tx.account_id not in self.accounts:
            return False
        if self.categories and tx.effective_category.casefold() not in self.categories:
            return False
        if self.merchant:
            needle = self.merchant.casefold()
            if needle not in tx.merchant.casefold() and normalize_merchant(self.merchant) not in tx.merchant_key:
                return False
        return True

    def apply(self, transactions: Iterable[Transaction]) -> list[Transaction]:
        return [tx for tx in transactions if self.matches(tx)]

    def without_dates(self) -> TransactionFilter:
        return TransactionFilter(accounts=self.accounts, categories=self.categories, merchant=self.merchant)

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "accounts": sorted(self.accounts),
            "categories": sorted(self.categories),
            "merchant": self.merchant,
        }


def filter_transactions(transactions: Iterable[Transaction], **criteria) -> list[Transaction]:
    return TransactionFilter(**criteria).apply(transactions)
