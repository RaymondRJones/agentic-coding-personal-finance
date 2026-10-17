"""Run the engine over the generated 5,000-record file and check it against the generator's ground truth."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from finance.analytics import monthly_cash_flow, spending_by_category
from finance.cli import main
from finance.duplicates import drop_duplicates, find_probable_duplicates
from finance.ledger import load_ledger
from finance.models import Kind
from finance.report import build_summary, to_json
from finance.subscriptions import detect_recurring

ROOT = Path(__file__).resolve().parent.parent


class GroundTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data, truth = Path(cls.tmp.name, "tx.json"), Path(cls.tmp.name, "truth.json")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_data.py"), "--seed", "7",
                        "--out", str(data), "--truth", str(truth)], check=True, capture_output=True)
        cls.data_path = data
        cls.truth = json.loads(truth.read_text())
        cls.ledger = load_ledger(data)
        cls.groups = find_probable_duplicates(cls.ledger.transactions)
        cls.clean = drop_duplicates(cls.ledger.transactions, cls.groups)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_record_count(self):
        self.assertEqual(self.ledger.total_records, 5000)

    def test_invalid_records_and_id_conflicts_rejected(self):
        rejected_ids = {i.tx_id for i in self.ledger.issues}
        self.assertEqual(rejected_ids, set(self.truth["invalid_record_ids"]) | set(self.truth["id_conflict_ids"]))

    def test_exact_duplicates_removed(self):
        self.assertEqual(sorted(d.tx_id for d in self.ledger.exact_duplicates), self.truth["exact_duplicate_ids"])

    def test_probable_duplicates_found(self):
        found = sorted([t.id for t in g.transactions] for g in self.groups)
        self.assertEqual(found, self.truth["probable_duplicate_pairs"])

    def test_internal_transfers_including_unlinked(self):
        self.assertEqual(len(self.ledger.transfer_pairs), self.truth["internal_transfer_pairs"])
        by_id = {t.id: t for t in self.ledger.transactions}
        for tx_id in self.truth["unlinked_card_payment_ids"]:
            self.assertIs(by_id[tx_id].kind, Kind.INTERNAL_TRANSFER, tx_id)
        self.assertEqual(sorted(t.id for t in self.ledger.unmatched_transfers), self.truth["unmatched_transfer_ids"])

    def test_monthly_income_and_expenses_match_to_the_cent(self):
        months = monthly_cash_flow(self.clean)
        for month, expected in self.truth["monthly"].items():
            with self.subTest(month=month):
                self.assertEqual(months[month].income, Decimal(str(expected["income"])))
                self.assertEqual(months[month].expenses, Decimal(str(expected["expenses"])))

    def test_category_totals_recover_missing_categories(self):
        actual = spending_by_category(self.clean)
        expected = {k: Decimal(str(v)) for k, v in self.truth["spending_by_category"].items()}
        self.assertEqual(actual, dict(sorted(expected.items(), key=lambda kv: (-kv[1], kv[0]))))

    def test_missing_categories_are_inferred(self):
        by_id = {t.id: t for t in self.ledger.transactions}
        for tx_id in self.truth["missing_category_ids"]:
            self.assertTrue(by_id[tx_id].category_inferred, tx_id)

    def test_recurring_charges(self):
        charges = detect_recurring(self.clean)
        expected = self.truth["recurring_merchants"]
        self.assertEqual(sorted(c.merchant for c in charges if c.active), expected["active"])
        self.assertEqual(sorted(c.merchant for c in charges if not c.active), expected["inactive"])

    def test_summary_is_valid_json(self):
        summary = json.loads(to_json(build_summary(self.ledger, top_n=3, drop_probable_duplicates=True)))
        self.assertEqual(len(summary["months"]), 12)
        first = summary["months"][0]
        for key in ("income", "expenses", "net_cash_flow", "spending_by_category", "top_merchants",
                    "rolling_30_day_daily_average_at_month_end"):
            self.assertIn(key, first)
        self.assertEqual(len(first["top_merchants"]), 3)

    def test_cli_summary_with_filters(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["summary", str(self.data_path), "--start", "2026-03-01", "--end", "2026-03-31",
                         "--account", "credit_1", "--top", "2"])
        self.assertEqual(code, 0)
        summary = json.loads(out.getvalue())
        self.assertEqual([m["month"] for m in summary["months"]], ["2026-03"])
        self.assertEqual(summary["totals"]["income"], 0)

    def test_subscription_status_does_not_depend_on_filter(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["subscriptions", str(self.data_path), "--merchant", "hulu"])
        (hulu,) = json.loads(out.getvalue())
        self.assertFalse(hulu["active"])

    def test_cli_validate_exit_code(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["validate", str(self.data_path)]), 1)


if __name__ == "__main__":
    unittest.main()
