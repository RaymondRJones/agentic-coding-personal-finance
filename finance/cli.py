"""Command-line interface. Every command prints JSON to stdout (or --output)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .analytics import (
    monthly_cash_flow,
    rolling_spending_average,
    spending_by_category,
    top_merchants,
)
from .duplicates import find_probable_duplicates
from .filters import TransactionFilter
from .ledger import load_ledger
from .models import money
from .report import build_summary, to_json
from .subscriptions import detect_recurring


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(args)
    try:
        ledger = load_ledger(args.file, strict=args.strict)
        flt = TransactionFilter(
            start=args.start, end=args.end,
            accounts=frozenset(args.account or ()),
            categories=frozenset(args.category or ()),
            merchant=args.merchant,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = args.handler(ledger, flt, args)
    text = to_json(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 1 if args.command == "validate" and ledger.issues else 0


def _serve(args) -> int:
    from .server import serve  # only the serve command needs http.server

    try:
        ledger = load_ledger(args.file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    serve(ledger, args.host, args.port, args.static)
    return 0


def _summary(ledger, flt, args):
    return build_summary(ledger, flt, top_n=args.top, drop_probable_duplicates=args.drop_probable_duplicates)


def _validate(ledger, flt, args):
    return ledger.data_quality()


def _transactions(ledger, flt, args):
    txs = flt.apply(ledger.transactions)
    return {"count": len(txs), "transactions": [t.to_dict() for t in txs[: args.limit]]}


def _cash_flow(ledger, flt, args):
    return {month: flow.to_dict() for month, flow in monthly_cash_flow(flt.apply(ledger.transactions)).items()}


def _categories(ledger, flt, args):
    return {k: money(v) for k, v in spending_by_category(flt.apply(ledger.transactions)).items()}


def _top_merchants(ledger, flt, args):
    return [m.to_dict() for m in top_merchants(flt.apply(ledger.transactions), args.top)]


def _duplicates(ledger, flt, args):
    groups = find_probable_duplicates(flt.apply(ledger.transactions), window_days=args.window)
    return {
        "exact_duplicates_removed": len(ledger.exact_duplicates),
        "probable_duplicate_groups": [g.to_dict() for g in groups],
    }


def _subscriptions(ledger, flt, args):
    history = flt.without_dates().apply(ledger.transactions)
    return [c.to_dict() for c in detect_recurring(history, as_of=ledger.as_of)]


def _rolling(ledger, flt, args):
    history = flt.without_dates().apply(ledger.transactions)
    points = rolling_spending_average(history, start=flt.start, end=flt.end, window_days=args.window)
    return [p.to_dict() for p in points]


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("file", help="path to the transactions JSON file")
    common.add_argument("--start", type=date.fromisoformat, help="inclusive start date (YYYY-MM-DD)")
    common.add_argument("--end", type=date.fromisoformat, help="inclusive end date (YYYY-MM-DD)")
    common.add_argument("--account", action="append", help="account id (repeatable)")
    common.add_argument("--category", action="append", help="category (repeatable, case-insensitive)")
    common.add_argument("--merchant", help="merchant name substring (case-insensitive)")
    common.add_argument("--strict", action="store_true", help="fail if any record is invalid")
    common.add_argument("-o", "--output", help="write JSON here instead of stdout")

    parser = argparse.ArgumentParser(prog="finance", description="Personal finance analytics engine")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text):
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.set_defaults(handler=handler)
        return p

    p = add("summary", _summary, "full monthly financial summary")
    p.add_argument("--top", type=_non_negative_int, default=5, help="top N merchants per month (default 5)")
    p.add_argument("--drop-probable-duplicates", action="store_true", help="exclude probable duplicates from totals")
    add("validate", _validate, "data-quality report; exit 1 if any record was rejected")
    p = add("transactions", _transactions, "list filtered transactions")
    p.add_argument("--limit", type=_non_negative_int, default=50)
    add("cash-flow", _cash_flow, "monthly income, expenses, and net cash flow")
    add("categories", _categories, "net spending by category")
    p = add("top-merchants", _top_merchants, "top N merchants by net spending")
    p.add_argument("--top", "-n", type=_non_negative_int, default=10)
    p = add("duplicates", _duplicates, "probable duplicate transactions")
    p.add_argument("--window", type=_non_negative_int, default=0, help="max days apart (default 0 = same day)")
    add("subscriptions", _subscriptions, "recurring charges")
    p = add("rolling", _rolling, "rolling N-day spending average")
    p.add_argument("--window", type=_positive_int, default=30)

    p = sub.add_parser("serve", help="serve the JSON API and the web UI")
    p.add_argument("file", help="path to the transactions JSON file")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=_non_negative_int, default=8000)
    p.add_argument("--static", type=Path, default=Path(__file__).resolve().parent.parent / "web" / "dist",
                   help="directory of the built UI (default: web/dist)")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
