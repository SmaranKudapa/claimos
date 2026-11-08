from __future__ import annotations

import html as H
import io
import re
from pathlib import Path

from .html import to_html
from .report import Doc

BODY = "Helvetica"
BOLD = "Helvetica-Bold"
BODY_PT = 11
TABLE_PT = 9
NOTE_PT = 9
LEADING = 1.15

INDEX_HEAD = ["Exhibit", "Document or evidence", "Date", "Source", "Packet pages"]
INDEX_W = [0.75, 2.35, 1.0, 2.05, 0.75]
STYLE_DEFAULTS = {"page": "US Letter, 1 inch margins", "font": "Helvetica, the PDF standard face metrically identical to Arial (no embedding needed)",
                  "body": "11 pt, 1.15 line spacing, 6 pt after paragraphs, left aligned, no indent",
                  "headings": "14 pt bold sections, 11 pt bold subsections", "tables": "9 pt", "notes": "9 pt",
                  "footer": "parcel | year | Page X of Y, with DRAFT marking when release fields are missing"}


def _esc(t) -> str:
    return H.escape(str(t), quote=False)


def page_ranges(doc: Doc, starts: dict, total: int | None) -> dict:
    keys = [e["key"] for e in doc.exhibits]
    out = {}
    for i, k in enumerate(keys):
        s = starts.get(k)
        if not s:
            continue
        nxt = next((starts.get(x) for x in keys[i + 1:] if starts.get(x)), None)
        end = (nxt - 1 if nxt and nxt > s else s) if nxt else (total or s)
        out[k] = f"{s}" if end == s else f"{s}-{end}"
    return out


def _index_rows(doc: Doc, ranges: dict | None) -> list[list[str]]:
    return [[e["id"], e["description"], e["date"], e["source"], str((ranges or {}).get(e["key"], "-"))] for e in doc.exhibits]


