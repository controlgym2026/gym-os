"""Members export — pure formatting (no DB, no FastAPI), unit-tested directly.

members_export.py fetches rows from the members_export() SQL function page by
page and hands each page to the writers here:

  * CsvChunkWriter  — UTF-8 with BOM, comma-separated, csv-module quoting;
                      yields encoded bytes per page so the response streams.
  * XlsxExportWriter — XlsxWriter in constant_memory mode (one row in memory
                      at a time), written to a temp file, then streamed.

Rules applied in both formats (see the module tests):
  * Formula injection: a text cell starting with = + - @ (or tab/CR, per
    OWASP) is neutralised — CSV gets a leading single quote; XLSX writes an
    explicit string cell with Excel's quote-prefix flag, so the value is
    never evaluated and displays unchanged.
  * Phones stay text: XLSX string cell with the '@' (Text) number format;
    CSV wraps a phone that is only digits/+/space/hyphen as ="<phone>" so
    Excel neither drops a leading zero nor shows 9.1E+11. Any other phone
    value falls back to the ordinary injection-safe text path.
  * Dates DD-MM-YYYY (real date cells in XLSX), datetimes converted to IST,
    amounts as plain numbers with two decimals.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Column order is part of the spec — tests pin it.
COLUMNS: list[str] = [
    "Member ID",
    "Name",
    "Phone",
    "Email",
    "Gender",
    "Batch",
    "Date of joining",
    "Plan name",
    "Subscription start date",
    "Subscription end date",
    "Days left",
    "Status",
    "Due amount",
    "Last payment date",
    "Last payment amount",
    "Last visit date",
    "Biometric enrolled",
]

# Width (characters) per column for the XLSX sheet.
COLUMN_WIDTHS: list[int] = [10, 26, 16, 28, 9, 10, 14, 22, 14, 14, 9, 11, 12, 14, 14, 14, 10]

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_SAFE_PHONE = re.compile(r"^\+?[0-9][0-9 \-]*$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


# --- small pure helpers -----------------------------------------------------


def is_formula_like(value: str) -> bool:
    return bool(value) and value.startswith(_FORMULA_PREFIXES)


def neutralise_csv_text(value: str | None) -> str:
    """Empty for None; a leading ' for anything a spreadsheet would treat as
    a formula; otherwise unchanged."""
    if value is None:
        return ""
    return "'" + value if is_formula_like(value) else value


def csv_phone(value: str | None) -> str:
    if not value:
        return ""
    if _SAFE_PHONE.match(value):
        return f'="{value}"'
    return neutralise_csv_text(value)


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_ist_date(value) -> date | None:
    """A timestamptz (ISO string from PostgREST, or datetime) -> the IST
    calendar date. Naive values are assumed UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(IST).date()


