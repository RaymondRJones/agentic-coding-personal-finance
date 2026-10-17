import unittest
from datetime import date
from decimal import Decimal

from finance.analytics import (
    cash_flow,
    monthly_cash_flow,
    rolling_spending_average,
    spending_by_category,
    spending_by_merchant,
    top_merchants,
)
from finance.duplicates import drop_duplicates, find_probable_duplicates
from finance.filters import TransactionFilter
from finance.models import UNCATEGORIZED, normalize_merchant
from finance.subscriptions import detect_recurring

from .helpers import ledger, tx


class CashFlowTests(unittest.TestCase):
    def test_monthly_income_expenses_net(self):
        lg = ledger(
            tx("2026-09-01", 3000, "Payroll", type="income", category="Income"),
            tx("2026-09-10", -1000, "Rent"),
            tx("2026-10-01", 3000, "Payroll", type="income", category="Income"),
            tx("2026-10-02", -250.25, "Groceries"),
            tx("2026-10-03", -10, "Bank Fee", type="fee"),
        )
        months = monthly_cash_flow(lg.transactions)
        self.assertEqual(list(months), ["2026-09", "2026-10"])
        self.assertEqual(months["2026-10"].expenses, Decimal("260.25"))
        self.assertEqual(months["2026-10"].net_cash_flow, Decimal("2739.75"))
        self.assertEqual(months["2026-09"].savings_rate, Decimal("0.6667"))

    def test_empty_months_are_filled(self):
        lg = ledger(tx("2026-01-05", -10), tx("2026-03-05", -10))
        months = monthly_cash_flow(lg.transactions)
        self.assertEqual(list(months), ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(months["2026-02"].expenses, 0)

    def test_refund_reduces_expenses_not_income(self):
        lg = ledger(
            tx("2026-10-01", -100, "Target", category="Shopping"),
            tx("2026-10-05", 40, "Target", type="refund", category="Shopping"),
        )
        flow = cash_flow(lg.transactions)
        self.assertEqual((flow.income, flow.gross_spend, flow.refunds, flow.expenses), (0, 100, 40, 60))

    def test_savings_rate_undefined_without_income(self):
        self.assertIsNone(cash_flow(ledger(tx("2026-10-01", -5)).transactions).savings_rate)


class CategoryTests(unittest.TestCase):
    def test_missing_category_inferred_from_merchant(self):
        lg = ledger(
            tx("2026-10-01", -50, "Whole Foods", category="Groceries"),
            tx("2026-10-02", -30, "WHOLE FOODS #10234", category=None),
            tx("2026-10-03", -20, "Whole Foods", category=""),
        )
        self.assertEqual(spending_by_category(lg.transactions), {"Groceries": Decimal("100")})
        self.assertEqual(sum(t.category_inferred for t in lg.transactions), 2)

    def test_absent_key_and_unknown_merchant_is_uncategorized(self):
        record = tx("2026-10-01", -12, "Mystery Shop")
        del record["category"]
        lg = ledger(record)
        self.assertEqual(spending_by_category(lg.transactions), {UNCATEGORIZED: Decimal("12")})

    def test_uncategorized_refund_nets_against_original_category(self):
        lg = ledger(
            tx("2026-10-01", -100, "Best Buy", category="Electronics"),
            tx("2026-10-09", 100, "Best Buy", type="refund", category=None),
            tx("2026-10-10", -10, "Starbucks", category="Dining"),
        )
        self.assertEqual(spending_by_category(lg.transactions), {"Dining": Decimal("10"), "Electronics": 0})


class MerchantTests(unittest.TestCase):
    def test_normalization(self):
        for raw, key in [("UBER *TRIP", "uber"), ("Uber", "uber"), ("AMAZON.COM*MK1A2", "amazon"),
                         ("STARBUCKS #4471", "starbucks"), ("CVS/PHARMACY #0912", "cvs pharmacy"),
                         ("7-Eleven", "7 eleven")]:
            self.assertEqual(normalize_merchant(raw), key, raw)

    def test_top_n_groups_variants_and_nets_refunds(self):
        lg = ledger(
            tx("2026-10-01", -30, "Uber"), tx("2026-10-02", -20, "UBER *TRIP"),
            tx("2026-10-03", -45, "Lyft"), tx("2026-10-04", -100, "Target"),
            tx("2026-10-05", 70, "Target", type="refund"),
        )
        top = top_merchants(lg.transactions, 2)
        self.assertEqual([(m.merchant_key, m.total) for m in top], [("uber", 50), ("lyft", 45)])
        self.assertEqual(top_merchants(lg.transactions, 0), [])

    def test_ties_are_broken_deterministically(self):
        lg = ledger(tx("2026-10-01", -10, "Beta"), tx("2026-10-01", -10, "Alpha"))
        self.assertEqual([m.merchant for m in spending_by_merchant(lg.transactions)], ["Alpha", "Beta"])

    def test_transfers_never_appear_in_merchants(self):
        lg = ledger(tx("2026-10-01", -500, "Online Transfer", type="transfer"))
        self.assertEqual(top_merchants(lg.transactions), [])


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.lg = ledger(
            tx("2026-09-30", -1, "Uber", category="Transportation"),
            tx("2026-10-01", -2, "UBER *TRIP", category="Transportation", account="credit_1"),
            tx("2026-10-15", -3, "Whole Foods", category="Groceries"),
            tx("2026-10-31", -4, "Target", category="Shopping"),
            tx("2026-11-01", -5, "Target", category="Shopping"),
        )

    def amounts(self, **criteria):
        return [-int(t.amount) for t in TransactionFilter(**criteria).apply(self.lg.transactions)]

    def test_date_range_is_inclusive(self):
        self.assertEqual(self.amounts(start=date(2026, 10, 1), end=date(2026, 10, 31)), [2, 3, 4])

    def test_account_category_merchant(self):
        self.assertEqual(self.amounts(accounts={"credit_1"}), [2])
        self.assertEqual(self.amounts(categories={"shopping"}), [4, 5])
        self.assertEqual(self.amounts(merchant="uber"), [1, 2])

    def test_combined(self):
        self.assertEqual(self.amounts(merchant="uber", start=date(2026, 10, 1)), [2])

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            TransactionFilter(start=date(2026, 2, 1), end=date(2026, 1, 1))


class DuplicateTests(unittest.TestCase):
    def test_probable_duplicates_flagged_and_droppable(self):
        lg = ledger(
            tx("2026-10-01", -8.75, "Starbucks", id="a"),
            tx("2026-10-01", -8.75, "STARBUCKS #4471", id="b"),
            tx("2026-10-01", -8.75, "Starbucks", account="credit_1", id="c"),  # other account
            tx("2026-10-02", -8.75, "Starbucks", id="d"),  # next day
        )
        groups = find_probable_duplicates(lg.transactions)
        self.assertEqual([[t.id for t in g.transactions] for g in groups], [["a", "b"]])
        self.assertEqual(len(find_probable_duplicates(lg.transactions, window_days=1)[0].transactions), 3)
        self.assertEqual([t.id for t in drop_duplicates(lg.transactions, groups)], ["a", "c", "d"])

    def test_transfer_legs_are_not_duplicates(self):
        lg = ledger(
            tx("2026-10-01", -100, "Transfer", type="transfer"),
            tx("2026-10-01", -100, "Transfer", type="transfer"),
        )
        self.assertEqual(find_probable_duplicates(lg.transactions), [])


class RecurringTests(unittest.TestCase):
    def monthly(self, merchant, amounts, start_month=1, day=12, **kw):
        return [tx(f"2026-{start_month + i:02d}-{day:02d}", -a, merchant, **kw) for i, a in enumerate(amounts)]

    def test_monthly_subscription_with_price_increase(self):
        lg = ledger(*self.monthly("Netflix", [15.49] * 4 + [17.99] * 4))
        (charge,) = detect_recurring(lg.transactions, as_of=date(2026, 8, 20))
        self.assertEqual((charge.merchant, charge.cadence), ("Netflix", "monthly"))
        self.assertEqual(charge.current_amount, Decimal("17.99"))
        self.assertEqual(charge.next_expected, date(2026, 9, 12))
        self.assertEqual(charge.annualized_cost, Decimal("215.88"))
        self.assertEqual(len(charge.price_changes), 1)
        self.assertTrue(charge.active)

    def test_cancelled_subscription_is_inactive(self):
        lg = ledger(*self.monthly("Hulu", [7.99] * 4), tx("2026-09-01", -5, "Other"))
        (charge,) = detect_recurring(lg.transactions)
        self.assertFalse(charge.active)

    def test_variable_bill_and_irregular_spending_are_not_subscriptions(self):
        lg = ledger(
            *self.monthly("PG&E", [80, 142, 95, 171, 110, 66]),
            *[tx(f"2026-03-{d:02d}", -9.50, "Chipotle") for d in (1, 3, 4, 9, 17, 18, 30)],
        )
        self.assertEqual(detect_recurring(lg.transactions), [])

    def test_weekly_with_a_skipped_week(self):
        days = ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-29", "2026-02-05", "2026-02-12"]
        lg = ledger(*[tx(d, -69.99, "HelloFresh") for d in days])
        self.assertEqual(detect_recurring(lg.transactions)[0].cadence, "weekly")

    def test_too_few_occurrences(self):
        self.assertEqual(detect_recurring(ledger(*self.monthly("Spotify", [11.99] * 2)).transactions), [])


class RollingAverageTests(unittest.TestCase):
    def test_trailing_window_includes_zero_days(self):
        lg = ledger(tx("2026-01-01", -30), tx("2026-01-03", -60), tx("2026-01-05", 30, type="refund"))
        points = rolling_spending_average(lg.transactions, window_days=3)
        self.assertEqual([(p.date.day, p.window_total) for p in points],
                         [(1, 30), (2, 30), (3, 90), (4, 60), (5, 30)])
        self.assertEqual(points[2].daily_average, Decimal(30))
        self.assertEqual([p.complete_window for p in points], [False, False, True, True, True])

    def test_history_before_start_feeds_window(self):
        lg = ledger(tx("2026-01-01", -300), tx("2026-01-31", -30))
        points = rolling_spending_average(lg.transactions, start=date(2026, 1, 30), end=date(2026, 1, 31))
        self.assertEqual([p.window_total for p in points], [300, 30])  # Jan 1 drops out on Jan 31

    def test_transfers_excluded(self):
        lg = ledger(tx("2026-01-01", -500, "Online Transfer", type="transfer"))
        self.assertEqual(rolling_spending_average(lg.transactions), [])


if __name__ == "__main__":
    unittest.main()
