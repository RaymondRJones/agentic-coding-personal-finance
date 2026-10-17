"""The surprise requirement: a card payment from checking must not count as an expense twice."""

import unittest
from decimal import Decimal

from finance.analytics import cash_flow, spending_by_category
from finance.filters import TransactionFilter
from finance.models import Kind

from .helpers import ledger, tx


def card_month(*payment_legs):
    return ledger(
        tx("2026-10-01", 4000, "Payroll", type="income", category="Income"),
        tx("2026-10-03", -300, "Whole Foods", account="credit_1", category="Groceries"),
        tx("2026-10-04", -200, "Uber", account="credit_1", category="Transportation"),
        *payment_legs,
    )


class InternalTransferTests(unittest.TestCase):
    def test_linked_card_payment_is_not_an_expense(self):
        lg = card_month(
            tx("2026-10-20", -500, "Payment to Card", type="transfer", category="Transfer", transfer_id="x1"),
            tx("2026-10-21", 500, "Payment Received", type="payment", account="credit_1", transfer_id="x1"),
        )
        flow = cash_flow(lg.transactions)
        self.assertEqual(flow.expenses, Decimal("500"))  # the card purchases, once
        self.assertEqual(flow.income, Decimal("4000"))  # the card credit isn't income
        self.assertEqual(flow.internal_transfers, Decimal("500"))
        self.assertEqual(lg.transfer_pairs[0].method, "transfer_id")

    def test_unlinked_mislabeled_card_payment_is_still_detected(self):
        # No transfer_id, checking leg typed as a purchase in "Bills & Utilities".
        lg = card_month(
            tx("2026-10-20", -500, "CHASE CREDIT CRD AUTOPAY", category="Bills & Utilities"),
            tx("2026-10-22", 500, "AUTOPAY PAYMENT - THANK YOU", type="payment", account="credit_1", category=None),
        )
        self.assertEqual(cash_flow(lg.transactions).expenses, Decimal("500"))
        self.assertEqual(lg.transfer_pairs[0].method, "matched")
        self.assertNotIn("Bills & Utilities", spending_by_category(lg.transactions))

    def test_naive_sum_would_double_count(self):
        lg = card_month(
            tx("2026-10-20", -500, "Payment to Card", type="transfer", transfer_id="x1"),
            tx("2026-10-21", 500, "Payment Received", type="payment", account="credit_1", transfer_id="x1"),
        )
        naive = -sum(t.amount for t in lg.transactions if t.amount < 0)
        self.assertEqual(naive, Decimal("1000"))
        self.assertEqual(cash_flow(lg.transactions).expenses, Decimal("500"))

    def test_savings_transfer_affects_neither_side(self):
        lg = ledger(
            tx("2026-10-05", -1000, "Online Transfer to Savings", type="transfer", transfer_id="s1"),
            tx("2026-10-05", 1000, "Online Transfer from Checking", type="transfer",
               account="savings_1", transfer_id="s1"),
        )
        flow = cash_flow(lg.transactions)
        self.assertEqual((flow.income, flow.expenses), (0, 0))

    def test_ordinary_purchase_never_pairs_with_payment(self):
        # Same amount and dates, but the purchase has no transfer signal.
        lg = ledger(
            tx("2026-10-20", -45, "Chipotle", category="Dining"),
            tx("2026-10-21", 45, "Payment Received", type="payment", account="credit_1"),
        )
        self.assertEqual(lg.transfer_pairs, [])
        kinds = {t.merchant: t.kind for t in lg.transactions}
        self.assertEqual(kinds["Chipotle"], Kind.EXPENSE)
        self.assertEqual(kinds["Payment Received"], Kind.UNMATCHED_TRANSFER)

    def test_legs_outside_window_do_not_pair(self):
        lg = ledger(
            tx("2026-10-01", -500, "Online Transfer", type="transfer"),
            tx("2026-10-09", 500, "Payment Received", type="payment", account="credit_1"),
        )
        self.assertEqual(lg.transfer_pairs, [])

    def test_same_account_legs_do_not_pair(self):
        lg = ledger(
            tx("2026-10-01", -500, "Transfer", type="transfer"),
            tx("2026-10-01", 500, "Transfer", type="transfer"),
        )
        self.assertEqual(lg.transfer_pairs, [])

    def test_each_inflow_is_used_once(self):
        lg = ledger(
            tx("2026-10-01", -500, "Transfer out", type="transfer"),
            tx("2026-10-02", -500, "Transfer out", type="transfer"),
            tx("2026-10-02", 500, "Transfer in", type="transfer", account="savings_1"),
        )
        self.assertEqual(len(lg.transfer_pairs), 1)
        self.assertEqual(len(lg.unmatched_transfers), 1)

    def test_unmatched_external_transfer_is_excluded_and_surfaced(self):
        lg = ledger(tx("2026-10-01", -450, "Zelle Transfer - Roommate", type="transfer", category=None))
        flow = cash_flow(lg.transactions)
        self.assertEqual(flow.expenses, 0)
        self.assertEqual(flow.unmatched_transfers, Decimal("450"))
        self.assertEqual(len(lg.data_quality()["unmatched_transfers"]), 1)

    def test_filtering_to_one_account_keeps_transfer_classification(self):
        lg = card_month(
            tx("2026-10-20", -500, "Payment to Card", type="transfer", transfer_id="x1"),
            tx("2026-10-21", 500, "Payment Received", type="payment", account="credit_1", transfer_id="x1"),
        )
        checking_only = TransactionFilter(accounts={"checking_1"}).apply(lg.transactions)
        self.assertEqual(cash_flow(checking_only).expenses, 0)


if __name__ == "__main__":
    unittest.main()
