"""The ledger pipeline: parse -> validate -> dedupe -> pair transfers -> classify -> categorize.

Transfer pairing and category inference run over the *whole* ledger before any
user filter is applied. Filtering first would break pairs (filter to checking and
the card leg disappears) and starve category inference of examples.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .models import (
    TRANSFER_CATEGORY,
    TRANSFER_KINDS,
    UNCATEGORIZED,
    Account,
    Kind,
    Transaction,
    TxType,
)
from .transfers import DEFAULT_WINDOW_DAYS, TransferPair, detect_internal_transfers
from .validation import (
    ExactDuplicate,
    LedgerFormatError,
    ValidationError,
    ValidationIssue,
    load_document,
    parse_accounts,
    parse_transactions,
)


@dataclass
class Ledger:
    accounts: dict[str, Account]
    transactions: list[Transaction]
    total_records: int
    issues: list[ValidationIssue] = field(default_factory=list)
    exact_duplicates: list[ExactDuplicate] = field(default_factory=list)
    transfer_pairs: list[TransferPair] = field(default_factory=list)

    @property
    def as_of(self) -> date | None:
        """Date of the latest transaction: "today" from the data's point of view."""
        return self.transactions[-1].date if self.transactions else None

    @property
    def unmatched_transfers(self) -> list[Transaction]:
        return [t for t in self.transactions if t.kind is Kind.UNMATCHED_TRANSFER]

    def data_quality(self) -> dict:
        return {
            "total_records": self.total_records,
            "valid_transactions": len(self.transactions),
            "rejected_records": len({i.index for i in self.issues}),
            "exact_duplicates_removed": len(self.exact_duplicates),
            "categories_inferred": sum(t.category_inferred for t in self.transactions),
            "uncategorized": sum(
                t.effective_category == UNCATEGORIZED for t in self.transactions
            ),
            "internal_transfer_pairs": len(self.transfer_pairs),
            "internal_transfer_pairs_by_method": dict(Counter(p.method for p in self.transfer_pairs)),
            "unmatched_transfers": [t.to_dict() for t in self.unmatched_transfers],
            "issues": [i.to_dict() for i in self.issues],
            "exact_duplicates": [d.to_dict() for d in self.exact_duplicates],
        }


def build_ledger(
    document: dict, *, strict: bool = False, transfer_window_days: int = DEFAULT_WINDOW_DAYS
) -> Ledger:
    if not isinstance(document, dict):
        raise LedgerFormatError("document must be a JSON object with 'accounts' and 'transactions'")
    for key in ("accounts", "transactions"):
        if key not in document:
            raise LedgerFormatError(f"document is missing '{key}'")

    accounts, account_issues = parse_accounts(document["accounts"])
    transactions, tx_issues, exact_duplicates = parse_transactions(document["transactions"], accounts)
    issues = account_issues + tx_issues
    if strict and issues:
        raise ValidationError(issues)

    pairs = detect_internal_transfers(transactions, transfer_window_days)
    classify(transactions, pairs)
    assign_categories(transactions)

    return Ledger(
        accounts=accounts,
        transactions=sorted(transactions, key=lambda t: (t.date, t.source_index)),
        total_records=len(document["transactions"]),
        issues=issues,
        exact_duplicates=exact_duplicates,
        transfer_pairs=pairs,
    )


def load_ledger(path: str | Path, **kwargs) -> Ledger:
    return build_ledger(load_document(path), **kwargs)


def classify(transactions: Iterable[Transaction], pairs: Iterable[TransferPair]) -> None:
    group_by_id = {}
    for pair in pairs:
        group_by_id[pair.outflow.id] = pair.group_id
        group_by_id[pair.inflow.id] = pair.group_id

    for tx in transactions:
        if tx.id in group_by_id:
            tx.kind, tx.transfer_group = Kind.INTERNAL_TRANSFER, group_by_id[tx.id]
        elif tx.type in (TxType.TRANSFER, TxType.PAYMENT):
            # A transfer whose other leg isn't in the data. Excluded from income and
            # expenses (we can't tell if it's internal) but surfaced for review.
            tx.kind = Kind.UNMATCHED_TRANSFER
        elif tx.type is TxType.INCOME:
            tx.kind = Kind.INCOME
        elif tx.type is TxType.REFUND:
            tx.kind = Kind.REFUND
        else:
            tx.kind = Kind.EXPENSE


def assign_categories(transactions: Iterable[Transaction]) -> None:
    """Fill missing categories from the merchant's most common category.

    This also gives a refund with no category the category of the purchases it
    reverses, so the refund nets against the right bucket.
    """
    txs = list(transactions)
    by_merchant: dict[str, Counter] = defaultdict(Counter)
    for tx in txs:
        if tx.kind not in TRANSFER_KINDS and tx.category:
            by_merchant[tx.merchant_key][tx.category] += 1

    for tx in txs:
        tx.category_inferred = False
        if tx.kind in TRANSFER_KINDS:
            tx.effective_category = TRANSFER_CATEGORY
        elif tx.category:
            tx.effective_category = tx.category
        elif counts := by_merchant.get(tx.merchant_key):
            tx.effective_category = counts.most_common(1)[0][0]
            tx.category_inferred = True
        else:
            tx.effective_category = UNCATEGORIZED
