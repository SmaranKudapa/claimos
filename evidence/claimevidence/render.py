from __future__ import annotations

import html as H
import io
import re
from pathlib import Path

from .html import to_html
from .report import Doc

PAGE_RE = re.compile(r"\{\{page:([a-z0-9_]+)\}\}")

FONT = "Times-Roman"
FONT_B = "Times-Bold"
SANS = "Helvetica"
SANS_B = "Helvetica-Bold"
BODY_PT = 11
TABLE_PT = 8.5


def _esc(t: str) -> str:
    return H.escape(str(t), quote=False)


def _index_rows(doc: Doc, pages: dict | None) -> list[list[str]]:
    return [[e["id"], e["description"], e["date"], e["source"], str((pages or {}).get(e["key"], "{{page:%s}}" % e["key"])), e["supports"]]
            for e in doc.exhibits]


INDEX_HEAD = ["Exhibit", "Description", "Date", "Source", "Page", "Supports"]
INDEX_W = [0.62, 1.75, 0.95, 1.35, 0.42, 1.91]


def to_pdf(doc: Doc, path: Path, footer_left: str, title: str, subject: str = "", passes: int = 4) -> dict:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, LongTable, PageBreak, PageTemplate,
                                    Paragraph, Spacer, TableStyle)

    st = {
        "title": ParagraphStyle("title", fontName=SANS_B, fontSize=17, leading=21, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontName=SANS, fontSize=10, leading=13, textColor=colors.HexColor("#333333"), spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName=SANS_B, fontSize=13, leading=16, spaceBefore=12, spaceAfter=6, keepWithNext=1),
        "exhibit": ParagraphStyle("exhibit", fontName=SANS_B, fontSize=11.5, leading=14, spaceBefore=4, spaceAfter=6, keepWithNext=1),
        "p": ParagraphStyle("p", fontName=FONT, fontSize=BODY_PT, leading=BODY_PT * 1.32, spaceAfter=6, alignment=TA_LEFT),
        "lead": ParagraphStyle("lead", fontName=FONT, fontSize=BODY_PT, leading=BODY_PT * 1.32, spaceAfter=6, alignment=TA_LEFT, keepWithNext=1),
        "note": ParagraphStyle("note", fontName=FONT, fontSize=10, leading=13, spaceBefore=8, borderPadding=6,
                               borderColor=colors.HexColor("#666666"), borderWidth=0.6, spaceAfter=8),
        "cell": ParagraphStyle("cell", fontName=SANS, fontSize=TABLE_PT, leading=TABLE_PT * 1.25),
        "cellb": ParagraphStyle("cellb", fontName=SANS_B, fontSize=TABLE_PT, leading=TABLE_PT * 1.25),
        "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=BODY_PT, leading=BODY_PT * 1.32, leftIndent=14, bulletIndent=2, spaceAfter=3),
        "caption": ParagraphStyle("caption", fontName=SANS, fontSize=8.5, leading=11, textColor=colors.HexColor("#333333")),
    }
    width = letter[0] - 2 * inch

    class Anchored(Paragraph):
        def __init__(self, text, style, key=None, level=0, label=None):
            super().__init__(text, style)
            self.anchor_key, self.level, self.label = key, level, label

    def table(head, rows, widths, name):
        data = [[Paragraph(_esc(h), st["cellb"]) for h in head]] + [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
        if widths:
            total = sum(widths)
            cw = [width * w / total for w in widths]
        else:
            k = len(head)
            first = width * 0.16
            cw = [first] + [(width - first) / (k - 1)] * (k - 1)
        t = LongTable(data, colWidths=cw, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#808080")),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    def story(pages):
        out = []
        for b in doc.blocks:
            kind = b[0]
            if kind == "title":
                out.append(Anchored(_esc(b[1]), st["title"], key="cover", level=0, label="Identification"))
            elif kind == "subtitle":
                out.append(Paragraph(_esc(b[1]), st["subtitle"]))
            elif kind == "meta":
                out.append(table(["Item", "Detail"], [[k, v] for k, v in b[1]], [1.6, 4.9], "meta"))
            elif kind == "note":
                out.append(Paragraph(_esc(b[1]), st["note"]))
            elif kind == "h1":
                out.append(Anchored(_esc(b[1]), st["h1"], key="sec_" + re.sub(r"[^a-z0-9]+", "_", b[1].lower()), level=0, label=b[1]))
            elif kind == "p":
                out.append(Paragraph(_esc(b[1]), st["lead"] if b[1].rstrip().endswith(":") else st["p"]))
            elif kind == "bullets":
                for x in b[1]:
                    out.append(Paragraph(_esc(x), st["bullet"], bulletText="•"))
            elif kind == "table":
                t = table(b[1], b[2], b[3], b[4])
                lead = []
                while out and getattr(out[-1], "style", None) in (st["lead"], st["h1"], st["exhibit"]):
                    lead.insert(0, out.pop())
                if len(b[2]) <= 12:
                    out.append(KeepTogether(lead + [t]))
                else:
                    out.extend(lead + [t])
                out.append(Spacer(1, 6))
            elif kind == "index":
                out.append(table(INDEX_HEAD, _index_rows(doc, pages), INDEX_W, "index"))
            elif kind == "pagebreak":
                out.append(PageBreak())
            elif kind == "exhibit":
                if b[2] == "Exhibit 1":
                    out.append(PageBreak())
                    out.append(Anchored("Exhibits", st["h1"], key="sec_exhibits", level=0, label="Exhibits"))
                else:
                    out.append(Spacer(1, 10))
                out.append(Anchored(_esc(f"{b[2]}: {b[3]}"), st["exhibit"], key=b[1], level=1, label=f"{b[2]}: {b[3]}"))
            elif kind == "image":
                img = Image(b[1])
                iw, ih = img.imageWidth, img.imageHeight
                scale = min(width / iw, (6.5 * inch) / ih, 1.0)
                img.drawWidth, img.drawHeight = iw * scale, ih * scale
                out.append(KeepTogether([img, Spacer(1, 4), Paragraph(_esc(b[2]), st["caption"])]))
        return out

    class Tpl(BaseDocTemplate):
        def __init__(self, fh, **kw):
            super().__init__(fh, **kw)
            self.found, self.outline = {}, []
            frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
            self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self.chrome)])
            self.total = None

        def chrome(self, canv, d):
            canv.saveState()
            canv.setFont(SANS, 8)
            canv.setFillGray(0.25)
            canv.drawString(inch, letter[1] - 0.6 * inch, title)
            canv.drawRightString(letter[0] - inch, letter[1] - 0.6 * inch, doc.case_label)
            canv.setLineWidth(0.4)
            canv.setStrokeGray(0.6)
            canv.line(inch, letter[1] - 0.66 * inch, letter[0] - inch, letter[1] - 0.66 * inch)
            canv.drawString(inch, 0.55 * inch, footer_left)
            pg = canv.getPageNumber()
            canv.drawRightString(letter[0] - inch, 0.55 * inch, f"Page {pg} of {self.total}" if self.total else f"Page {pg}")
            canv.restoreState()

        def afterFlowable(self, f):
            key = getattr(f, "anchor_key", None)
            if key:
                pg = self.canv.getPageNumber()
                self.found.setdefault(key, pg)
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(f.label, key, level=f.level, closed=False)
                self.outline.append({"key": key, "label": f.label, "level": f.level, "page": pg})

    def build(pages, total):
        buf = io.BytesIO()
        t = Tpl(buf, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=0.9 * inch, bottomMargin=0.85 * inch,
                title=title, author="Claim OS", subject=subject, creator="Claim OS Evidence", invariant=1)
        t.total = total
        t.build(story(pages))
        return buf.getvalue(), t.found, t.outline, t.page

    pages, total = None, None
    for _ in range(passes):
        data, found, outline, last = build(pages, total)
        new_pages = {e["key"]: found.get(e["key"]) for e in doc.exhibits}
        if new_pages == pages and last == total:
            break
        pages, total = new_pages, last
    for e in doc.exhibits:
        e["page"] = found.get(e["key"])
    Path(path).write_bytes(data)
    return {"pages": last, "exhibit_pages": {e["id"]: e["page"] for e in doc.exhibits}, "outline": outline, "bytes": len(data)}


