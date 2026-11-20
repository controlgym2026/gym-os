"""Members export (GET /members/export) — formatting rules + route behaviour.

The SQL side (members_export() returning the same rows as GET /members for
the same filters) is checked against a real Postgres by
scripts/export_sql_parity/ and live by scripts/live_regression_export.py;
here the RPC page fetch is stubbed so the route and the writers can be tested
without a database.
"""

import csv
import io
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import auth
import export_format as ef
import members_export
from auth import get_current_staff
from fake_client import FakeClient
from main import app

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
PLAN = "33333333-3333-3333-3333-333333333333"
OWNER = {"id": "staff-owner", "tenant_id": TENANT, "role": "owner"}

INJECTION_NAME = '=HYPERLINK("http://evil.example","click")'


def _row(**over):
    row = {
        "member_number": 7,
        "name": "Ravi Kumar",
        "phone": "09876543210",
        "email": "ravi@example.com",
        "joined_on": "2026-01-05",
        "plan_name": "Monthly",
        "start_date": "2026-11-01",
        "end_date": "2026-12-01",
        "days_left": 13,
        "status": "Active",
        "due_amount": 500,
        "last_payment_at": "2026-11-01T20:00:00+00:00",  # 02-11-2026 01:30 IST
        "last_payment_amount": 999.5,
        "last_visit_at": "2026-11-17T18:45:00+00:00",  # 18-11-2026 00:15 IST
        "biometric_enrolled": True,
        "total_count": 1,
    }
    row.update(over)
    return row


# --- pure formatting ------------------------------------------------------------


class TestFormulaInjection:
    @pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tx", "\rx", INJECTION_NAME])
    def test_csv_text_is_prefixed_with_a_quote(self, value):
        assert ef.neutralise_csv_text(value) == "'" + value

    @pytest.mark.parametrize("value", ["Ravi", "रवि शर्मा", "a=b", "", "O'Brien"])
    def test_ordinary_text_is_unchanged(self, value):
        assert ef.neutralise_csv_text(value) == value

    def test_none_is_empty(self):
        assert ef.neutralise_csv_text(None) == ""


class TestPhone:
    @pytest.mark.parametrize("phone", ["09876543210", "+919876543210", "98765 43210", "0123-456789"])
    def test_safe_phone_is_wrapped_as_a_text_formula(self, phone):
        assert ef.csv_phone(phone) == f'="{phone}"'

    def test_unsafe_phone_falls_back_to_neutralised_text(self):
        assert ef.csv_phone('=HYPERLINK("x")') == "'=HYPERLINK(\"x\")"
        assert ef.csv_phone('1"),EVIL(') == '1"),EVIL('  # no quote breakout: not wrapped

    def test_blank_phone(self):
        assert ef.csv_phone(None) == "" and ef.csv_phone("") == ""


class TestDatesAndAmounts:
    def test_date_format_is_dd_mm_yyyy(self):
        assert ef.format_date(date(2026, 3, 9)) == "09-03-2026"

    def test_timestamps_convert_to_ist_date(self):
        # 20:00 UTC on 1 Nov is 01:30 on 2 Nov in IST
        assert ef.parse_ist_date("2026-11-01T20:00:00+00:00") == date(2026, 11, 2)
        assert ef.parse_ist_date("2026-11-01T20:00:00.123Z") == date(2026, 11, 2)
        assert ef.parse_ist_date(None) is None

    def test_amounts_have_two_decimals_and_no_symbol(self):
        assert ef.format_amount(500) == "500.00"
        assert ef.format_amount(999.5) == "999.50"
        assert ef.format_amount("1250.555") == "1250.56"
        assert ef.format_amount(None) == ""


class TestFilename:
    def test_slug_and_date(self):
        assert ef.export_filename("Control Gym & Fitness!", "csv", date(2026, 11, 18)) == "members_control-gym-fitness_2026-11-18.csv"

    def test_non_latin_name_falls_back(self):
        assert ef.export_filename("जिम", "xlsx", date(2026, 1, 2)) == "members_gym_2026-01-02.xlsx"


def test_column_order_is_pinned():
    assert ef.COLUMNS == [
        "Member ID", "Name", "Phone", "Email", "Gender", "Batch", "Date of joining", "Plan name",
        "Subscription start date", "Subscription end date", "Days left", "Status", "Due amount",
        "Last payment date", "Last payment amount", "Last visit date", "Biometric enrolled",
    ]
    assert len(ef.COLUMN_WIDTHS) == len(ef.COLUMNS)


