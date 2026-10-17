import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from finance.report import to_json
from finance.server import BadRequest, FinanceAPI, NotFound, make_server

from .helpers import ledger, tx


def sample_ledger():
    return ledger(
        tx("2026-09-01", 3000, "Payroll", type="income", category="Income"),
        tx("2026-09-03", -40, "Starbucks", account="credit_1", category="Dining", id="a"),
        tx("2026-09-03", -40, "Starbucks", account="credit_1", category="Dining", id="b"),  # double swipe
        tx("2026-10-02", -100, "Target", account="credit_1", category="Shopping"),
        tx("2026-10-05", 25, "Target", type="refund", account="credit_1", category=None),
        tx("2026-10-20", -180, "Payment to Card", type="transfer", transfer_id="x"),
        tx("2026-10-21", 180, "Payment Received", type="payment", account="credit_1", transfer_id="x"),
    )


def q(**params):
    return {k: v if isinstance(v, list) else [v] for k, v in params.items()}


class FinanceAPITests(unittest.TestCase):
    def setUp(self):
        self.api = FinanceAPI(sample_ledger())

    def test_meta(self):
        meta = self.api.handle("/api/meta", {})
        self.assertEqual([a["id"] for a in meta["accounts"]], ["checking_1", "savings_1", "credit_1"])
        self.assertEqual(meta["categories"], ["Dining", "Shopping"])
        self.assertEqual(str(meta["last_date"]), "2026-10-21")

    def test_summary_respects_filters_and_duplicate_toggle(self):
        kept = self.api.handle("/api/summary", q(start="2026-09-01", end="2026-09-30", drop_duplicates="false"))
        dropped = self.api.handle("/api/summary", q(start="2026-09-01", end="2026-09-30", drop_duplicates="true"))
        self.assertEqual(kept["totals"]["expenses"], 80)
        self.assertEqual(dropped["totals"]["expenses"], 40)
        json.loads(to_json(kept))  # serializable

    def test_date_range_like_the_ui_presets(self):
        summary = self.api.handle("/api/summary", q(start="2026-09-01", end="2026-10-31"))
        self.assertEqual(str(summary["filters"]["start"]), "2026-09-01")
        self.assertEqual(str(summary["filters"]["end"]), "2026-10-31")
        self.assertEqual(summary["totals"]["expenses"], 155)

    def test_transactions_paginate_newest_first_and_flag_duplicates(self):
        page = self.api.handle("/api/transactions", q(limit="2"))
        self.assertEqual(page["total"], 7)
        self.assertEqual([str(t["date"]) for t in page["items"]], ["2026-10-21", "2026-10-20"])
        everything = self.api.handle("/api/transactions", q(limit="50"))
        self.assertEqual([t["id"] for t in everything["items"] if t["probable_duplicate"]], ["b"])

    def test_transactions_kind_filter(self):
        page = self.api.handle("/api/transactions", q(kind=["internal_transfer"]))
        self.assertEqual(page["total"], 2)

    def test_rolling(self):
        result = self.api.handle("/api/rolling", q(window="7", start="2026-10-01"))
        self.assertEqual(result["window_days"], 7)
        self.assertEqual(str(result["points"][0]["date"]), "2026-10-01")

    def test_bad_input_is_a_400_not_a_crash(self):
        for query in (q(start="10/01/2026"), q(start="2026-10-02", end="2026-10-01"), q(limit="0"),
                      q(limit="abc"), q(drop_duplicates="maybe"), q(kind=["bogus"])):
            with self.subTest(query=query), self.assertRaises(BadRequest):
                self.api.handle("/api/transactions", query)

    def test_unknown_route(self):
        with self.assertRaises(NotFound):
            self.api.handle("/api/nope", {})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.static = tempfile.TemporaryDirectory()
        Path(self.static.name, "index.html").write_text("<!doctype html><title>ui</title>")
        self.server = make_server(sample_ledger(), "127.0.0.1", 0, Path(self.static.name))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.static.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as res:
            return res.status, res.headers["Content-Type"], res.read().decode()

    def test_api_and_spa_fallback(self):
        status, ctype, body = self.get("/api/summary?account=credit_1")
        self.assertEqual((status, ctype), (200, "application/json"))
        self.assertEqual(json.loads(body)["totals"]["expenses"], 155)
        self.assertIn("<title>ui</title>", self.get("/some/client/route")[2])

    def test_errors_are_json(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/summary?start=bad")
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("start", json.loads(ctx.exception.read())["error"])


if __name__ == "__main__":
    unittest.main()
