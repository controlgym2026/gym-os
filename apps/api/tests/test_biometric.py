"""Tests for the ATTLOG parser (pure) and the biometric ingestion pipeline
(against FakeClient — matched member, unmatched PIN, duplicate/retry,
inactive subscription, per the Phase 2 spec's required scenarios)."""

from datetime import datetime, timedelta, timezone

from biometric import ingest_attlog, parse_attlog_body, parse_attlog_line
from tests.fake_client import FakeClient

TENANT = "tenant-1"
DEVICE_ID = "device-1"
BRANCH_ID = "branch-1"


class TestParseAttlogLine:
    def test_parses_tab_delimited_line(self):
        rec = parse_attlog_line("1001\t2026-01-15 09:30:00\t0\t1\t0")
        assert rec is not None
        assert rec.pin == "1001"
        assert rec.timestamp == datetime(2026, 1, 15, 9, 30, 0)
        assert rec.raw_timestamp == "2026-01-15 09:30:00"

    def test_ignores_blank_line(self):
        assert parse_attlog_line("") is None
        assert parse_attlog_line("   ") is None
        assert parse_attlog_line("\r\n") is None

    def test_rejects_too_few_fields(self):
        assert parse_attlog_line("1001") is None

    def test_rejects_unparseable_timestamp(self):
        assert parse_attlog_line("1001\tnot-a-date\t0\t1\t0") is None

    def test_extra_trailing_fields_ignored(self):
        # Real firmware may send more columns than the reference shape.
        rec = parse_attlog_line("1001\t2026-01-15 09:30:00\t0\t1\t0\textra\tcolumns")
        assert rec is not None
        assert rec.pin == "1001"

    def test_parses_multi_line_body_skipping_bad_lines(self):
        body = "1001\t2026-01-15 09:30:00\t0\t1\t0\n\n1002\t2026-01-15 09:31:00\t0\t1\t0\nbroken-line\n"
        records = parse_attlog_body(body)
        assert [r.pin for r in records] == ["1001", "1002"]


def _device(**overrides) -> dict:
    base = {
        "id": DEVICE_ID,
        "tenant_id": TENANT,
        "branch_id": BRANCH_ID,
        "branch": {"timezone": "UTC"},
    }
    base.update(overrides)
    return base


def _member(member_id="member-1", pin="1001", **overrides) -> dict:
    base = {
        "id": member_id,
        "tenant_id": TENANT,
        "biometric_ref": pin,
        "deleted_at": None,
        "name": "Test Member",
    }
    base.update(overrides)
    return base