def test_no_sensitive_fields_in_columns():
    lowered = " ".join(ef.COLUMNS).lower()
    for banned in ("pin", "biometric_ref", "photo", "uuid", "tenant"):
        assert banned not in lowered


class TestCsvWriter:
    def _csv(self, rows):
        w = ef.CsvChunkWriter()
        return w.header() + w.rows(rows)

    def test_bom_and_header(self):
        data = self._csv([])
        assert data.startswith(b"\xef\xbb\xbf")
        text = data.decode("utf-8-sig")
        assert list(csv.reader(io.StringIO(text))) == [ef.COLUMNS]

    def test_row_values(self):
        text = self._csv([_row(name=INJECTION_NAME, email="+x@y.com")]).decode("utf-8-sig")
        header, row = list(csv.reader(io.StringIO(text)))
        rec = dict(zip(header, row))
        assert rec["Member ID"] == "7"
        assert rec["Name"] == "'" + INJECTION_NAME
        assert rec["Email"] == "'+x@y.com"
        assert rec["Phone"] == '="09876543210"'
        assert rec["Gender"] == "" and rec["Batch"] == ""
        assert rec["Date of joining"] == "05-01-2026"
        assert rec["Subscription end date"] == "01-12-2026"
        assert rec["Days left"] == "13"
        assert rec["Due amount"] == "500.00"
        assert rec["Last payment date"] == "02-11-2026"
        assert rec["Last payment amount"] == "999.50"
        assert rec["Last visit date"] == "18-11-2026"
        assert rec["Biometric enrolled"] == "Yes"

    def test_quoting_of_commas_quotes_and_newlines(self):
        text = self._csv([_row(name='Ali, "Raja"\nKhan')]).decode("utf-8-sig")
        _, row = list(csv.reader(io.StringIO(text)))
        assert row[1] == 'Ali, "Raja"\nKhan'

    def test_no_plan_row(self):
        text = self._csv([_row(plan_name=None, start_date=None, end_date=None, days_left=None, status="No plan",
                               due_amount=None, last_payment_at=None, last_payment_amount=None, biometric_enrolled=False)]).decode("utf-8-sig")
        _, row = list(csv.reader(io.StringIO(text)))
        rec = dict(zip(ef.COLUMNS, row))
        assert rec["Status"] == "No plan" and rec["Due amount"] == "" and rec["Days left"] == ""
        assert rec["Biometric enrolled"] == "No"

    def test_non_english_round_trips(self):
        text = self._csv([_row(name="रवि शर्मा")]).decode("utf-8-sig")
        assert "रवि शर्मा" in text


class TestXlsxWriter:
    def _book(self, tmp_path, rows, info=None):
        path = tmp_path / "out.xlsx"
        w = ef.XlsxExportWriter(str(path))
        w.add_rows(rows)
        w.close(info or [("Gym", "QA"), ("Rows", str(w.row_count))])
        return openpyxl.load_workbook(path)

    def test_structure(self, tmp_path):
        wb = self._book(tmp_path, [_row(), _row(member_number=8)])
        assert wb.sheetnames == ["Members", "Export info"]
        ws = wb["Members"]
        assert [c.value for c in ws[1]] == ef.COLUMNS
        assert all(c.font.bold for c in ws[1])
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == "A1:Q3"
        assert ws.column_dimensions["B"].width > 20

    def test_cell_types(self, tmp_path):
        ws = self._book(tmp_path, [_row(name=INJECTION_NAME)])["Members"]
        rec = {h: c for h, c in zip(ef.COLUMNS, ws[2])}
        # phone: string cell, Text format, leading zero kept
        assert rec["Phone"].data_type == "s" and rec["Phone"].value == "09876543210"
        assert rec["Phone"].number_format == "@"
        # injection: stored as a plain string (never a formula), quote-prefixed
        assert rec["Name"].data_type == "s" and rec["Name"].value == INJECTION_NAME
        assert rec["Name"].quotePrefix
        # real dates, dd-mm-yyyy
        assert isinstance(rec["Subscription end date"].value, datetime)
        assert rec["Subscription end date"].value.date() == date(2026, 12, 1)
        assert rec["Subscription end date"].number_format == "dd-mm-yyyy"
        assert rec["Last payment date"].value.date() == date(2026, 11, 2)
        # amounts are numbers with 2dp format
        assert rec["Due amount"].value == 500 and rec["Due amount"].number_format == "0.00"
        assert rec["Last payment amount"].value == 999.5
        assert rec["Member ID"].value == 7 and rec["Days left"].value == 13
        assert rec["Gender"].value is None and rec["Batch"].value is None

    def test_empty_export_is_valid_with_headers(self, tmp_path):
        wb = self._book(tmp_path, [])
        ws = wb["Members"]
        assert [c.value for c in ws[1]] == ef.COLUMNS
        assert ws.max_row == 1

    def test_info_sheet_neutralises_injection(self, tmp_path):
        wb = self._book(tmp_path, [], info=[("Gym", "=EVIL()")])
        cell = wb["Export info"]["B1"]
        assert cell.data_type == "s" and cell.value == "=EVIL()" and cell.quotePrefix


