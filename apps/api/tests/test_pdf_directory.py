"""Tests for build_member_directory_pdf — can't meaningfully assert on
rendered pixels, so these check what's actually checkable: it produces a
real PDF for any input (including zero/one/many members, with and without
photo bytes, with and without a name to hash a placeholder color from) and
never raises."""

from io import BytesIO

from PIL import Image as PILImage

from pdf_directory import _color_for, _downscale_photo, build_member_directory_pdf

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


def _real_jpeg(width: int, height: int) -> bytes:
    """An actually-decodable JPEG, unlike _TINY_JPEG above — needed to
    exercise the real PIL resize/recompress path, not just its except branch."""
    img = PILImage.new("RGB", (width, height), color=(120, 45, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestDownscalePhoto:
    def test_large_photo_is_shrunk_well_below_original_size(self):
        """The real-world case this exists for: a multi-megapixel phone
        photo must not be embedded in the PDF at full resolution — that's
        what OOM-crashed Render's free instance on the full member
        directory (335 members, 106 real photos -> 502, empty body, ~28s
        in) once photo count got large."""
        original = _real_jpeg(3000, 3000)
        shrunk = _downscale_photo(original)
        assert len(shrunk) < len(original)
        out = PILImage.open(BytesIO(shrunk))
        assert max(out.size) <= 400

    def test_small_photo_stays_small(self):
        original = _real_jpeg(100, 100)
        shrunk = _downscale_photo(original)
        out = PILImage.open(BytesIO(shrunk))
        assert out.size == (100, 100)

    def test_non_square_photo_keeps_aspect_ratio(self):
        original = _real_jpeg(4000, 2000)
        shrunk = _downscale_photo(original)
        out = PILImage.open(BytesIO(shrunk))
        assert out.size[0] == 400
        assert out.size[1] == 200

    def test_corrupt_bytes_pass_through_unchanged(self):
        garbage = b"not an image at all"
        assert _downscale_photo(garbage) == garbage
