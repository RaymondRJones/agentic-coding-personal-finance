import json
import tempfile
import unittest
from decimal import Decimal

from finance.ledger import build_ledger, load_ledger
from finance.validation import LedgerFormatError, ValidationError

from .helpers import ledger, tx


class RequiredFieldTests(unittest.TestCase):
    def test_valid_record_is_parsed_with_exact_decimal(self):
        lg = ledger(tx("2026-10-01", -85.50, "Whole Foods"))
        self.assertEqual(len(lg.transactions), 1)
        self.assertEqual(lg.transactions[0].amount, Decimal("-85.50"))
        self.assertEqual(lg.issues, [])

    def test_each_required_field_is_enforced(self):
        for field in ("id", "account_id", "date", "amount", "type"):
            with self.subTest(field=field):
                record = tx("2026-10-01", -10)
                del record[field]
                lg = ledger(record)
                self.assertEqual(lg.transactions, [])
                self.assertEqual(lg.issues[0].field, field)

    def test_null_counts_as_missing(self):
        lg = ledger(tx("2026-10-01", None))
        self.assertEqual(lg.issues[0].message, "missing required field")

    def test_merchant_is_optional(self):
        record = tx("2026-10-01", -10)
        del record["merchant"]
        self.assertEqual(ledger(record).transactions[0].merchant, "")


class FieldFormatTests(unittest.TestCase):
    def assertRejected(self, record, field):
        lg = ledger(record)
        self.assertEqual(lg.transactions, [], lg.issues)
        self.assertIn(field, [i.field for i in lg.issues])

    def test_bad_dates(self):
        for value in ("2026-02-30", "10/05/2026", "20261005", 20261005, "2026-1-5"):
            with self.subTest(value=value):
                self.assertRejected(tx(value, -10), "date")

    def test_bad_amounts(self):
        for value in ("12.50", True, 12.345, float("nan"), Decimal("1e40")):
            with self.subTest(value=value):
                self.assertRejected(tx("2026-10-01", value), "amount")

    def test_unknown_account_and_type(self):
        self.assertRejected(tx("2026-10-01", -10, account="nope"), "account_id")
        self.assertRejected(tx("2026-10-01", -10, type="bonus"), "type")

    def test_sign_rules(self):
        self.assertRejected(tx("2026-10-01", 10, type="purchase"), "amount")
        self.assertRejected(tx("2026-10-01", -10, type="income"), "amount")
        self.assertRejected(tx("2026-10-01", -10, type="refund"), "amount")

    def test_one_bad_record_does_not_sink_the_file(self):
        lg = ledger(tx("2026-10-01", -10), tx("bad", -10), tx("2026-10-02", -20))
        self.assertEqual(len(lg.transactions), 2)
        self.assertEqual(len(lg.issues), 1)
        self.assertEqual(lg.issues[0].index, 1)

    def test_strict_mode_raises(self):
        with self.assertRaises(ValidationError):
            ledger(tx("bad", -10), strict=True)

    def test_structural_errors_always_raise(self):
        for doc in ([], {"accounts": []}, {"accounts": {}, "transactions": []}):
            with self.subTest(doc=doc), self.assertRaises(LedgerFormatError):
                build_ledger(doc)


class DuplicateIdTests(unittest.TestCase):
    def test_exact_duplicate_is_dropped_and_reported(self):
        record = tx("2026-10-01", -10, id="a")
        lg = ledger(record, dict(record))
        self.assertEqual(len(lg.transactions), 1)
        self.assertEqual(len(lg.exact_duplicates), 1)
        self.assertEqual(lg.issues, [])

    def test_id_conflict_keeps_first_and_reports_issue(self):
        lg = ledger(tx("2026-10-01", -10, id="a"), tx("2026-10-01", -99, id="a"))
        self.assertEqual([t.amount for t in lg.transactions], [Decimal("-10.00")])
        self.assertIn("different content", lg.issues[0].message)


class LoadFromFileTests(unittest.TestCase):
    def test_floats_are_parsed_as_decimals(self):
        doc = {"accounts": [{"id": "a", "type": "checking"}],
               "transactions": [tx("2026-10-01", -0.1, account="a"), tx("2026-10-01", -0.2, account="a")]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doc, fh)
        total = sum(t.amount for t in load_ledger(fh.name).transactions)
        self.assertEqual(total, Decimal("-0.30"))  # 0.1 + 0.2 == 0.3 exactly, unlike float


if __name__ == "__main__":
    unittest.main()
