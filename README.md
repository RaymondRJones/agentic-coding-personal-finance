# Personal Finance Analytics Engine

A transaction analytics engine written in Python 3.11+ using only the standard library.
It reads a JSON file of accounts and transactions and produces monthly cash flow,
spending breakdowns, duplicate and subscription detection, rolling averages, and a full
monthly summary in JSON.

## Quick start

```bash
python3 scripts/generate_data.py              # data/transactions.json (5,000 records) + data/ground_truth.json
python3 -m finance summary data/transactions.json --drop-probable-duplicates -o reports/summary.json
python3 -m unittest discover -s tests -t .    # 75 tests
ruff check .                                  # optional lint (config in pyproject.toml)
```

## The challenge: three bugs reported by users

This app is a personal finance budgeting and projection tool. Users have reported three
problems with the dashboard. All three are in the **Python backend** (`finance/`). The tests
and the web UI are correct, and the UI only displays what the API returns.

Right now `python3 -m unittest discover -s tests -t .` reports **9 failing tests**. When you're
done, all 75 should pass and the dashboard should look right.

### Run it and see the bugs

```bash
python3 -m finance serve data/transactions.json      # terminal 1: API on :8000
(cd web && npm install && npm run dev)                # terminal 2: open http://localhost:5173
python3 -m unittest discover -s tests -t .            # terminal 3: the test suite
```

The API loads the code once at startup. **Restart `finance serve` after each fix** to see the
change in the UI. You can also call the API directly, e.g.
`curl 'localhost:8000/api/rolling?window=30'`.

### The bug reports

1. **"My Groceries category is always negative."** Open **Spending by category**: Groceries,
   and in fact every category, shows a negative amount, and the list is in the wrong order.
   The Spending total at the top of the page is still correct, and so is **Top merchants**.
2. **"The Daily spending, 30-day average chart is completely empty."** The chart says there's
   no spending, and the "Daily spending, last 30 days" stat shows "—", for every date range and filter,
   even though the rest of the dashboard shows plenty of spending.
3. **"The 6 months / 3 months / 30 days buttons don't work."** Choosing any of them shows a
   red error from the backend: `end must be YYYY-MM-DD`. Clicking a month in the Cash flow
   chart fails the same way. "All time" works. Look at what the UI actually sends.

The three bugs are independent, so you can fix them in any order. What we're looking for: how
you go from a symptom in the UI or a failing test to the cause in the code, and whether you can
explain *why* each bug happens, not just what to change.

## Web UI

A dashboard in `web/` (Vite + React + TypeScript + Tailwind) sits on top of a small JSON API
served by the engine. Every number is computed in Python; the UI only displays it.

```bash
# One-time build, then one command serves the API and the UI at http://127.0.0.1:8000
(cd web && npm install && npm run build)
python3 -m finance serve data/transactions.json

# Or, while working on the UI (hot reload on :5173, /api proxied to :8000)
python3 -m finance serve data/transactions.json      # terminal 1
(cd web && npm run dev)                               # terminal 2
```

API (`finance/server.py`, standard library only). Every endpoint accepts `start`, `end`,
`account` (repeatable), `category` (repeatable), `merchant` and `drop_duplicates`.

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | accounts, categories, first/last date |
| `GET /api/summary?top=N` | the monthly summary (same as `finance summary`) |
| `GET /api/rolling?window=N` | rolling N-day average spending |
| `GET /api/transactions?kind=&limit=&offset=` | paginated transactions, newest first |

Bad input returns HTTP 400 with `{"error": ...}`.

**Design choices.** These follow *Refactoring UI*:

- **Hierarchy comes from weight and color, not just size.** Labels are small and muted;
  values are bold and dark. There is one big number per page (net cash flow).
- **Cards are separated by soft shadows on a warm-tinted page,** with no borders. The one
  accent border marks the "Not double counted" callout.
- **Warm grays and a small set of colors,** defined once as CSS variables (`src/index.css`).
  Dark mode uses its own values for each color rather than an automatic inversion.
- **Color never carries meaning alone.** Status badges always include an icon and a label,
  and negative amounts use a minus sign as well as color.
- **Short labels.** "Saved 4.6% of income" instead of "Savings rate: 4.6%".
- **Every panel has an empty state,** and while new data loads the old data stays on screen,
  slightly faded, so the layout doesn't jump.

**Charts** are hand-drawn SVG:

- The blue/orange pair is checked for colorblind safety in both themes.
- Bars are thin with rounded tops, gridlines are faint, and there is only ever one y-axis.
  Net cash flow goes in the tooltip and the table rather than on a second axis.
- Every chart has a hover tooltip, and the monthly chart also has a table view so no value
  is only available on hover.

**Interactions:**

- Click a month to focus the dashboard on it; click again to clear.
- Click a category or merchant to filter by it.
- Filters are saved in the URL, so any view can be bookmarked or shared.

## CLI

Every command prints JSON. They all accept the same filters: `--start`, `--end` (inclusive,
`YYYY-MM-DD`), `--account` (repeatable), `--category` (repeatable, case-insensitive),
`--merchant` (substring), plus `--strict` and `-o FILE`.