def test_search_pattern_matches_list_semantics():
    assert members_export.search_pattern(None) is None
    assert members_export.search_pattern("") is None
    assert members_export.search_pattern("ra,(vi)") == "%ravi%"
    assert members_export.search_pattern("Raj*") == "%Raj%%"


def test_describe_filters():
    assert members_export.describe_filters(None, None, None, None) == "None (all members)"
    assert members_export.describe_filters("ravi", "expired", "has_photo", "Monthly") == (
        'Search "ravi"; Status: Expired; Plan: Monthly; Photo: Has photo'
    )


# --- route ---------------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    """TestClient with a FakeClient behind get_admin_client and the RPC page
    fetch stubbed to slice an in-memory row list (PAGE_SIZE shrunk to 2 so
    multi-page streaming is exercised)."""
    fake = FakeClient()
    fake.seed("tenant", [{"id": TENANT, "name": "QA Gym"}, {"id": OTHER_TENANT, "name": "Other"}])
    fake.seed("membership_plan", [{"id": PLAN, "tenant_id": TENANT, "name": "Monthly"}])
    state = {"rows": [], "calls": [], "staff": dict(OWNER)}

    def fake_fetch(tenant_id, today, params, offset):
        state["calls"].append({"tenant_id": tenant_id, "params": params, "offset": offset})
        rows = [dict(r, total_count=len(state["rows"])) for r in state["rows"]]
        return rows[offset : offset + members_export.PAGE_SIZE]

    monkeypatch.setattr(members_export, "get_admin_client", lambda: fake)
    monkeypatch.setattr(members_export, "_fetch_page", fake_fetch)
    monkeypatch.setattr(members_export, "PAGE_SIZE", 2)
    app.dependency_overrides[get_current_staff] = lambda: state["staff"]
    yield TestClient(app), fake, state
    app.dependency_overrides.clear()


def test_csv_export_streams_all_pages(env):
    client, fake, state = env
    state["rows"] = [_row(member_number=i, name=f"M{i}") for i in range(1, 6)]
    r = client.get("/members/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["x-export-row-count"] == "5"
    assert r.headers["cache-control"] == "no-store"
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="members_qa-gym_') and cd.endswith('.csv"')
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ef.COLUMNS and [x[1] for x in rows[1:]] == ["M1", "M2", "M3", "M4", "M5"]
    assert [c["offset"] for c in state["calls"]] == [0, 2, 4]


def test_xlsx_export(env):
    client, fake, state = env
    state["rows"] = [_row(member_number=i) for i in range(1, 4)]
    r = client.get(f"/members/export?format=xlsx&filter=expired&plan_id={PLAN}&q=ra")
    assert r.status_code == 200
    assert r.headers["content-disposition"].endswith('.xlsx"')
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb["Members"].max_row == 4
    info = {row[0].value: row[1].value for row in wb["Export info"].iter_rows()}
    assert info["Gym"] == "QA Gym" and info["Rows"] == "3"
    assert info["Filters applied"] == 'Search "ra"; Status: Expired; Plan: Monthly'
    assert info["Exported at"].endswith("IST")


def test_empty_result_still_returns_a_file(env):
    client, _, state = env
    r = client.get("/members/export?format=csv&filter=due")
    assert r.status_code == 200 and r.headers["x-export-row-count"] == "0"
    assert list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")))) == [ef.COLUMNS]
    r = client.get("/members/export?format=xlsx&filter=due")
    assert openpyxl.load_workbook(io.BytesIO(r.content))["Members"].max_row == 1


def test_filters_are_passed_through_like_the_list(env):
    client, _, state = env
    client.get(f"/members/export?format=csv&q=ra,vi&filter=expiring&photo=no_photo&plan_id={PLAN}")
    assert state["calls"][0] == {
        "tenant_id": TENANT,
        "params": {"search": "%ravi%", "filter": "expiring", "photo": "no_photo", "plan_id": PLAN},
        "offset": 0,
    }


def test_tenant_comes_from_staff_not_from_the_request(env):
    client, _, state = env
    client.get(f"/members/export?format=csv&tenant_id={OTHER_TENANT}")
    assert state["calls"][0]["tenant_id"] == TENANT


@pytest.mark.parametrize("role", ["trainer", "front_desk"])
def test_non_export_roles_get_403(env, role):
    client, fake, state = env
    state["staff"]["role"] = role
    r = client.get("/members/export?format=csv")
    assert r.status_code == 403
    assert state["calls"] == [] and fake.tables.get("data_export_log", []) == []


@pytest.mark.parametrize("role", ["owner", "manager"])
def test_owner_and_manager_allowed(env, role):
    client, _, state = env
    state["staff"]["role"] = role
    assert client.get("/members/export?format=csv").status_code == 200


@pytest.mark.parametrize("query", ["format=pdf", "filter=bogus", "photo=maybe", "plan_id=not-a-uuid"])
def test_bad_params_are_400(env, query):
    client, _, _ = env
    assert client.get(f"/members/export?{query}").status_code == 400


def test_audit_row_written(env):
    client, fake, state = env
    state["rows"] = [_row(), _row()]
    client.get(f"/members/export?format=xlsx&filter=active&plan_id={PLAN}")
    (log,) = fake.tables["data_export_log"]
    assert log["tenant_id"] == TENANT and log["staff_id"] == OWNER["id"]
    assert log["format"] == "xlsx" and log["row_count"] == 2
    assert log["filters"] == {"filter": "active", "plan_id": PLAN}


def test_rate_limit(env):
    client, fake, state = env
    now = datetime.now(timezone.utc)
    recent = [{"staff_id": OWNER["id"], "created_at": (now - timedelta(minutes=m)).isoformat()} for m in range(1, 10)]
    fake.seed("data_export_log", recent)  # 9 in the window
    # an old row outside the window and another user's rows don't count
    fake.seed("data_export_log", [{"staff_id": OWNER["id"], "created_at": (now - timedelta(hours=2)).isoformat()}])
    fake.seed("data_export_log", [{"staff_id": "someone-else", "created_at": now.isoformat()} for _ in range(5)])
    assert client.get("/members/export?format=csv").status_code == 200
    # FakeClient doesn't apply the DB's created_at default; stamp the row
    # the route just logged so it counts, as it would in Postgres -> 10 now.
    fake.tables["data_export_log"][-1]["created_at"] = now.isoformat()
    r = client.get("/members/export?format=csv")
    assert r.status_code == 429
    assert "Export limit reached" in r.json()["detail"]
    assert 0 < int(r.headers["retry-after"]) <= 3600
    assert len([x for x in fake.tables["data_export_log"] if x["staff_id"] == OWNER["id"]]) == 11  # 429 not logged


def test_export_route_is_not_captured_by_member_detail(env, monkeypatch):
    client, _, state = env
    import members

    def boom(*_a, **_k):
        raise AssertionError("GET /members/{member_id} handled /members/export")

    monkeypatch.setattr(members, "get_member_or_404", boom)
    assert client.get("/members/export").status_code == 200  # format defaults to csv
    assert state["calls"]


def test_suspended_tenant_gets_402_through_the_real_dependency(env, monkeypatch):
    client, _, state = env
    app.dependency_overrides.clear()  # use the real get_current_staff

    class _User:
        id = OWNER["id"]

    app.dependency_overrides[auth.get_current_user] = lambda: _User()
    monkeypatch.setattr(auth, "get_staff_row", lambda _uid: {**OWNER, "tenant": {"billing_status": "suspended"}})
    r = client.get("/members/export?format=csv")
    assert r.status_code == 402 and state["calls"] == []
    monkeypatch.setattr(auth, "get_staff_row", lambda _uid: {**OWNER, "tenant": {"billing_status": "active"}})
    assert client.get("/members/export?format=csv").status_code == 200
