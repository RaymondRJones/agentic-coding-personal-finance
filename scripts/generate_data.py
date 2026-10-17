"""Generate a realistic, deterministic transactions file with known traps baked in.

Writes:
  data/transactions.json   the input (exactly --count records)
  data/ground_truth.json   what a correct engine must conclude, computed independently
                           from the generator's own bookkeeping

Traps included:
  * credit-card payments from checking (both legs), most linked by transfer_id,
    some unlinked and mislabeled as a "purchase" in "Bills & Utilities"
  * checking <-> savings transfers, and unmatched Zelle transfers
  * refunds (full and partial), some with no category
  * missing categories (null, "", and absent key)
  * exact duplicate records, id conflicts, and probable double-swipes
  * invalid records (bad dates, wrong types, wrong signs, unknown accounts, ...)
  * subscriptions incl. a price increase, a cancellation, and a weekly cadence
  * merchant-name variants ("UBER *TRIP" vs "Uber")
"""

from __future__ import annotations

import argparse
import calendar
import copy
import json
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from finance.models import normalize_merchant  # noqa: E402  (only used to avoid accidental collisions)

START, END = date(2025, 10, 1), date(2026, 9, 30)

ACCOUNTS = [
    {"id": "checking_1", "type": "checking", "name": "Everyday Checking"},
    {"id": "savings_1", "type": "savings", "name": "High-Yield Savings"},
    {"id": "credit_1", "type": "credit_card", "name": "Rewards Visa"},
    {"id": "credit_2", "type": "credit_card", "name": "Travel Card"},
]
CARDS = {"credit_1": ("Rewards Visa", 18), "credit_2": ("Travel Card", 22)}  # name, payment day
# (card, year, month) of payments that arrive unlinked and mislabeled.
UNLINKED_CARD_PAYMENTS = {("credit_1", 2026, 1), ("credit_1", 2026, 6), ("credit_2", 2026, 3)}

# names, category, min $, max $, weight, account weights (checking, credit_1, credit_2)
MERCHANTS = [
    (("Whole Foods", "WHOLE FOODS #10234"), "Groceries", 18, 160, 8, (3, 6, 1)),
    (("Trader Joe's",), "Groceries", 12, 110, 7, (3, 6, 1)),
    (("Safeway", "SAFEWAY #1189"), "Groceries", 8, 120, 5, (4, 5, 1)),
    (("Starbucks", "STARBUCKS #4471"), "Dining", 4, 9, 16, (2, 7, 1)),
    (("Chipotle",), "Dining", 9, 26, 7, (2, 7, 1)),
    (("Sweetgreen",), "Dining", 11, 22, 6, (2, 7, 1)),
    (("Olive Garden",), "Dining", 35, 110, 1.5, (1, 5, 4)),
    (("DoorDash", "DOORDASH*ORDER"), "Dining", 16, 60, 5, (1, 8, 1)),
    (("Uber", "UBER *TRIP"), "Transportation", 7, 42, 9, (1, 5, 4)),
    (("Lyft",), "Transportation", 7, 38, 4, (1, 5, 4)),
    (("Shell", "SHELL #57442"), "Transportation", 28, 70, 4, (4, 5, 1)),
    (("Amazon", "AMAZON.COM*MK1A2"), "Shopping", 6, 140, 9, (1, 8, 1)),
    (("Target", "TARGET #0342"), "Shopping", 8, 120, 5, (3, 6, 1)),
    (("Best Buy",), "Shopping", 40, 550, 0.6, (0, 7, 3)),
    (("CVS Pharmacy", "CVS/PHARMACY #0912"), "Health", 5, 55, 3, (4, 5, 1)),
    (("AMC Theatres",), "Entertainment", 12, 45, 2, (1, 6, 3)),
    (("Steam", "STEAM*GAMES"), "Entertainment", 5, 60, 1.5, (0, 9, 1)),
    (("Delta Air Lines",), "Travel", 180, 620, 0.35, (0, 1, 9)),
    (("Airbnb",), "Travel", 150, 850, 0.25, (0, 1, 9)),
    (("Home Depot",), "Home", 12, 240, 2, (3, 6, 1)),
]
ACCOUNT_ORDER = ("checking_1", "credit_1", "credit_2")