| Command | Purpose |
|---|---|
| `summary` | Full monthly report (`--top N`, `--drop-probable-duplicates`) |
| `validate` | Data-quality report. Exits with code 1 if any record was rejected |
| `transactions` | List filtered transactions (`--limit`) |
| `cash-flow` | Monthly income / expenses / net cash flow |
| `categories` | Net spending by category |
| `top-merchants` | Top N merchants by net spending (`-n`) |
| `duplicates` | Probable duplicates (`--window DAYS`) |
| `subscriptions` | Recurring charges |
| `rolling` | Rolling N-day spending average (`--window`, default 30) |

```bash
python3 -m finance top-merchants data/transactions.json -n 5 --start 2026-01-01 --end 2026-03-31
python3 -m finance cash-flow data/transactions.json --account credit_1
```

## Layout

```
finance/
  models.py         Transaction/Account types, merchant normalization, sign convention
  validation.py     JSON loading (Decimal amounts), per-record validation, exact-duplicate removal
  transfers.py      internal-transfer pairing (explicit transfer_id + heuristic matching)
  ledger.py         pipeline: validate -> pair transfers -> classify -> infer categories
  filters.py        date / account / category / merchant filters
  analytics.py      cash flow, category & merchant totals, top N, rolling average
  duplicates.py     probable-duplicate detection
  subscriptions.py  recurring-charge detection
  report.py         monthly summary JSON
  server.py         JSON API + static hosting for the web UI
  cli.py
scripts/generate_data.py   deterministic data generator with traps + ground truth
tests/                     unit tests + end-to-end check against ground truth
web/                       React dashboard (see Web UI)
```

## Definitions and design decisions

**Sign convention.** Each amount is signed from its account's point of view: money leaving the
account is negative. A card purchase is negative (more debt) and a card payment is positive.
`purchase` and `fee` must be ≤ 0, and `income` and `refund` must be ≥ 0. A record that breaks
these rules is rejected, not silently flipped.

**Money is `Decimal`, never `float`.** The JSON is parsed with `parse_float=Decimal`. Amounts with
more than 2 decimal places, NaN/Infinity, booleans, and numeric strings are rejected. The output
JSON writes values as numbers rounded to the cent.

**Cash-flow definitions.**

| | |
|---|---|
| income | sum of `income` transactions |
| gross_spend | purchases + fees |
| refunds | refunds (reduce spending; never counted as income) |
| expenses | gross_spend − refunds |
| net_cash_flow | income − expenses |

### Internal transfers (the double-counting problem)

When you pay a credit card from checking, the real expenses are the card purchases you already
made. The payment just moves money between your own accounts. If you add up every outflow, each
card purchase is counted twice: once on the card and again when checking pays the bill.

The engine pairs the two legs of each transfer and leaves both out of income and expenses:

1. **Explicit pairing:** two legs with the same `transfer_id`, in different accounts, that sum to zero.
2. **Heuristic pairing:** for data where the bank feed lost the link. An outflow and an inflow are
   paired if they have the same absolute amount, are in different accounts, are within 3 days of
   each other, and **both** look like a transfer (type `transfer`/`payment`, a keyword such as
   "autopay" or "payment thank you", or a transfer category). Because both legs must look like a
   transfer, a $45 Chipotle charge can't pair with a $45 card payment. If `counterparty_account_id`
   is present, it narrows the match.

Pairing runs over the **whole ledger before any filter is applied**. If you filter to `checking_1`,
the payment leg still counts as a transfer, even though its other leg is filtered out.

A `transfer` or `payment` with no matching leg (for example, a Zelle payment to a roommate) is
classified as `unmatched_transfer`. It is left out of totals but listed in `data_quality` for
review, because the engine can't tell whether it's internal.

### Other edge cases

- **Refunds** count against spending in the merchant's category. A refund with no category gets
  the category of that merchant's purchases.
- **Missing categories** (`null`, `""`, or no key at all) are filled with the merchant's most
  common category. If the merchant has none, the transaction is labeled `Uncategorized`.
  `category_inferred` marks every filled value.
- **Duplicates:**
  - *Exact* (same id, identical record): dropped automatically.
  - *Same id, different content*: rejected; the first record is kept.
  - *Probable* (different ids, but same account, merchant, amount and day): flagged.
    Use `--drop-probable-duplicates` to also remove them from totals.
- **Merchant normalization** groups `UBER *TRIP` with `Uber`, `AMAZON.COM*MK1A2` with `Amazon`,
  and `STARBUCKS #4471` with `Starbucks`.
- **Subscriptions** need at least 3 charges on a recognized schedule (weekly, biweekly, monthly,
  quarterly or annual). Amounts are compared between consecutive charges, so a one-time price
  increase (Netflix $15.49 → $17.99) is still detected while variable bills like electricity are
  not. Each result includes next expected date, annualized cost, price changes, and whether it's
  still active.
- **Rolling average:** the trailing 30-day net spend divided by 30 for each calendar day. Days with
  no spending count as zero. Spending before `--start` still counts toward the early windows, and
  `complete_window` is false until 30 days of history exist.

## Generated data

`scripts/generate_data.py --seed N` produces 12 months of data for a household with 4 accounts. It
includes these traps:

- 3 credit-card payments that are unlinked and mislabeled
- checking ↔ savings transfers
- 3 unmatched Zelle transfers
- 60 refunds
- missing categories in all three forms
- 15 exact duplicates, 3 id conflicts, and 20 double swipes
- 12 invalid records
- subscriptions, including a price increase, a cancellation, and a weekly cadence with skipped weeks

The generator keeps its own records of what really happened, separate from the engine. It writes
that to `ground_truth.json`, and `tests/test_end_to_end.py` checks the engine against it to the cent.
