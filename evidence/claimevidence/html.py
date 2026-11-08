from __future__ import annotations

import html
import re

CSS = """
@page { size: Letter; margin: 0.7in 0.6in 0.8in; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 9pt system-ui, sans-serif; color: #555; } }
:root { color-scheme: light; }
body { font: 10.5pt/1.45 Georgia, 'Times New Roman', serif; color: #111; background: #fff; max-width: 8.5in; margin: 0 auto; padding: 24px; }
h1 { font: 600 18pt/1.25 system-ui, sans-serif; margin: 0 0 6px; }
h2 { font: 600 12.5pt/1.3 system-ui, sans-serif; margin: 22px 0 8px; padding-top: 6px; border-top: 1.5px solid #222; }
h2.exhibit { break-before: page; }
p, li { margin: 4px 0; overflow-wrap: anywhere; }
a { overflow-wrap: anywhere; word-break: break-all; }
blockquote { margin: 10px 0; padding: 8px 12px; border-left: 4px solid #b45309; background: #fff7ed; font: 9.5pt/1.4 system-ui, sans-serif; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font: 8.5pt/1.3 system-ui, sans-serif; }
th, td { border: 1px solid #bbb; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background: #f1f1f1; }
td:not(:first-child) { font-variant-numeric: tabular-nums; }
code { font: 8.5pt ui-monospace, Menlo, monospace; }
em { color: #555; }
.foot { margin-top: 18px; font: 8.5pt system-ui, sans-serif; color: #555; }
@media print { body { padding: 0; } a { color: inherit; text-decoration: none; } }
"""


def _inline(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])_(.+?)_(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"(https://[^\s<]+)", r'<a href="\1">\1</a>', t)
    return t


def to_html(md: str, title: str) -> str:
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{_inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            cls = ' class="exhibit"' if ln[3:].startswith("Exhibit") else ""
            out.append(f"<h2{cls}>{_inline(ln[3:])}</h2>")
        elif ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>")
            continue
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows if not re.match(r"^\|[\s\-:|]+\|$", r)]
            if cells:
                head, body = cells[0], cells[1:]
                out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                           + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        elif ln.startswith("- "):
            buf = []
            while i < len(lines) and lines[i].startswith("- "):
                buf.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue
        elif ln.strip().startswith("_") and ln.strip().endswith("_"):
            out.append(f'<p class="foot">{_inline(ln.strip()[1:-1])}</p>')
        elif ln.strip():
            out.append(f"<p>{_inline(ln)}</p>")
        i += 1
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>" + "\n".join(out) + "</body></html>\n")
