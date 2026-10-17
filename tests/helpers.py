from __future__ import annotations

import itertools

from finance.ledger import build_ledger

ACCOUNTS = [
    {"id": "checking_1", "type": "checking"},
    {"id": "savings_1", "type": "savings"},
    {"id": "credit_1", "type": "credit_card"},
]

_ids = itertools.count(1)


def tx(date, amount, merchant="Store", type="purchase", account="checking_1", category="Shopping", **extra):
    record = {
        "id": extra.pop("id", f"t{next(_ids)}"),
        "account_id": account,
        "date": date,
        "merchant": merchant,
        "amount": amount,
        "category": category,
        "type": type,
    }
    record.update(extra)
    return record


def ledger(*transactions, accounts=ACCOUNTS, **kwargs):
    return build_ledger({"accounts": accounts, "transactions": list(transactions)}, **kwargs)
