"""
Generates sample_data/nightmare_invoice.pdf — a deliberately messy, unaligned
invoice with no real table structure, inconsistent spacing, wrapped line
items, and mixed-in summary rows. This is the "nightmare" input this project
is built to handle.

Run: python scripts/generate_sample_pdf.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "nightmare_invoice.pdf"


def build_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    y = height - 60

    def line(text, x=50, size=10, font="Helvetica", gap=16):
        nonlocal y
        c.setFont(font, size)
        c.drawString(x, y, text)
        y -= gap

    # Messy header - inconsistent spacing, no clean label/value alignment
    line("BRIGHTPATH MARKETING CO.", size=14, font="Helvetica-Bold", gap=20)
    line("2118  Ravenswood   Ave,  Suite  400   Chicago IL 60613")
    line("Invoice#  BP-2026-0447        Date 03/12/2026     Terms: Net 30")
    y -= 10

    # No real header row — just a loosely aligned label line, then ragged items
    line("DESCRIPTION                                   QTY    AMOUNT", font="Helvetica-Bold")
    y -= 4

    items = [
        "Google Ads mgmt fee - Q1 campaign             1        2,450.00",
        "  (retainer, includes 2 rounds of creative revisions)",
        "Facebook/Meta ad spend passthrough    ---     14,802.33",
        "Stock photography license x12 images   12    @  18.50   222.00",
        "Freelance copywriter - landing pages, 8 hrs @ 65/hr",
        "                                                          520.00",
        "Zoom Business subscription (3 seats) monthly            74.97",
        "Canva Pro annual - renewed",
        "                          1                              119.99",
        "Shipping - trade show banners & swag to Austin TX",
        "    2 boxes, FedEx Ground                                 88.40",
        "Misc office snacks + coffee for client visit    n/a       41.16",
        "Adobe Creative Cloud - team plan (4 licenses)    4      239.96",
        "Consulting - GA4 migration audit (Priya R.)     6 hrs   900.00",
    ]
    for it in items:
        line(it, x=50, size=9.5, gap=14)

    y -= 10
    line("---------------------------------------------------------------")
    line("Subtotal                                                19,458.81", font="Helvetica-Bold")
    line("Tax (0% - services)                                          0.00")
    line("TOTAL DUE                                              19,458.81", font="Helvetica-Bold")
    y -= 20
    line("Please remit payment within 30 days to avoid late fees.", size=8)
    line("Questions? billing@brightpathmarketing.example", size=8)

    c.showPage()
    c.save()


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(OUT_PATH)
    print(f"Wrote {OUT_PATH}")
