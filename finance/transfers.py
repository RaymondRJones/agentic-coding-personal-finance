"""Internal transfer detection.

Paying a credit card from checking produces two records: money leaving checking
and a payment landing on the card. The card *purchases* are the real expenses;
both legs of the payment are just money moving between the user's own accounts.
Counting the checking leg as an expense double counts every purchase made on the card.

Legs are paired in two passes:
  1. Explicit: both legs share a `transfer_id`.
  2. Heuristic: an outflow and an inflow of the same absolute amount, in different
     accounts, within `window_days`, where *both* legs look like a transfer
     (type, merchant keywords, or category). Requiring both legs keeps a random
     $45 purchase from pairing with an unrelated $45 card payment.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .models import Transaction, TxType

DEFAULT_WINDOW_DAYS = 3

TRANSFER_KEYWORDS = (
    "transfer", "xfer", "autopay", "auto pay", "payment thank you", "payment - thank you",
    "payment received", "online payment", "card payment", "epay",
)
TRANSFER_CATEGORIES = frozenset({"transfer", "transfers", "credit card payment", "internal transfer"})
_TRANSFER_TYPES = frozenset({TxType.TRANSFER, TxType.PAYMENT})
_NEVER_TRANSFER = frozenset({TxType.INCOME, TxType.REFUND})


@dataclass(frozen=True)
class TransferPair:
    group_id: str
    outflow: Transaction
    inflow: Transaction
    method: str  # "transfer_id" or "matched"

    @property
    def amount(self) -> Decimal:
        return -self.outflow.amount

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "method": self.method,
            "amount": self.amount,
            "from_account": self.outflow.account_id,
            "to_account": self.inflow.account_id,
            "outflow_id": self.outflow.id,
            "inflow_id": self.inflow.id,
            "outflow_date": self.outflow.date,
            "inflow_date": self.inflow.date,
        }


def is_transfer_like(tx: Transaction) -> bool:
    if tx.type in _NEVER_TRANSFER:
        return False
    if tx.type in _TRANSFER_TYPES:
        return True
    if tx.category and tx.category.casefold() in TRANSFER_CATEGORIES:
        return True
    merchant = tx.merchant.casefold()
    return any(keyword in merchant for keyword in TRANSFER_KEYWORDS)


def detect_internal_transfers(
    transactions: Iterable[Transaction], window_days: int = DEFAULT_WINDOW_DAYS
) -> list[TransferPair]:
    txs = list(transactions)
    pairs: list[TransferPair] = []
    paired: set[str] = set()

    # Pass 1: explicit transfer_id. Only a clean two-leg, zero-sum group qualifies;
    # anything else falls through to the heuristic pass.
    by_transfer_id: dict[str, list[Transaction]] = defaultdict(list)
    for tx in txs:
        if tx.transfer_id:
            by_transfer_id[tx.transfer_id].append(tx)
    for transfer_id, legs in by_transfer_id.items():
        if len(legs) != 2:
            continue
        out, inn = sorted(legs, key=lambda t: t.amount)
        if out.amount < 0 and out.amount + inn.amount == 0 and out.account_id != inn.account_id:
            pairs.append(TransferPair(transfer_id, out, inn, "transfer_id"))
            paired.update((out.id, inn.id))

    # Pass 2: heuristic matching on amount, date proximity, and transfer-like signals.
    inflows_by_amount: dict[Decimal, list[Transaction]] = defaultdict(list)
    outflows: list[Transaction] = []
    for tx in txs:
        if tx.id in paired or not is_transfer_like(tx):
            continue
        if tx.amount > 0:
            inflows_by_amount[tx.amount].append(tx)
        elif tx.amount < 0:
            outflows.append(tx)

    outflows.sort(key=lambda t: (t.date, t.id))
    for out in outflows:
        best: Transaction | None = None
        best_key: tuple | None = None
        for inn in inflows_by_amount.get(-out.amount, ()):
            if inn.id in paired or inn.account_id == out.account_id:
                continue
            if out.counterparty_account_id and inn.account_id != out.counterparty_account_id:
                continue
            if inn.counterparty_account_id and inn.counterparty_account_id != out.account_id:
                continue
            gap = abs((inn.date - out.date).days)
            if gap > window_days:
                continue
            key = (gap, inn.date, inn.id)
            if best_key is None or key < best_key:
                best, best_key = inn, key
        if best is not None:
            pairs.append(TransferPair(f"matched:{out.id}:{best.id}", out, best, "matched"))
            paired.update((out.id, best.id))

    pairs.sort(key=lambda p: (p.outflow.date, p.outflow.id))
    return pairs
