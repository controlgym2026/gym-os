"""Minimal in-memory stand-in for the subset of the supabase-py/postgrest
chainable query builder this codebase actually uses (select/insert/update,
eq/is_/gte/lte/order/limit, .execute() -> .data). Not a general emulator —
just enough surface to drive the real ingestion functions (biometric.py,
attendance.py, subscriptions.py) against in-memory data for tests, instead
of mocking each call individually.
"""

import uuid


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, rows: list[dict], mode: str, payload=None):
        self._rows = rows  # the table's live row list (insert/update mutate it)
        self._filtered = list(rows)
        self._mode = mode
        self._payload = payload
        # PostgREST's count=exact reports the total matching rows *before*
        # range/limit is applied (it comes back in Content-Range), so capture
        # it at the moment the window is narrowed rather than at execute().
        self._total = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def is_(self, col, val):
        target = None if val == "null" else val
        self._filtered = [r for r in self._filtered if r.get(col) == target]
        return self

    def in_(self, col, values):
        values = set(values)
        self._filtered = [r for r in self._filtered if r.get(col) in values]
        return self

    def gte(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) is not None and r[col] >= val]
        return self

    def lte(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) is not None and r[col] <= val]
        return self

    def order(self, col, desc=False):
        self._filtered.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def or_(self, expr: str):
        """Supports just the one shape this codebase builds: comma-separated
        "col.ilike.%needle%" alternatives (members list search)."""
        matched = []
        for row in self._filtered:
            for clause in expr.split(","):
                col, op, pattern = clause.split(".", 2)
                if op != "ilike":
                    raise NotImplementedError(f"or_ operator '{op}'")
                value = row.get(col)
                if value is not None and pattern.strip("%").lower() in str(value).lower():
                    matched.append(row)
                    break
        self._filtered = matched
        return self

    def range(self, start, end):
        self._total = len(self._filtered)
        self._filtered = self._filtered[start : end + 1]
        return self

    def limit(self, n):
        self._total = len(self._filtered)
        self._filtered = self._filtered[:n]
        return self

    def execute(self):
        if self._mode == "select":
            total = self._total if self._total is not None else len(self._filtered)
            return _Result(list(self._filtered), count=total)
        if self._mode == "insert":
            # Real postgrest-py's .insert() takes either one dict or a list
            # of dicts (a batch insert in one request) — support both here.
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            new_rows = []
            for p in payloads:
                row = dict(p)
                row.setdefault("id", str(uuid.uuid4()))
                self._rows.append(row)
                new_rows.append(row)
            return _Result(new_rows)
        if self._mode == "update":
            for r in self._filtered:
                r.update(self._payload)
            return _Result(list(self._filtered))
        raise NotImplementedError(self._mode)


class _Table:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def select(self, *_a, **_k):
        return _Query(self._rows, "select")

    def insert(self, payload: dict):
        return _Query(self._rows, "insert", payload)

    def update(self, payload: dict):
        return _Query(self._rows, "update", payload)


class FakeClient:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> _Table:
        return _Table(self.tables.setdefault(name, []))

    def seed(self, name: str, rows: list[dict]) -> None:
        self.tables.setdefault(name, []).extend(rows)