# merchant, category, amount(s), account, day-of-month (or None = weekly), months active
SUBSCRIPTIONS = [
    ("Netflix", "Entertainment", ("15.49", "17.99"), "credit_1", 12),
    ("Spotify", "Entertainment", ("11.99",), "credit_1", 3),
    ("Planet Fitness", "Health", ("24.99",), "credit_1", 1),
    ("iCloud Storage", "Software", ("2.99",), "credit_1", 20),
    ("Hulu", "Entertainment", ("7.99",), "credit_2", 9),  # cancelled after Feb 2026
    ("Comcast Xfinity", "Bills & Utilities", ("89.99",), "checking_1", 15),
    ("Verizon Wireless", "Bills & Utilities", ("85.00",), "credit_1", 25),
]

TRAP_COUNTS = {"refunds": 60, "probable_duplicates": 20, "exact_duplicates": 15, "id_conflicts": 3}


def cents(rng: random.Random, lo: float, hi: float) -> Decimal:
    return Decimal(rng.randint(int(lo * 100), int(hi * 100))) / 100


def skewed_cents(rng: random.Random, lo: float, hi: float) -> Decimal:
    """Most purchases sit near the low end of a merchant's range; a few are large."""
    return Decimal(int((lo + (hi - lo) * rng.random() ** 2.5) * 100)) / 100