def _active_subscription(member_id="member-1", **overrides) -> dict:
    base = {
        "id": "sub-1",
        "tenant_id": TENANT,
        "member_id": member_id,
        "status": "ACTIVE",
        "end_date": (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat(),
        "sessions_remaining": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _record(pin="1001", when: datetime | None = None) -> "object":
    when = when or datetime(2026, 1, 15, 9, 30, 0)
    ts_str = when.strftime("%Y-%m-%d %H:%M:%S")
    return parse_attlog_line(f"{pin}\t{ts_str}\t0\t1\t0")


class TestIngestAttlog:
    def test_matched_member_with_active_subscription_is_accepted(self):
        client = FakeClient()
        client.seed("member", [_member()])
        client.seed("subscription", [_active_subscription()])

        stats = ingest_attlog(client, _device(), [_record()])

        assert stats == {"accepted": 1, "unmatched": 0, "rejected": 0, "duplicate": 0}
        attendance = client.tables["attendance"]
        assert len(attendance) == 1
        assert attendance[0]["source"] == "biometric"
        assert attendance[0]["member_id"] == "member-1"
        assert attendance[0]["branch_id"] == BRANCH_ID

    def test_unmatched_pin_is_logged_not_dropped(self):
        client = FakeClient()
        client.seed("member", [_member(pin="1001")])
        client.seed("subscription", [_active_subscription()])

        stats = ingest_attlog(client, _device(), [_record(pin="9999")])

        assert stats == {"accepted": 0, "unmatched": 1, "rejected": 0, "duplicate": 0}
        assert client.tables.get("attendance", []) == []
        unmatched = client.tables["attendance_unmatched"]
        assert len(unmatched) == 1
        assert unmatched[0]["raw_pin"] == "9999"
        assert unmatched[0]["member_id"] is None
        assert unmatched[0]["reason"] == "unmatched_pin"

    def test_inactive_subscription_is_rejected_and_logged(self):
        client = FakeClient()
        client.seed("member", [_member()])
        client.seed("subscription", [_active_subscription(status="FROZEN")])

        stats = ingest_attlog(client, _device(), [_record()])

        assert stats == {"accepted": 0, "unmatched": 0, "rejected": 1, "duplicate": 0}
        assert client.tables.get("attendance", []) == []
        unmatched = client.tables["attendance_unmatched"]
        assert len(unmatched) == 1
        assert unmatched[0]["member_id"] == "member-1"
        assert "frozen" in unmatched[0]["reason"]

    def test_no_subscription_at_all_is_rejected_and_logged(self):
        client = FakeClient()
        client.seed("member", [_member()])
        # no subscription seeded

        stats = ingest_attlog(client, _device(), [_record()])

        assert stats == {"accepted": 0, "unmatched": 0, "rejected": 1, "duplicate": 0}
        assert "no active subscription" in client.tables["attendance_unmatched"][0]["reason"]

    def test_duplicate_push_within_window_is_not_double_logged(self):
        client = FakeClient()
        client.seed("member", [_member()])
        client.seed("subscription", [_active_subscription()])

        first = ingest_attlog(client, _device(), [_record()])
        assert first["accepted"] == 1

        # Device retries the exact same record (or one a minute later, still
        # inside the 2-minute tolerance window).
        retry = _record(when=datetime(2026, 1, 15, 9, 31, 30))
        second = ingest_attlog(client, _device(), [retry])

        assert second == {"accepted": 0, "unmatched": 0, "rejected": 0, "duplicate": 1}
        assert len(client.tables["attendance"]) == 1  # still just the one row

    def test_retry_outside_dedup_window_is_a_new_checkin(self):
        client = FakeClient()
        client.seed("member", [_member()])
        client.seed("subscription", [_active_subscription()])

        ingest_attlog(client, _device(), [_record()])
        later = _record(when=datetime(2026, 1, 15, 12, 0, 0))  # hours later
        stats = ingest_attlog(client, _device(), [later])

        assert stats["accepted"] == 1
        assert len(client.tables["attendance"]) == 2

    def test_multi_record_push_mixes_outcomes_independently(self):
        client = FakeClient()
        client.seed(
            "member",
            [_member(member_id="m-active", pin="1001"), _member(member_id="m-frozen", pin="1002")],
        )
        client.seed(
            "subscription",
            [
                _active_subscription(member_id="m-active", id="sub-a"),
                _active_subscription(member_id="m-frozen", id="sub-f", status="FROZEN"),
            ],
        )

        records = [_record(pin="1001"), _record(pin="1002"), _record(pin="unknown")]
        stats = ingest_attlog(client, _device(), records)

        assert stats == {"accepted": 1, "unmatched": 1, "rejected": 1, "duplicate": 0}

    def test_session_based_plan_decrements_and_can_auto_expire(self):
        client = FakeClient()
        client.seed("member", [_member()])
        client.seed(
            "subscription",
            [_active_subscription(end_date=None, sessions_remaining=1)],
        )

        stats = ingest_attlog(client, _device(), [_record()])

        assert stats["accepted"] == 1
        sub = client.tables["subscription"][0]
        assert sub["sessions_remaining"] == 0
        assert sub["status"] == "EXPIRED"