def format_date(d: date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def to_amount(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_amount(value) -> str:
    amount = to_amount(value)
    return "" if amount is None else f"{amount:.2f}"


def slugify(name: str | None) -> str:
    slug = _SLUG_STRIP.sub("-", (name or "").lower()).strip("-")
    return slug[:60].strip("-") or "gym"


def export_filename(gym_name: str | None, fmt: str, today: date) -> str:
    return f"members_{slugify(gym_name)}_{today.isoformat()}.{fmt}"


# --- row normalisation --------------------------------------------------------


def normalise_row(raw: dict) -> list:
    """One members_export() row -> a list of typed values in COLUMNS order
    (str | int | date | Decimal | None). Gender and Batch are always None:
    the schema has no such fields (see the export report)."""
    return [
        raw.get("member_number"),
        raw.get("name") or "",
        raw.get("phone") or "",
        raw.get("email") or "",
        None,  # Gender — not stored in Gym OS
        None,  # Batch — not stored in Gym OS
        parse_date(raw.get("joined_on")),
        raw.get("plan_name") or "",
        parse_date(raw.get("start_date")),
        parse_date(raw.get("end_date")),
        raw.get("days_left"),
        raw.get("status") or "",
        to_amount(raw.get("due_amount")),  # null (blank) when the member has no plan
        parse_ist_date(raw.get("last_payment_at")),
        to_amount(raw.get("last_payment_amount")),
        parse_ist_date(raw.get("last_visit_at")),
        "Yes" if raw.get("biometric_enrolled") else "No",
    ]


_PHONE_COL = COLUMNS.index("Phone")


# --- CSV ----------------------------------------------------------------------


class CsvChunkWriter:
    """Call header() once, then rows(page) per page; each returns bytes."""

    BOM = "﻿"

    def __init__(self):
        self._buf = io.StringIO()
        self._writer = csv.writer(self._buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    def _drain(self) -> bytes:
        data = self._buf.getvalue().encode("utf-8")
        self._buf.seek(0)
        self._buf.truncate(0)
        return data

    def header(self) -> bytes:
        self._buf.write(self.BOM)
        self._writer.writerow(COLUMNS)
        return self._drain()

    @staticmethod
    def _cell(index: int, value) -> str:
        if value is None:
            return ""
        if index == _PHONE_COL:
            return csv_phone(value)
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, date):
            return format_date(value)
        if isinstance(value, int):
            return str(value)
        return neutralise_csv_text(str(value))

    def rows(self, raw_rows: list[dict]) -> bytes:
        for raw in raw_rows:
            values = normalise_row(raw)
            self._writer.writerow([self._cell(i, v) for i, v in enumerate(values)])
        return self._drain()


# --- XLSX ---------------------------------------------------------------------


class XlsxExportWriter:
    """Streaming (constant_memory) XLSX writer. Usage:
        w = XlsxExportWriter(path); w.add_rows(page) ...; w.close(info)"""

    def __init__(self, path: str):
        import xlsxwriter  # imported lazily so CSV-only paths don't need it

        self._wb = xlsxwriter.Workbook(
            path,
            {"constant_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
        )
        self._ws = self._wb.add_worksheet("Members")
        self._header_fmt = self._wb.add_format({"bold": True, "bg_color": "#F3F4F6", "bottom": 1})
        self._date_fmt = self._wb.add_format({"num_format": "dd-mm-yyyy"})
        self._amount_fmt = self._wb.add_format({"num_format": "0.00"})
        self._text_fmt = self._wb.add_format({"num_format": "@"})
        self._quoted_fmt = self._wb.add_format({"num_format": "@", "quote_prefix": True})
        self._wrap_fmt = self._wb.add_format({"text_wrap": True, "valign": "top"})
        self._label_fmt = self._wb.add_format({"bold": True, "valign": "top"})

        for i, width in enumerate(COLUMN_WIDTHS):
            fmt = self._text_fmt if i == _PHONE_COL else None
            self._ws.set_column(i, i, width, fmt)
        self._ws.freeze_panes(1, 0)
        for i, title in enumerate(COLUMNS):
            self._ws.write_string(0, i, title, self._header_fmt)
        self._row = 1

    def _write_text(self, col: int, value: str) -> None:
        if value == "":
            return
        fmt = self._quoted_fmt if is_formula_like(value) else (self._text_fmt if col == _PHONE_COL else None)
        if fmt is None:
            self._ws.write_string(self._row, col, value)
        else:
            self._ws.write_string(self._row, col, value, fmt)

    def add_rows(self, raw_rows: list[dict]) -> None:
        for raw in raw_rows:
            for col, value in enumerate(normalise_row(raw)):
                if value is None:
                    continue
                if isinstance(value, Decimal):
                    self._ws.write_number(self._row, col, float(value), self._amount_fmt)
                elif isinstance(value, date):
                    self._ws.write_datetime(self._row, col, datetime(value.year, value.month, value.day), self._date_fmt)
                elif isinstance(value, bool):
                    self._write_text(col, "Yes" if value else "No")
                elif isinstance(value, int):
                    self._ws.write_number(self._row, col, value)
                else:
                    self._write_text(col, str(value))
            self._row += 1

    @property
    def row_count(self) -> int:
        return self._row - 1

    def close(self, info: list[tuple[str, str]]) -> None:
        """Finish the data sheet (autofilter over header + rows) and add the
        "Export info" sheet, then write the file."""
        self._ws.autofilter(0, 0, max(self._row - 1, 0), len(COLUMNS) - 1)
        meta = self._wb.add_worksheet("Export info")
        meta.set_column(0, 0, 18)
        meta.set_column(1, 1, 70)
        for r, (label, value) in enumerate(info):
            meta.write_string(r, 0, label, self._label_fmt)
            # Gym name / filter text are user-controlled — same injection rule.
            meta.write_string(r, 1, value, self._quoted_fmt if is_formula_like(value) else self._wrap_fmt)
        self._wb.close()
