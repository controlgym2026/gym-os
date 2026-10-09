"""Bulk member photo directory — a printable PDF grid, one small card per
member (photo + name/ID/phone/status below it), paginated automatically
across as many A4 pages as needed.

Member photos must already be downloaded by the caller (server-side, via
the service_role Storage client — see reports.py) into `photo_bytes_by_member_id`;
this module only lays them out. A member with no photo (or no entry in
that dict) gets a colored initial-letter placeholder instead of a blank
box — the same convention as MemberPhoto.tsx's frontend fallback, with the
same name-hashed color palette, so the printed sheet looks consistent with
what staff already see on screen.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle

COLS = 3
CARD_W = 58 * mm
PHOTO_SIDE = 50 * mm

# Same six hues as apps/web/components/MemberPhoto.tsx's AVATAR_COLORS, in
# the same order, so a given name hashes to the same color in the app and
# on the printed sheet.
AVATAR_COLORS = [
    colors.HexColor("#059669"),  # emerald-600
    colors.HexColor("#0d9488"),  # teal-600
    colors.HexColor("#2563eb"),  # blue-600
    colors.HexColor("#9333ea"),  # purple-600
    colors.HexColor("#e11d48"),  # rose-600
    colors.HexColor("#d97706"),  # amber-600
]


def _color_for(name: str) -> colors.Color:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return AVATAR_COLORS[h % len(AVATAR_COLORS)]


def _photo_flowable(member: dict, photo_bytes: bytes | None):
    if photo_bytes:
        try:
            return Image(BytesIO(photo_bytes), width=PHOTO_SIDE, height=PHOTO_SIDE)
        except Exception:
            pass  # corrupt/unreadable image — fall through to the placeholder
    initial = (member["name"].strip()[:1] or "?").upper()
    style = ParagraphStyle(
        "placeholder_initial", fontSize=28, leading=32, alignment=1,
        textColor=colors.white, fontName="Helvetica-Bold",
    )
    placeholder = Table([[Paragraph(initial, style)]], colWidths=[PHOTO_SIDE], rowHeights=[PHOTO_SIDE])
    placeholder.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _color_for(member["name"])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return placeholder


def _member_card(member: dict, photo_bytes: bytes | None, styles) -> Table:
    sub = member.get("current_subscription")
    status_line = sub["status"] if sub else "No plan"
    if sub and sub.get("end_date"):
        status_line += f" · {sub['end_date']}"

    rows = [
        [_photo_flowable(member, photo_bytes)],
        [Paragraph(member["name"], styles["name"])],
        [Paragraph(f"#{member.get('member_number', '')}", styles["detail"])],
        [Paragraph(member.get("phone") or "—", styles["detail"])],
        [Paragraph(status_line, styles["detail"])],
    ]
    card = Table(rows, colWidths=[CARD_W])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#d1d5db")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4),
            ]
        )
    )
    return card


def build_member_directory_pdf(members: list[dict], photo_bytes_by_member_id: dict[str, bytes]) -> bytes:
    base = getSampleStyleSheet()
    styles = {
        "name": ParagraphStyle("card_name", parent=base["Normal"], fontSize=9, leading=11, alignment=1, fontName="Helvetica-Bold"),
        "detail": ParagraphStyle("card_detail", parent=base["Normal"], fontSize=7, leading=9, alignment=1, textColor=colors.grey),
    }

    cards = [_member_card(m, photo_bytes_by_member_id.get(m["id"]), styles) for m in members]
    grid_rows = [cards[i : i + COLS] for i in range(0, len(cards), COLS)]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=12 * mm, bottomMargin=12 * mm, leftMargin=10 * mm, rightMargin=10 * mm,
    )

    if not grid_rows:
        doc.build([Paragraph("No members to show.", styles["detail"])])
        return buf.getvalue()

    grid = Table(grid_rows, colWidths=[CARD_W + 4 * mm] * COLS)
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    doc.build([grid])
    return buf.getvalue()
