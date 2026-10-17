"""The JSON the CLI and API actually emit — what the UI receives."""

import json
import unittest
from datetime import date
from decimal import Decimal

from finance.report import build_summary, to_json

from .helpers import ledger, tx


class SerializationTests(unittest.TestCase):
    def test_dates_are_iso_strings(self):
        self.assertEqual(json.loads(to_json({"d": date(2026, 10, 7)})), {"d": "2026-10-07"})

    def test_money_keeps_cents(self):
        self.assertEqual(json.loads(to_json({"amount": Decimal("17.99")})), {"amount": 17.99})
        self.assertEqual(json.loads(to_json({"amount": Decimal("-0.50")})), {"amount": -0.5})

    def test_summary_round_trips(self):
        lg = ledger(
            tx("2026-10-01", 1000, "Payroll", type="income", category="Income"),
            tx("2026-10-12", -15.49, "Netflix", category="Entertainment"),
        )
        summary = json.loads(to_json(build_summary(lg)))
        month = summary["months"][0]
        self.assertEqual(month["month"], "2026-10")
        self.assertEqual(month["expenses"], 15.49)
        self.assertEqual(month["net_cash_flow"], 984.51)
        self.assertEqual(summary["filters"]["start"], None)


if __name__ == "__main__":
    unittest.main()