def to_pdf(doc: Doc, path: Path, footer_left: str, title: str, subject: str = "", passes: int = 5) -> dict:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, LongTable, PageBreak, PageTemplate,
                                    Paragraph, Spacer, TableStyle)

    lead = BODY_PT * LEADING
    st = {
        "court": ParagraphStyle("court", fontName=BOLD, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=14),
        "title": ParagraphStyle("title", fontName=BOLD, fontSize=12, leading=15, alignment=TA_CENTER, spaceAfter=2),
        "draft": ParagraphStyle("draft", fontName=BOLD, fontSize=11, leading=lead, alignment=TA_CENTER, borderWidth=1,
                                borderColor=colors.black, borderPadding=6, spaceBefore=10, spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=14, leading=17, spaceBefore=12, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=11, leading=13.5, spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "exhibit": ParagraphStyle("exhibit", fontName=BOLD, fontSize=11, leading=13.5, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "p": ParagraphStyle("p", fontName=BODY, fontSize=BODY_PT, leading=lead, spaceAfter=6, alignment=TA_LEFT),
        "lead": ParagraphStyle("lead", fontName=BODY, fontSize=BODY_PT, leading=lead, spaceAfter=6, alignment=TA_LEFT, keepWithNext=1),
        "note": ParagraphStyle("note", fontName=BODY, fontSize=NOTE_PT, leading=NOTE_PT * 1.25, spaceBefore=6, spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName=BODY, fontSize=TABLE_PT, leading=TABLE_PT * 1.22),
        "cellb": ParagraphStyle("cellb", fontName=BOLD, fontSize=TABLE_PT, leading=TABLE_PT * 1.22),
        "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=BODY_PT, leading=lead, leftIndent=14, bulletIndent=2, spaceAfter=3),
        "caption": ParagraphStyle("caption", fontName=BODY, fontSize=NOTE_PT, leading=NOTE_PT * 1.25),
    }
    width = letter[0] - 2 * inch

    class Anchored(Paragraph):
        def __init__(self, text, style, key=None, level=0, label=None):
            super().__init__(text, style)
            self.anchor_key, self.level, self.label = key, level, label

    def table(head, rows, widths, name, header=True):
        body = [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
        data = ([[Paragraph(_esc(h), st["cellb"]) for h in head]] + body) if header else body
        if widths:
            total = sum(widths)
            cw = [width * w / total for w in widths]
        else:
            k = len(head)
            first = width * 0.2
            cw = [first] + [(width - first) / (k - 1)] * (k - 1)
        t = LongTable(data, colWidths=cw, repeatRows=1 if header else 0, hAlign="LEFT")
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#808080")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")))
        t.setStyle(TableStyle(style))
        return t

    def story(ranges):
        out = []
        first_exhibit = True
        for b in doc.blocks:
            kind = b[0]
            if kind == "court":
                out.append(Anchored(_esc(b[1]), st["court"], key="cover", level=0, label="Cover"))
            elif kind == "title":
                out.append(Paragraph(_esc(b[1]), st["title"]))
            elif kind == "draft":
                out.append(Paragraph(_esc(b[1]), st["draft"]))
            elif kind == "meta":
                out.append(Spacer(1, 10))
                out.append(table(["Field", "Content"], [[k, v] for k, v in b[1]], [1.9, 4.6], "meta"))
            elif kind == "note":
                out.append(Paragraph(_esc(b[1]), st["note"]))
            elif kind in ("h1", "h2"):
                key = "sec_" + re.sub(r"[^a-z0-9]+", "_", b[1].lower())
                out.append(Anchored(_esc(b[1]), st[kind], key=key, level=0 if kind == "h1" else 1, label=b[1]))
            elif kind == "p":
                out.append(Paragraph(_esc(b[1]), st["lead"] if b[1].rstrip().endswith(":") else st["p"]))
            elif kind == "bullets":
                for x in b[1]:
                    out.append(Paragraph(_esc(x), st["bullet"], bulletText="•"))
            elif kind in ("table", "index"):
                t = table(b[1], b[2], b[3], b[4]) if kind == "table" else table(INDEX_HEAD, _index_rows(doc, ranges), INDEX_W, "index")
                rows = len(b[2]) if kind == "table" else len(doc.exhibits)
                held = []
                if out and getattr(out[-1], "style", None) is st["p"] and rows <= 14:
                    held.insert(0, out.pop())
                while out and getattr(out[-1], "style", None) in (st["lead"], st["h1"], st["h2"], st["exhibit"]):
                    held.insert(0, out.pop())
                if rows <= 14:
                    out.append(KeepTogether(held + [t]))
                else:
                    out.extend(held + [t])
                out.append(Spacer(1, 6))
            elif kind == "pagebreak":
                out.append(PageBreak())
            elif kind == "exhibit":
                if first_exhibit:
                    out.append(PageBreak())
                    out.append(Anchored("Exhibits", st["h1"], key="sec_exhibits", level=0, label="Exhibits"))
                    first_exhibit = False
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
            canv.setFont(BODY, 8.5)
            canv.setFillGray(0)
            pg = canv.getPageNumber()
            text = f"{doc.case_label} | Page {pg} of {self.total}" if self.total else f"{doc.case_label} | Page {pg}"
            if doc.draft:
                text = "DRAFT - NOT FOR SUBMISSION | " + text
            canv.drawCentredString(letter[0] / 2, 0.6 * inch, text)
            canv.restoreState()

        def afterFlowable(self, f):
            key = getattr(f, "anchor_key", None)
            if key:
                pg = self.canv.getPageNumber()
                self.found.setdefault(key, pg)
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(f.label, key, level=f.level, closed=False)
                self.outline.append({"key": key, "label": f.label, "level": f.level, "page": pg})

    def build(ranges, total):
        buf = io.BytesIO()
        t = Tpl(buf, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch,
                title=title, author="Claim OS", subject=subject, creator="Claim OS Evidence", invariant=1)
        t.total = total
        t.build(story(ranges))
        return buf.getvalue(), t.found, t.outline, t.page

    ranges, total = None, None
    for _ in range(passes):
        data, found, outline, last = build(ranges, total)
        starts = {e["key"]: found.get(e["key"]) for e in doc.exhibits}
        new = page_ranges(doc, starts, last)
        if new == ranges and last == total:
            break
        ranges, total = new, last
    for e in doc.exhibits:
        e["page"] = found.get(e["key"])
        e["pages"] = (ranges or {}).get(e["key"])
    Path(path).write_bytes(data)
    return {"pages": last, "exhibit_pages": {e["id"]: e["pages"] for e in doc.exhibits}, "outline": outline, "bytes": len(data),
            "style": STYLE_DEFAULTS}


def to_markdown(doc: Doc, pages: dict | None = None) -> str:
    L = []
    ranges = pages or {e["key"]: e.get("pages") or "-" for e in doc.exhibits}

    def cell(x):
        return str(x).replace("|", "/").replace("\n", " ")

    def tab(head, rows):
        L.append("| " + " | ".join(cell(h) for h in head) + " |")
        L.append("|" + "---|" * len(head))
        L.extend("| " + " | ".join(cell(c) for c in r) + " |" for r in rows)
        L.append("")

    for b in doc.blocks:
        k = b[0]
        if k in ("court", "title"):
            L += [f"**{b[1]}**", ""]
        elif k == "draft":
            L += [f"> **{b[1]}**", ""]
        elif k == "meta":
            tab(["Field", "Content"], [[a, v] for a, v in b[1]])
        elif k == "note":
            L += [f"> {b[1]}", ""]
        elif k == "h1":
            L += [f"## {b[1]}", ""]
        elif k == "h2":
            L += [f"### {b[1]}", ""]
        elif k == "p":
            L += [b[1], ""]
        elif k == "bullets":
            L += [f"- {x}" for x in b[1]] + [""]
        elif k == "table":
            tab(b[1], b[2])
        elif k == "index":
            tab(INDEX_HEAD, _index_rows(doc, ranges))
        elif k == "exhibit":
            L += [f"## {b[2]}: {b[3]}", ""]
        elif k == "image":
            L += [f"[Image: {b[2]}]", ""]
    return "\n".join(L)
