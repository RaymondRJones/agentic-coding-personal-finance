"""JSON parsing and record-level validation.

Validation is lenient by default: bad records are rejected individually and
reported as `ValidationIssue`s so one malformed row can't sink a 5,000-row file.
Structural problems (the document isn't shaped like a ledger at all) always raise.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import CENT, Account, Transaction, TxType

REQUIRED_FIELDS = ("id", "account_id", "date", "amount", "type")

# Sign convention: amounts are from the account's perspective; money out is negative.
_MUST_BE_NEGATIVE = frozenset({TxType.PURCHASE, TxType.FEE})
_MUST_BE_POSITIVE = frozenset({TxType.INCOME, TxType.REFUND})

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class ValidationIssue:
    index: int
    tx_id: str | None
    field: str | None
    message: str

    def to_dict(self) -> dict:
        return {"index": self.index, "id": self.tx_id, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class ExactDuplicate:
    """A record that repeats an earlier record byte-for-byte (same id, same content)."""

    index: int
    tx_id: str
    first_index: int

    def to_dict(self) -> dict:
        return {"index": self.index, "id": self.tx_id, "first_index": self.first_index}


class LedgerFormatError(ValueError):
    """The document is not structurally a ledger."""


class ValidationError(ValueError):
    """Raised in strict mode when any record fails validation."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        preview = "; ".join(f"[{i.index}] {i.field}: {i.message}" for i in issues[:5])
        more = f" (+{len(issues) - 5} more)" if len(issues) > 5 else ""
        super().__init__(f"{len(issues)} validation issue(s): {preview}{more}")


def load_document(path: str | Path) -> dict:
    """Read JSON with exact decimal amounts. NaN/Infinity parse to Decimal and are rejected later."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh, parse_float=Decimal, parse_constant=Decimal)


def parse_accounts(raw_accounts: Any) -> tuple[dict[str, Account], list[ValidationIssue]]:
    if not isinstance(raw_accounts, list):
        raise LedgerFormatError("'accounts' must be a list")
    accounts: dict[str, Account] = {}
    issues: list[ValidationIssue] = []
    for index, raw in enumerate(raw_accounts):
        if not isinstance(raw, dict):
            issues.append(ValidationIssue(index, None, None, "account must be an object"))
            continue
        acc_id, acc_type = raw.get("id"), raw.get("type")
        if not isinstance(acc_id, str) or not acc_id.strip():
            issues.append(ValidationIssue(index, None, "id", "account id must be a non-empty string"))
            continue
        if not isinstance(acc_type, str) or not acc_type.strip():
            issues.append(ValidationIssue(index, acc_id, "type", "account type must be a non-empty string"))
            continue
        if acc_id in accounts:
            issues.append(ValidationIssue(index, acc_id, "id", "duplicate account id"))
            continue
        name = raw.get("name") if isinstance(raw.get("name"), str) else None
        accounts[acc_id] = Account(acc_id, acc_type, name)
    return accounts, issues


def parse_transactions(
    raw_transactions: Any, accounts: dict[str, Account]
) -> tuple[list[Transaction], list[ValidationIssue], list[ExactDuplicate]]:
    """Validate every record; drop exact duplicates; reject id conflicts (first occurrence wins)."""
    if not isinstance(raw_transactions, list):
        raise LedgerFormatError("'transactions' must be a list")

    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    duplicates: list[ExactDuplicate] = []
    seen: dict[str, tuple[int, str]] = {}  # id -> (first index, fingerprint)

    for index, raw in enumerate(raw_transactions):
        tx, tx_issues = _parse_transaction(raw, index, accounts)
        if tx_issues:
            issues.extend(tx_issues)
            continue
        fingerprint = json.dumps(raw, sort_keys=True, default=str)
        if tx.id in seen:
            first_index, first_fp = seen[tx.id]
            if fingerprint == first_fp:
                duplicates.append(ExactDuplicate(index, tx.id, first_index))
            else:
                issues.append(ValidationIssue(
                    index, tx.id, "id",
                    f"id already used by record {first_index} with different content; first occurrence kept",
                ))
            continue
        seen[tx.id] = (index, fingerprint)
        transactions.append(tx)

    return transactions, issues, duplicates


def _parse_transaction(
    raw: Any, index: int, accounts: dict[str, Account]
) -> tuple[Transaction | None, list[ValidationIssue]]:
    if not isinstance(raw, dict):
        return None, [ValidationIssue(index, None, None, "transaction must be an object")]

    tx_id = raw.get("id") if isinstance(raw.get("id"), str) else None
    issues: list[ValidationIssue] = []

    def error(field: str, message: str) -> None:
        issues.append(ValidationIssue(index, tx_id, field, message))

    for field in REQUIRED_FIELDS:
        if raw.get(field) is None:
            error(field, "missing required field")
    if issues:
        return None, issues

    if tx_id is None or not tx_id.strip():
        error("id", "must be a non-empty string")

    account_id = raw["account_id"]
    if not isinstance(account_id, str) or account_id not in accounts:
        error("account_id", f"unknown account {account_id!r}")

    tx_date = _parse_date(raw["date"])
    if tx_date is None:
        error("date", f"must be a valid ISO date (YYYY-MM-DD), got {raw['date']!r}")

    amount, amount_error = _parse_amount(raw["amount"])
    if amount_error:
        error("amount", amount_error)

    try:
        tx_type = TxType(raw["type"])
    except ValueError:
        tx_type = None
        allowed = ", ".join(t.value for t in TxType)
        error("type", f"must be one of {allowed}; got {raw['type']!r}")

    merchant = raw.get("merchant")
    if merchant is None:
        merchant = ""
    elif not isinstance(merchant, str):
        error("merchant", "must be a string")

    category = raw.get("category")
    if category is not None and not isinstance(category, str):
        error("category", "must be a string or null")
    elif isinstance(category, str):
        category = category.strip() or None  # "" and "   " mean missing

    optional_ids = {}
    for field in ("transfer_id", "counterparty_account_id"):
        value = raw.get(field)
        if value is not None and not isinstance(value, str):
            error(field, "must be a string or null")
        optional_ids[field] = value or None

    if amount is not None and tx_type is not None:
        if tx_type in _MUST_BE_NEGATIVE and amount > 0:
            error("amount", f"{tx_type.value} must have a negative amount (money out)")
        elif tx_type in _MUST_BE_POSITIVE and amount < 0:
            error("amount", f"{tx_type.value} must have a positive amount (money in)")

    if issues:
        return None, issues

    return Transaction(
        id=tx_id,
        account_id=account_id,
        date=tx_date,
        merchant=merchant.strip(),
        amount=amount,
        type=tx_type,
        category=category,
        transfer_id=optional_ids["transfer_id"],
        counterparty_account_id=optional_ids["counterparty_account_id"],
        source_index=index,
    ), []


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_amount(value: Any) -> tuple[Decimal | None, str | None]:
    if isinstance(value, bool):
        return None, "must be a number, not a boolean"
    if isinstance(value, int):
        value = Decimal(value)
    elif isinstance(value, float):  # documents not loaded via load_document
        value = Decimal(repr(value))
    elif not isinstance(value, Decimal):
        return None, f"must be a number, got {type(value).__name__}"
    if not value.is_finite():
        return None, "must be finite"
    try:
        rounded = value.quantize(CENT)
    except InvalidOperation:
        return None, "is out of range"
    if value != rounded:
        return None, "must not have more than 2 decimal places"
    return rounded, None