def to_markdown(doc: Doc, pages: dict | None = None) -> str:
    L = []

    def cell(x):
        return str(x).replace("|", "/").replace("\n", " ")

    def tab(head, rows):
        L.append("| " + " | ".join(cell(h) for h in head) + " |")
        L.append("|" + "---|" * len(head))
        L.extend("| " + " | ".join(cell(c) for c in r) + " |" for r in rows)
        L.append("")

    for b in doc.blocks:
        k = b[0]
        if k == "title":
            L += [f"# {b[1]}", ""]
        elif k == "subtitle":
            L += [b[1], ""]
        elif k == "meta":
            tab(["Item", "Detail"], [[a, v] for a, v in b[1]])
        elif k == "note":
            L += [f"> {b[1]}", ""]
        elif k == "h1":
            L += [f"## {b[1]}", ""]
        elif k == "p":
            L += [b[1], ""]
        elif k == "bullets":
            L += [f"- {x}" for x in b[1]] + [""]
        elif k == "table":
            tab(b[1], b[2])
        elif k == "index":
            tab(INDEX_HEAD, _index_rows(doc, pages or {e["key"]: e.get("page") or "-" for e in doc.exhibits}))
        elif k == "exhibit":
            L += [f"## {b[2]}: {b[3]}", ""]
        elif k == "image":
            L += [f"[Image: {b[2]}]", ""]
    return "\n".join(L)
