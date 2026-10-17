"""Probable-duplicate detection.

Exact duplicates (same id, identical record) are removed during parsing. This module
finds the harder case: *different* ids for what looks like the same charge — same
account, same normalized merchant, same amount, within `window_days`. These are
flagged, not silently dropped, because two identical coffees on one day can be real.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .models import TRANSFER_KINDS, Transaction


@dataclass(frozen=True)
class DuplicateGroup:
    transactions: tuple[Transaction, ...]

    @property
    def keep(self) -> Transaction:
        return self.transactions[0]

    @property
    def extras(self) -> tuple[Transaction, ...]:
        return self.transactions[1:]

    def to_dict(self) -> dict:
        first = self.keep
        return {
            "account_id": first.account_id,
            "merchant": first.merchant,
            "amount": first.amount,
            "dates": sorted({t.date for t in self.transactions}),
            "ids": [t.id for t in self.transactions],
            "suggested_keep": first.id,
        }


def find_probable_duplicates(
    transactions: Iterable[Transaction], window_days: int = 0
) -> list[DuplicateGroup]:
    buckets: dict[tuple, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.kind in TRANSFER_KINDS:
            continue  # transfer legs are reconciled by the transfer matcher instead
        buckets[(tx.account_id, tx.merchant_key, tx.amount)].append(tx)

    groups: list[DuplicateGroup] = []
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        bucket.sort(key=lambda t: (t.date, t.source_index))
        cluster = [bucket[0]]
        for tx in bucket[1:]:
            if (tx.date - cluster[-1].date).days <= window_days:
                cluster.append(tx)
            else:
                if len(cluster) > 1:
                    groups.append(DuplicateGroup(tuple(cluster)))
                cluster = [tx]
        if len(cluster) > 1:
            groups.append(DuplicateGroup(tuple(cluster)))

    groups.sort(key=lambda g: (g.keep.date, g.keep.source_index))
    return groups


def drop_duplicates(transactions: Iterable[Transaction], groups: Iterable[DuplicateGroup]) -> list[Transaction]:
    """Remove every member of each group except the first."""
    drop = {tx.id for group in groups for tx in group.extras}
    return [tx for tx in transactions if tx.id not in drop]