def months_between(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def rec(account, day, merchant, amount, category, tx_type, kind, **extra):
    """A record plus generator-only metadata (keys starting with '_' are stripped on output)."""
    r = {"account_id": account, "date": day, "merchant": merchant, "amount": Decimal(amount),
         "category": category, "type": tx_type, "_kind": kind, "_true_category": category}
    r.update(extra)
    return r


def generate(seed: int, total: int):
    rng = random.Random(seed)
    records: list[dict] = []

    # --- Income -------------------------------------------------------------
    day = date(2025, 10, 3)
    while day <= END:
        records.append(rec("checking_1", day, "Acme Corp Payroll", "4150.00", "Income", "income", "income"))
        day += timedelta(days=14)
    for y, m in months_between(START, END):
        for d in (1, 15):
            records.append(rec("checking_1", date(y, m, d), "Globex Payroll", "3400.00", "Income", "income", "income"))
        last = date(y, m, calendar.monthrange(y, m)[1])
        records.append(rec("savings_1", last, "Interest Payment", cents(rng, 18, 42), "Interest", "income", "income"))

    # --- Fixed monthly bills & subscriptions ---------------------------------
    for y, m in months_between(START, END):
        records.append(rec("checking_1", date(y, m, 1), "Parkview Apartments", "-2800.00", "Housing",
                           "purchase", "expense"))
        records.append(rec("checking_1", date(y, m, rng.randint(6, 10)), "PG&E", -cents(rng, 70, 190),
                           "Bills & Utilities", "purchase", "expense"))
        for merchant, category, prices, account, dom in SUBSCRIPTIONS:
            if merchant == "Hulu" and (y, m) > (2026, 2):
                continue
            price = prices[-1] if len(prices) > 1 and (y, m) >= (2026, 5) else prices[0]
            records.append(rec(account, date(y, m, dom), merchant, -Decimal(price), category, "purchase", "expense"))
    day = date(2025, 10, 2)  # Thursdays
    while day <= END:
        if rng.random() > 0.08:  # occasionally skipped weeks
            records.append(rec("credit_1", day, "HelloFresh", "-69.99", "Groceries", "purchase", "expense"))
        day += timedelta(days=7)

    # --- Savings transfers & external (unmatched) transfers ------------------
    for y, m in months_between(START, END):
        tid = f"xfer_sav_{y}{m:02d}"
        d = date(y, m, 5)
        records.append(rec("checking_1", d, "Online Transfer to Savings", "-1000.00", "Transfer", "transfer",
                           "internal", transfer_id=tid, counterparty_account_id="savings_1"))
        records.append(rec("savings_1", d, "Online Transfer from Checking", "1000.00", "Transfer", "transfer",
                           "internal", transfer_id=tid, counterparty_account_id="checking_1"))
    d = date(2026, 4, 2)
    records.append(rec("savings_1", d, "Online Transfer to Checking", "-2500.00", "Transfer", "transfer",
                       "internal", transfer_id="xfer_sav_out_1", counterparty_account_id="checking_1"))
    records.append(rec("checking_1", d + timedelta(days=1), "Online Transfer from Savings", "2500.00", "Transfer",
                       "transfer", "internal", transfer_id="xfer_sav_out_1", counterparty_account_id="savings_1"))
    for d, amt in ((date(2025, 11, 28), "-450.00"), (date(2026, 3, 1), "-120.00"), (date(2026, 7, 19), "-600.00")):
        records.append(rec("checking_1", d, "Zelle Transfer - Roommate", amt, None, "transfer", "unmatched"))

    # --- Random everyday purchases (fills the file to exactly `total`) --------
    card_payment_legs = 2 * len(CARDS) * (len(list(months_between(START, END))) - 1)
    trap_records = sum(TRAP_COUNTS.values()) + len(INVALID_MUTATIONS)
    n_random = total - len(records) - card_payment_legs - trap_records
    if n_random < 0:
        raise SystemExit(f"--count {total} is too small for the fixed records")

    span = (END - START).days
    weights = [m[4] for m in MERCHANTS]
    used_keys = set()  # (account, merchant_key, amount, date) — keep accidental duplicates out
    for r in records:
        used_keys.add((r["account_id"], normalize_merchant(r["merchant"]), r["amount"], r["date"]))
    for _ in range(n_random):
        names, category, lo, hi, _, acct_weights = rng.choices(MERCHANTS, weights)[0]
        account = rng.choices(ACCOUNT_ORDER, acct_weights)[0]
        merchant = rng.choice(names)
        day = START + timedelta(days=rng.randint(0, span))
        while True:
            amount = -skewed_cents(rng, lo, hi)
            key = (account, normalize_merchant(merchant), amount, day)
            if key not in used_keys:
                used_keys.add(key)
                break
        records.append(rec(account, day, merchant, amount, category, "purchase", "expense", _random=True))

    # Missing categories: ~4% of random purchases, in three different spellings.
    for r in records:
        if r.get("_random") and rng.random() < 0.04:
            style = rng.choice(("null", "empty", "absent"))
            r["category"] = {"null": None, "empty": "", "absent": "_ABSENT_"}[style]

    # --- Refunds --------------------------------------------------------------
    candidates = [r for r in records if r.get("_random") and r["date"] <= END - timedelta(days=21)
                  and r["amount"] <= Decimal("-15")]
    for original in rng.sample(candidates, TRAP_COUNTS["refunds"]):
        full = rng.random() < 0.6
        amount = -original["amount"]
        if not full:
            amount = (amount * Decimal(rng.randint(20, 80)) / 100).quantize(Decimal("0.01"))
        category = original["_true_category"] if rng.random() < 0.6 else None
        r = rec(original["account_id"], original["date"] + timedelta(days=rng.randint(2, 20)),
                original["merchant"], amount, category, "refund", "refund")
        r["_true_category"] = original["_true_category"]
        records.append(r)

    # --- Credit-card payments (pay last month's net card activity) ------------
    card_activity = defaultdict(Decimal)
    for r in records:
        if r["account_id"] in CARDS and r["_kind"] in ("expense", "refund"):
            card_activity[(r["account_id"], r["date"].year, r["date"].month)] += r["amount"]
    months = list(months_between(START, END))
    for (py, pm), (y, m) in pairwise(months):
        for card, (card_name, pay_day) in CARDS.items():
            balance = -card_activity[(card, py, pm)]
            d = date(y, m, pay_day)
            if (card, y, m) in UNLINKED_CARD_PAYMENTS:
                # Bank feed lost the link and the aggregator miscategorized the checking leg.
                records.append(rec("checking_1", d, "CHASE CREDIT CRD AUTOPAY", -balance, "Bills & Utilities",
                                   "purchase", "internal", _unlinked=True))
                records.append(rec(card, d + timedelta(days=2), "AUTOPAY PAYMENT - THANK YOU", balance, None,
                                   "payment", "internal", _unlinked=True))
            else:
                tid = f"xfer_cc_{card}_{y}{m:02d}"
                records.append(rec("checking_1", d, f"Payment to {card_name}", -balance, "Transfer", "transfer",
                                   "internal", transfer_id=tid, counterparty_account_id=card))
                records.append(rec(card, d + timedelta(days=1), "Payment Received - Thank You", balance,
                                   "Credit Card Payment", "payment", "internal", transfer_id=tid,
                                   counterparty_account_id="checking_1"))

    # --- Probable duplicates (double swipes: new id, same everything else) ----
    swipeable = [r for r in records if r.get("_random")]
    for original in rng.sample(swipeable, TRAP_COUNTS["probable_duplicates"]):
        dup = copy.deepcopy(original)
        dup["_dup_of"] = original
        dup.pop("_random")
        records.append(dup)

    # --- Assign ids in date order ---------------------------------------------
    records.sort(key=lambda r: (r["date"], r["account_id"], r["merchant"], r["amount"]))
    for i, r in enumerate(records, start=1):
        r["id"] = f"tx_{i:05d}"

    output = [to_output(r) for r in records]

    # --- Exact duplicates, id conflicts, invalid records -----------------------
    singles = [i for i, r in enumerate(records) if r.get("_random")]
    exact_ids, conflict_ids = [], []
    originals = [output[i] for i in rng.sample(singles, TRAP_COUNTS["exact_duplicates"] + TRAP_COUNTS["id_conflicts"])]
    for original in originals:
        idx = next(i for i, o in enumerate(output) if o is original)  # positions shift as we insert
        clone = copy.deepcopy(original)
        if len(exact_ids) < TRAP_COUNTS["exact_duplicates"]:
            exact_ids.append(clone["id"])
        else:
            clone["amount"] = round(clone["amount"] - 1.0, 2)
            conflict_ids.append(clone["id"])
        output.insert(min(len(output), idx + rng.randint(1, 40)), clone)

    template = to_output(records[singles[0]])
    invalid = []
    for n, mutate in enumerate(INVALID_MUTATIONS, start=1):
        bad = dict(template, id=f"tx_bad_{n:02d}")
        mutate(bad)
        invalid.append(bad)
        output.insert(rng.randint(0, len(output)), bad)

    assert len(output) == total, (len(output), total)
    document = {"accounts": ACCOUNTS, "transactions": output}
    truth = ground_truth(records, exact_ids, conflict_ids, invalid)
    return document, truth


def _drop(field):
    return lambda r: r.pop(field)


def _set(field, value):
    return lambda r: r.__setitem__(field, value)


INVALID_MUTATIONS = [
    _drop("amount"),
    _set("amount", "12.50"),
    _set("date", "2026-02-30"),
    _set("date", "10/05/2026"),
    _set("account_id", "checking_9"),
    _set("type", "bonus"),
    _set("amount", 45.00),  # positive purchase
    _set("amount", -12.345),
    _drop("id"),
    _drop("date"),
    _set("amount", True),
    lambda r: r.update(type="income", amount=-100.00, merchant="Acme Corp Payroll", category="Income"),
]


def to_output(r: dict) -> dict:
    out = {"id": r["id"], "account_id": r["account_id"], "date": r["date"].isoformat(),
           "merchant": r["merchant"], "amount": float(r["amount"]), "category": r["category"], "type": r["type"]}
    if out["category"] == "_ABSENT_":
        del out["category"]
    for key in ("transfer_id", "counterparty_account_id"):
        if key in r:
            out[key] = r[key]
    return out


def ground_truth(records, exact_ids, conflict_ids, invalid) -> dict:
    """Independent bookkeeping: what the engine should report with probable duplicates dropped."""
    months = defaultdict(lambda: {"income": Decimal(0), "expenses": Decimal(0)})
    categories = defaultdict(Decimal)
    for r in records:
        if "_dup_of" in r:
            continue
        month = r["date"].strftime("%Y-%m")
        if r["_kind"] == "income":
            months[month]["income"] += r["amount"]
        elif r["_kind"] in ("expense", "refund"):
            months[month]["expenses"] -= r["amount"]
            categories[r["_true_category"]] -= r["amount"]

    return {
        "note": "Totals assume probable duplicates are dropped (summary --drop-probable-duplicates).",
        "monthly": {m: {k: float(v) for k, v in vals.items()} for m, vals in sorted(months.items())},
        "spending_by_category": {k: float(v) for k, v in sorted(categories.items())},
        "internal_transfer_pairs": sum(1 for r in records if r["_kind"] == "internal") // 2,
        "unlinked_card_payment_ids": [r["id"] for r in records if r.get("_unlinked")],
        "unmatched_transfer_ids": [r["id"] for r in records if r["_kind"] == "unmatched"],
        "exact_duplicate_ids": sorted(exact_ids),
        "id_conflict_ids": sorted(conflict_ids),
        "invalid_record_ids": [r.get("id") for r in invalid],
        "probable_duplicate_pairs": sorted([r["_dup_of"]["id"], r["id"]] for r in records if "_dup_of" in r),
        "missing_category_ids": sorted(
            r["id"] for r in records
            if r["category"] in (None, "", "_ABSENT_") and r["_kind"] in ("expense", "refund")
        ),
        "recurring_merchants": {
            "active": sorted([s[0] for s in SUBSCRIPTIONS if s[0] != "Hulu"] + ["HelloFresh", "Parkview Apartments"]),
            "inactive": ["Hulu"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "transactions.json")
    parser.add_argument("--truth", type=Path, default=ROOT / "data" / "ground_truth.json")
    args = parser.parse_args()

    document, truth = generate(args.seed, args.count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    args.truth.write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(document['transactions'])} transactions to {args.out}")
    print(f"wrote ground truth to {args.truth}")


if __name__ == "__main__":
    main()
