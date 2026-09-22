"""get_super_admin_emails() parsing — the pure piece behind
get_current_super_admin. The rest of Phase 3's auth separation (403 for
non-admins, suspension blocking/restoring tenant-scoped access, audit log
correctness) is verified live against production — see the Phase 3 report;
it isn't meaningfully unit-testable without faking Supabase's Auth server
itself (get_current_user calls out to it directly, by design — see
auth.py's module docstring)."""

from auth import get_super_admin_emails


def test_parses_comma_separated_emails(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "a@x.com, B@Y.com ,c@z.com")
    assert get_super_admin_emails() == {"a@x.com", "b@y.com", "c@z.com"}


def test_empty_env_var_yields_empty_set(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "")
    assert get_super_admin_emails() == set()


def test_missing_env_var_yields_empty_set(monkeypatch):
    monkeypatch.delenv("SUPER_ADMIN_EMAILS", raising=False)
    assert get_super_admin_emails() == set()


def test_ignores_blank_entries_between_commas(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "a@x.com,,  ,b@y.com")
    assert get_super_admin_emails() == {"a@x.com", "b@y.com"}
