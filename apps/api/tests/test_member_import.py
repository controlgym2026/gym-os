"""Tests for the member CSV import: parser (pure) and run_member_import
(against FakeClient) — missing name, duplicate phone (existing + within the
same file), plan_name matched/unmatched, and a mixed multi-row file."""

from member_import import parse_member_import_csv, run_member_import
from tests.fake_client import FakeClient

TENANT = "tenant-1"


class TestParseMemberImportCsv:
    def test_parses_basic_rows(self):
        text = "name,phone,email,plan_name\nRahul Sharma,9876543210,rahul@example.com,Monthly\n"
        rows = parse_member_import_csv(text)
        assert len(rows) == 1
        assert rows[0].name == "Rahul Sharma"
        assert rows[0].phone == "9876543210"
        assert rows[0].email == "rahul@example.com"
        assert rows[0].plan_name == "Monthly"

    def test_header_case_and_order_independent(self):
        text = "Plan_Name,Name,Email\nAnnual,Priya,priya@example.com\n"
        rows = parse_member_import_csv(text)
        assert rows[0].name == "Priya"
        assert rows[0].plan_name == "Annual"
        assert rows[0].phone is None

    def test_blank_optional_fields_become_none(self):
        text = "name,phone,email,plan_name\nAmit,,amit@example.com,\n"
        rows = parse_member_import_csv(text)
        assert rows[0].phone is None
        assert rows[0].plan_name is None

    def test_skips_blank_lines(self):
        text = "name,phone\nA,1\n\n   \nB,2\n"
        rows = parse_member_import_csv(text)
        assert [r.name for r in rows] == ["A", "B"]

    def test_quoted_field_with_embedded_comma(self):
        text = 'name,phone\n"Sharma, Rahul",9876543210\n'
        rows = parse_member_import_csv(text)
        assert rows[0].name == "Sharma, Rahul"

    def test_empty_file_returns_no_rows(self):
        assert parse_member_import_csv("") == []

    def test_line_numbers_are_1_indexed_from_first_data_row(self):
        text = "name\nFirst\nSecond\nThird\n"
        rows = parse_member_import_csv(text)
        assert [r.line for r in rows] == [1, 2, 3]


def _plan(**overrides) -> dict:
    base = {
        "id": "plan-1",
        "tenant_id": TENANT,
        "name": "Monthly",
        "is_active": True,
        "duration_days": 30,
        "session_limit": None,
    }
    base.update(overrides)
    return base


def _row(line=1, name="Test", phone=None, email=None, plan_name=None):
    from member_import import ImportRow

    return ImportRow(line=line, name=name, phone=phone, email=email, plan_name=plan_name)


class TestRunMemberImport:
    def test_imports_a_simple_row(self):
        client = FakeClient()
        result = run_member_import(client, TENANT, [_row(name="Alice", phone="111")])
        assert result["imported"] == 1
        assert result["skipped"] == []
        assert len(client.tables["member"]) == 1
        assert client.tables["member"][0]["name"] == "Alice"

    def test_missing_name_is_skipped(self):
        client = FakeClient()
        result = run_member_import(client, TENANT, [_row(name="  ", phone="111")])
        assert result["imported"] == 0
        assert result["skipped"] == [{"line": 1, "reason": "missing name"}]

    def test_duplicate_phone_against_existing_member_is_skipped(self):
        client = FakeClient()
        client.seed("member", [{"id": "m-1", "tenant_id": TENANT, "phone": "999", "deleted_at": None}])
        result = run_member_import(client, TENANT, [_row(name="Bob", phone="999")])
        assert result["imported"] == 0
        assert result["skipped"] == [{"line": 1, "reason": "duplicate phone"}]

    def test_duplicate_phone_within_the_same_file_is_skipped(self):
        client = FakeClient()
        rows = [_row(line=1, name="First", phone="555"), _row(line=2, name="Second", phone="555")]
        result = run_member_import(client, TENANT, rows)
        assert result["imported"] == 1
        assert result["skipped"] == [{"line": 2, "reason": "duplicate phone"}]

    def test_members_without_phone_never_collide(self):
        client = FakeClient()
        rows = [_row(line=1, name="First"), _row(line=2, name="Second")]
        result = run_member_import(client, TENANT, rows)
        assert result["imported"] == 2
        assert result["skipped"] == []

    def test_matched_plan_name_starts_a_subscription(self):
        client = FakeClient()
        client.seed("membership_plan", [_plan()])
        result = run_member_import(client, TENANT, [_row(name="Alice", plan_name="monthly")])  # case-insensitive
        assert result["imported"] == 1
        assert result["subscriptions_started"] == 1
        assert result["plan_warnings"] == []
        assert len(client.tables["subscription"]) == 1
        assert client.tables["subscription"][0]["status"] == "ACTIVE"

    def test_unmatched_plan_name_is_a_warning_not_a_skip(self):
        client = FakeClient()
        result = run_member_import(client, TENANT, [_row(name="Alice", plan_name="Nonexistent Plan")])
        assert result["imported"] == 1  # member still created
        assert result["subscriptions_started"] == 0
        assert result["plan_warnings"] == [{"line": 1, "plan_name": "Nonexistent Plan"}]

    def test_inactive_plan_is_not_matched(self):
        client = FakeClient()
        client.seed("membership_plan", [_plan(is_active=False)])
        result = run_member_import(client, TENANT, [_row(name="Alice", plan_name="Monthly")])
        assert result["subscriptions_started"] == 0
        assert result["plan_warnings"] == [{"line": 1, "plan_name": "Monthly"}]

    def test_mixed_file_reports_each_row_independently(self):
        client = FakeClient()
        client.seed("member", [{"id": "existing", "tenant_id": TENANT, "phone": "111", "deleted_at": None}])
        client.seed("membership_plan", [_plan()])
        rows = [
            _row(line=1, name="Good", phone="222", plan_name="Monthly"),
            _row(line=2, name="", phone="333"),
            _row(line=3, name="Dup", phone="111"),
        ]
        result = run_member_import(client, TENANT, rows)
        assert result["imported"] == 1
        assert result["subscriptions_started"] == 1
        assert {s["reason"] for s in result["skipped"]} == {"missing name", "duplicate phone"}
