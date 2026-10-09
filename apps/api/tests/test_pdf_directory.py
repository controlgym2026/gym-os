"""Tests for build_member_directory_pdf — can't meaningfully assert on
rendered pixels, so these check what's actually checkable: it produces a
real PDF for any input (including zero/one/many members, with and without
photo bytes, with and without a name to hash a placeholder color from) and
never raises."""

from pdf_directory import _color_for, build_member_directory_pdf

# Minimal recognizable byte sequence — enough for reportlab's own JPEG
# decoder to accept it as a 1x1 image; what matters here is only that a
# *present* entry in photo_bytes_by_member_id takes the photo path instead
# of the placeholder path, not that it looks like anything in particular.
_TINY_JPEG = bytes.fromhex("FFD8FFE000104A46494600010100000100010000FFD9")


def _member(mid, name, number=1, sub=None):
    return {"id": mid, "name": name, "phone": "9999999999", "member_number": number, "current_subscription": sub}


def _is_pdf(b: bytes) -> bool:
    return b.startswith(b"%PDF-")


class TestBasicGeneration:
    def test_empty_member_list_still_produces_a_valid_pdf(self):
        pdf = build_member_directory_pdf([], {})
        assert _is_pdf(pdf)

    def test_single_member_no_photo(self):
        pdf = build_member_directory_pdf([_member("m1", "Alice")], {})
        assert _is_pdf(pdf)

    def test_single_member_with_photo(self):
        pdf = build_member_directory_pdf([_member("m1", "Alice")], {"m1": _TINY_JPEG})
        assert _is_pdf(pdf)

    def test_mixed_photo_and_no_photo(self):
        members = [_member("m1", "Alice"), _member("m2", "Bob"), _member("m3", "Carol")]
        pdf = build_member_directory_pdf(members, {"m2": _TINY_JPEG})
        assert _is_pdf(pdf)

    def test_many_members_spans_multiple_pages_without_error(self):
        members = [_member(f"m{i}", f"Member {i}", i) for i in range(1, 61)]  # forces pagination
        pdf = build_member_directory_pdf(members, {})
        assert _is_pdf(pdf)
        assert len(pdf) > 0

    def test_corrupt_photo_bytes_fall_back_to_placeholder_without_raising(self):
        pdf = build_member_directory_pdf([_member("m1", "Alice")], {"m1": b"not a real image"})
        assert _is_pdf(pdf)

    def test_member_with_no_current_subscription(self):
        pdf = build_member_directory_pdf([_member("m1", "Alice", sub=None)], {})
        assert _is_pdf(pdf)

    def test_member_with_empty_name_still_renders(self):
        """An initial-letter placeholder needs *a* letter — an edge-case
        blank name must still produce something, not crash."""
        pdf = build_member_directory_pdf([_member("m1", "")], {})
        assert _is_pdf(pdf)


class TestColorFor:
    def test_same_name_always_gets_the_same_color(self):
        assert _color_for("Alice") == _color_for("Alice")

    def test_different_names_can_get_different_colors(self):
        colors_seen = {_color_for(f"Name{i}") for i in range(20)}
        assert len(colors_seen) > 1
