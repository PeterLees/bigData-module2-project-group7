"""Stamp a running footer and page numbers onto the rendered runbook.

Chrome's --print-to-pdf can only emit its own header/footer, which includes the
local file:// URL. So the page is rendered clean and the footer is added here.
The cover page is left untouched.
"""
import io, sys
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

SRC, DST = sys.argv[1], sys.argv[2]
LEFT = "Big Data Module 2  ·  Group 7  ·  Runbook"

reader = PdfReader(SRC)
total = len(reader.pages)
writer = PdfWriter()

for i, page in enumerate(reader.pages):
    if i > 0:  # no footer on the cover
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setStrokeColor(HexColor("#c9d3dd")); c.setLineWidth(0.5)
        c.line(45, 34, w - 45, 34)
        c.setFont("Helvetica", 7.5); c.setFillColor(HexColor("#8a8a8a"))
        c.drawString(45, 23, LEFT)
        c.drawRightString(w - 45, 23, f"Page {i} of {total - 1}")
        c.save(); buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    writer.add_page(page)

writer.add_metadata({
    "/Title": "Module 2 Group 7 — Runbook: How to Run the Project",
    "/Subject": "From an empty machine to the live dashboard",
    "/Author": "Big Data Module 2, Group 7",
    "/Creator": "Olist delivery-performance pipeline",
})
with open(DST, "wb") as fh:
    writer.write(fh)
print(f"stamped {total} pages -> {DST}")
