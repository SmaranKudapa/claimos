from __future__ import annotations

import html as H
from pathlib import Path


def _esc(t) -> str:
    return H.escape(str(t), quote=False)


INDEX_HEAD = ["Exhibit", "Description", "Date", "Source", "Page", "Supports"]


def _index_rows(doc, pages):
    return [[e["id"], e["description"], e["date"], e["source"], str((pages or {}).get(e["key"], "-")), e["supports"]] for e in doc.exhibits]


CSS = """
@page { size: Letter; margin: 0.9in 1in 0.85in 1in; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt Helvetica, Arial, sans-serif; } }
body { font-family: "Times New Roman", Times, serif; font-size: 11pt; line-height: 1.35; color: #111; max-width: 7.2in; margin: 0 auto; padding: 16px; }
h1.t { font: bold 17pt Helvetica, Arial, sans-serif; margin: 0 0 4px; }
.sub { font: 10pt Helvetica, Arial, sans-serif; color: #333; margin-bottom: 12px; }
h2 { font: bold 13pt Helvetica, Arial, sans-serif; margin: 18px 0 6px; }
h2.ex { margin-top: 22px; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 10px; font: 8.5pt Helvetica, Arial, sans-serif; }
thead { display: table-header-group; }
th, td { border: 0.5pt solid #808080; padding: 2px 4px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #e6e6e6; }
.note { border: 0.6pt solid #666; padding: 6px 8px; font-size: 10pt; }
.pb { break-after: page; }
img { max-width: 100%; }
@media screen { body { background: #fff; } .wrap { overflow-x: auto; } }
"""


def to_html(doc: Doc, title: str, pages: dict | None = None) -> str:
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
           f"<title>{_esc(title)}</title><style>{CSS}</style></head><body>"]

    def tab(head, rows):
        r = ["<div class='wrap'><table><thead><tr>" + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr></thead><tbody>"]
        r += ["<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows]
        return "".join(r) + "</tbody></table></div>"

    for b in doc.blocks:
        k = b[0]
        if k == "title":
            out.append(f"<h1 class='t'>{_esc(b[1])}</h1>")
        elif k == "subtitle":
            out.append(f"<div class='sub'>{_esc(b[1])}</div>")
        elif k == "meta":
            out.append(tab(["Item", "Detail"], [[a, v] for a, v in b[1]]))
        elif k == "note":
            out.append(f"<p class='note'>{_esc(b[1])}</p>")
        elif k == "h1":
            out.append(f"<h2>{_esc(b[1])}</h2>")
        elif k == "p":
            out.append(f"<p>{_esc(b[1])}</p>")
        elif k == "bullets":
            out.append("<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in b[1]) + "</ul>")
        elif k == "table":
            out.append(tab(b[1], b[2]))
        elif k == "index":
            out.append(tab(INDEX_HEAD, _index_rows(doc, pages or {e["key"]: e.get("page") or "-" for e in doc.exhibits})))
        elif k == "pagebreak":
            out.append("<div class='pb'></div>")
        elif k == "exhibit":
            out.append(f"<h2 class='ex' id='{_esc(b[1])}'>{_esc(b[2])}: {_esc(b[3])}</h2>")
        elif k == "image":
            out.append(f"<figure><img src='{_esc(Path(b[1]).name)}' alt='{_esc(b[2])}'><figcaption>{_esc(b[2])}</figcaption></figure>")
    out.append("</body></html>")
    return "\n".join(out)


