"""Read-only JSON API over a loaded ledger, plus static hosting for the built web UI.

Standard library only. The ledger is built once at startup; every request is a pure
function of (ledger, query string), so the handler is safe to run threaded.

  GET /api/meta          accounts, categories, date bounds
  GET /api/summary       monthly summary (same as `finance summary`)
  GET /api/rolling       rolling N-day spending average
  GET /api/transactions  filtered, paginated transactions (newest first)

Filters for every endpoint: start, end, account (repeatable), category (repeatable),
merchant, drop_duplicates (true/false).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .analytics import rolling_spending_average
from .duplicates import drop_duplicates, find_probable_duplicates
from .filters import TransactionFilter
from .ledger import Ledger
from .models import SPENDING_KINDS, Kind
from .report import build_summary, json_default

MAX_PAGE_SIZE = 500
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class BadRequest(ValueError):
    pass


class NotFound(LookupError):
    pass


class FinanceAPI:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.duplicate_groups = find_probable_duplicates(ledger.transactions)
        self.duplicate_extra_ids = {tx.id for g in self.duplicate_groups for tx in g.extras}
        self._routes = {
            "/api/meta": self.meta,
            "/api/summary": self.summary,
            "/api/rolling": self.rolling,
            "/api/transactions": self.transactions,
        }

    def handle(self, path: str, query: dict[str, list[str]]):
        route = self._routes.get(path.rstrip("/"))
        if route is None:
            raise NotFound(path)
        return route(query)

    def meta(self, query):
        txs = self.ledger.transactions
        return {
            "accounts": [
                {"id": a.id, "type": a.type, "name": a.name or a.id} for a in self.ledger.accounts.values()
            ],
            "categories": sorted({t.effective_category for t in txs if t.kind in SPENDING_KINDS}),
            "first_date": txs[0].date if txs else None,
            "last_date": self.ledger.as_of,
        }

    def summary(self, query):
        return build_summary(
            self.ledger,
            _filter(query),
            top_n=_int(query, "top", 5, minimum=0, maximum=50),
            drop_probable_duplicates=_bool(query, "drop_duplicates", False),
        )

    def rolling(self, query):
        flt = _filter(query)
        history = flt.without_dates().apply(self._working(query))
        window = _int(query, "window", 30, minimum=1, maximum=365)
        points = rolling_spending_average(history, start=flt.start, end=flt.end, window_days=window)
        return {"window_days": window, "points": [p.to_dict() for p in points]}

    def transactions(self, query):
        txs = _filter(query).apply(self._working(query))
        kinds = _kinds(query)
        if kinds:
            txs = [t for t in txs if t.kind in kinds]
        txs.sort(key=lambda t: (t.date, t.source_index), reverse=True)
        limit = _int(query, "limit", 50, minimum=1, maximum=MAX_PAGE_SIZE)
        offset = _int(query, "offset", 0, minimum=0)
        page = txs[offset : offset + limit]
        return {
            "total": len(txs),
            "offset": offset,
            "limit": limit,
            "items": [{**t.to_dict(), "probable_duplicate": t.id in self.duplicate_extra_ids} for t in page],
        }

    def _working(self, query):
        if _bool(query, "drop_duplicates", False):
            return drop_duplicates(self.ledger.transactions, self.duplicate_groups)
        return self.ledger.transactions


def _filter(query) -> TransactionFilter:
    try:
        return TransactionFilter(
            start=_date(query, "start"),
            end=_date(query, "end"),
            accounts=frozenset(query.get("account", ())),
            categories=frozenset(query.get("category", ())),
            merchant=_one(query, "merchant") or None,
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def _one(query, name) -> str | None:
    values = query.get(name)
    return values[-1].strip() if values else None


def _date(query, name) -> date | None:
    value = _one(query, name)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%d-%m").date()
    except ValueError as exc:
        raise BadRequest(f"{name} must be YYYY-MM-DD") from exc


def _int(query, name, default, *, minimum, maximum=None) -> int:
    value = _one(query, name)
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise BadRequest(f"{name} must be an integer") from exc
    if number < minimum or (maximum is not None and number > maximum):
        raise BadRequest(f"{name} must be between {minimum} and {maximum if maximum is not None else 'inf'}")
    return number


def _bool(query, name, default) -> bool:
    value = (_one(query, name) or "").lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise BadRequest(f"{name} must be true or false")


def _kinds(query) -> frozenset[Kind]:
    try:
        return frozenset(Kind(k) for k in query.get("kind", ()))
    except ValueError as exc:
        raise BadRequest(f"kind must be one of {', '.join(k.value for k in Kind)}") from exc


class _Handler(SimpleHTTPRequestHandler):
    api: FinanceAPI  # injected by serve()

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            self._api(url.path, parse_qs(url.query))
        elif not Path(self.directory).is_dir():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "UI not built: run `npm run build` in web/"})
        else:
            # Single-page app: unknown paths fall back to index.html.
            if not (Path(self.directory) / url.path.lstrip("/")).exists():
                self.path = "/index.html"
            super().do_GET()

    def _api(self, path, query):
        try:
            self._send_json(HTTPStatus.OK, self.api.handle(path, query))
        except BadRequest as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except NotFound:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"no such endpoint: {path}"})

    def _send_json(self, status, payload):
        body = json.dumps(payload, default=json_default).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # quieter than the default per-request stderr line
        if not self.path.startswith("/assets/"):
            super().log_message(format, *args)


def make_server(ledger: Ledger, host: str, port: int, static_dir: Path) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"api": FinanceAPI(ledger)})
    return ThreadingHTTPServer((host, port), partial(handler, directory=str(static_dir)))


def serve(ledger: Ledger, host: str, port: int, static_dir: Path) -> None:
    server = make_server(ledger, host, port, static_dir)
    print(f"Serving on http://{host}:{server.server_port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
