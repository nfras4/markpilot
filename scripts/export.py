#!/usr/bin/env python3
"""export.py - turn a markdown report into .docx and a print-ready .html.

Stdlib only. No pandoc, no LibreOffice, no pip install.

    python export.py report.md                 # writes report.docx AND report.pdf
    python export.py report.md --pdf
    python export.py report.md --all           # .docx + .pdf + .html
    python export.py report.md -o ~/Desktop/markpilot-report

No dependencies at all: the .docx is written directly as an OOXML package (a zip
of XML), and the .pdf is written directly too (see pdfwrite.py), using the
base-14 fonts every reader must provide so nothing needs embedding. The .html is
a print-friendly extra for anyone who would rather use a browser's own PDF
export, which does handle full Unicode.

Handles the subset markpilot's own outputs use: headings, paragraphs, bullet and
numbered lists, fenced code blocks, tables, block quotes, horizontal rules,
**bold**, *italic* and `code`.
"""

import argparse
import html as html_mod
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfwrite  # noqa: E402

W = "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\""


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ------------------------------------------------------------------ parsing

def parse(md):
    """-> list of blocks: (kind, payload). Deliberately small; this reads our own
    output, not arbitrary CommonMark."""
    blocks, lines, i = [], md.replace("\r\n", "\n").split("\n"), 0
    while i < len(lines):
        line = lines[i]
        t = line.strip()
        if not t:
            i += 1
            continue
        if t.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append(("code", buf))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", t)
        if m:
            blocks.append(("h" + str(len(m.group(1))), m.group(2)))
            i += 1
            continue
        if re.match(r"^([-*_])\1{2,}$", t):
            blocks.append(("hr", ""))
            i += 1
            continue
        if t.startswith("|") and i + 1 < len(lines) and re.match(
                r"^\|[\s:|-]+\|?$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in row):
                    rows.append(row)
                i += 1
            blocks.append(("table", rows))
            continue
        if re.match(r"^[-*+]\s+|^\d+[.)]\s+", t):
            items = []
            ordered = bool(re.match(r"^\d+[.)]\s+", t))
            while i < len(lines) and re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", lines[i]):
                items.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i]).strip())
                i += 1
            blocks.append(("ol" if ordered else "ul", items))
            continue
        if t.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip("> ").rstrip())
                i += 1
            blocks.append(("quote", " ".join(buf)))
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(?:#{1,6}\s|```|[-*+]\s|\d+[.)]\s|>|\|)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(buf)))
    return blocks


def inline(text):
    """-> list of (text, bold, italic, code) runs."""
    out, pos = [], 0
    pat = re.compile(r"\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|`([^`]+)`")
    for m in pat.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False, False, False))
        if m.group(1) is not None:
            out.append((m.group(1), True, False, False))
        elif m.group(2) is not None:
            out.append((m.group(2), False, True, False))
        else:
            out.append((m.group(3), False, False, True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False, False, False))
    return out or [(text, False, False, False)]


# -------------------------------------------------------------------- docx

def runs_xml(text, mono=False):
    parts = []
    for txt, b, it, code in inline(text):
        props = []
        if b:
            props.append("<w:b/>")
        if it:
            props.append("<w:i/>")
        if code or mono:
            props.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/>')
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        parts.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(txt)}</w:t></w:r>')
    return "".join(parts)


def para(text, style=None, mono=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{runs_xml(text, mono)}</w:p>"


def to_docx(blocks, path):
    body = []
    for kind, payload in blocks:
        if kind.startswith("h") and kind[1:].isdigit():
            body.append(para(payload, "Heading" + kind[1:]))
        elif kind == "p":
            body.append(para(payload))
        elif kind == "quote":
            body.append(para(payload, "Quote"))
        elif kind == "hr":
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                        'w:color="BBBBBB"/></w:pBdr></w:pPr></w:p>')
        elif kind == "code":
            for ln in payload:
                body.append(para(ln if ln.strip() else " ", "MPCode", mono=True))
        elif kind in ("ul", "ol"):
            for it in payload:
                body.append(para(("• " if kind == "ul" else "– ") + it, "MPList"))
        elif kind == "table":
            rows = []
            for r_i, row in enumerate(payload):
                cells = []
                for c in row:
                    cells.append(
                        "<w:tc><w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/></w:tcPr>"
                        + para(("**" + c + "**") if r_i == 0 else c) + "</w:tc>")
                rows.append("<w:tr>" + "".join(cells) + "</w:tr>")
            body.append(
                '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
                '<w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
                + "".join(f'<w:{s} w:val="single" w:sz="4" w:color="CCCCCC"/>'
                          for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
                + "</w:tblBorders></w:tblPr>" + "".join(rows) + "</w:tbl>")

    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<w:document {W}><w:body>{"".join(body)}'
           f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           f'<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
           f'</w:sectPr></w:body></w:document>')

    def style(sid, name, sz, bold=False, mono=False, color=None, before=160):
        rpr = ""
        if mono:
            rpr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
        if bold:
            rpr += "<w:b/>"
        if color:
            rpr += f'<w:color w:val="{color}"/>'
        rpr += f'<w:sz w:val="{sz}"/>'
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
                f'<w:pPr><w:spacing w:before="{before}" w:after="60"/></w:pPr>'
                f'<w:rPr>{rpr}</w:rPr></w:style>')

    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
              '<w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
              '</w:rPr></w:rPrDefault></w:docDefaults>'
              + style("Heading1", "heading 1", 32, bold=True, before=280)
              + style("Heading2", "heading 2", 26, bold=True, before=240)
              + style("Heading3", "heading 3", 23, bold=True)
              + style("Heading4", "heading 4", 22, bold=True)
              + style("Quote", "Quote", 22, color="555555")
              + style("MPCode", "Code", 18, mono=True, before=0)
              + style("MPList", "List", 22, before=40)
              + '</w:styles>')

    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", drels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", styles)


# -------------------------------------------------------------------- html

CSS = """
:root { --ink:#16181d; --dim:#5b6270; --line:#d8dce4; --bg:#fff; --code:#f4f6f9; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--ink); margin:0 auto; padding:32px 28px 64px;
  max-width:820px; font:15px/1.62 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
h1 { font-size:1.7rem; margin:0 0 .2em; letter-spacing:-.01em; }
h2 { font-size:1.22rem; margin:1.9em 0 .5em; padding-bottom:.28em; border-bottom:1px solid var(--line); }
h3 { font-size:1.04rem; margin:1.5em 0 .4em; }
h4 { font-size:.96rem; margin:1.3em 0 .3em; color:var(--dim); }
p, li { margin:.55em 0; }
ul, ol { padding-left:1.35em; }
hr { border:0; border-top:1px solid var(--line); margin:2em 0; }
blockquote { margin:1em 0; padding:.5em 0 .5em 1em; border-left:3px solid var(--line); color:var(--dim); }
code { background:var(--code); padding:.12em .34em; border-radius:3px;
  font:.87em/1.5 Consolas,"SF Mono",Menlo,monospace; }
pre { background:var(--code); border:1px solid var(--line); border-radius:6px;
  padding:14px 16px; overflow-x:auto; }
pre code { background:none; padding:0; font-size:.84em; line-height:1.5; }
table { border-collapse:collapse; width:100%; margin:1em 0; font-size:.93em; }
th, td { border:1px solid var(--line); padding:7px 10px; text-align:left; vertical-align:top; }
th { background:var(--code); font-weight:600; }
@media print {
  body { max-width:none; padding:0; font-size:11pt; }
  h2 { break-after:avoid; } pre, table, blockquote { break-inside:avoid; }
  a { color:inherit; text-decoration:none; }
}
@page { margin:18mm; }
"""

BANNER = """<div style="background:#f4f6f9;border:1px solid #d8dce4;border-radius:6px;
padding:10px 14px;margin:0 0 22px;font-size:.86rem;color:#5b6270">
To save as PDF: <strong>Ctrl+P</strong> (⌘P on a Mac) → Destination
<strong>Save as PDF</strong>. Margins and page breaks are already set.</div>"""


def il_html(text):
    out = []
    for txt, b, it, code in inline(text):
        t = html_mod.escape(txt)
        if code:
            t = f"<code>{t}</code>"
        if b:
            t = f"<strong>{t}</strong>"
        if it:
            t = f"<em>{t}</em>"
        out.append(t)
    return "".join(out)


def to_html(blocks, path, title):
    b = [BANNER]
    for kind, payload in blocks:
        if kind.startswith("h") and kind[1:].isdigit():
            b.append(f"<h{kind[1:]}>{il_html(payload)}</h{kind[1:]}>")
        elif kind == "p":
            b.append(f"<p>{il_html(payload)}</p>")
        elif kind == "quote":
            b.append(f"<blockquote>{il_html(payload)}</blockquote>")
        elif kind == "hr":
            b.append("<hr>")
        elif kind == "code":
            b.append("<pre><code>" + html_mod.escape("\n".join(payload)) + "</code></pre>")
        elif kind in ("ul", "ol"):
            tag = "ul" if kind == "ul" else "ol"
            b.append(f"<{tag}>" + "".join(f"<li>{il_html(i)}</li>" for i in payload) + f"</{tag}>")
        elif kind == "table":
            rows = []
            for i, row in enumerate(payload):
                cell = "th" if i == 0 else "td"
                rows.append("<tr>" + "".join(f"<{cell}>{il_html(c)}</{cell}>" for c in row) + "</tr>")
            b.append("<table>" + "".join(rows) + "</table>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                f"<title>{html_mod.escape(title)}</title><style>{CSS}</style></head>"
                f"<body>{''.join(b)}</body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown")
    ap.add_argument("-o", "--out", default="", help="output basename (no extension)")
    ap.add_argument("--docx", action="store_true", help="write .docx")
    ap.add_argument("--pdf", action="store_true", help="write .pdf")
    ap.add_argument("--html", action="store_true", help="write print-ready .html")
    ap.add_argument("--all", action="store_true", help="all three")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not os.path.exists(args.markdown):
        print(f"error: no such file: {args.markdown}", file=sys.stderr)
        return 2
    md = open(args.markdown, encoding="utf-8-sig").read()
    blocks = parse(md)
    base = args.out or os.path.splitext(args.markdown)[0]
    title = next((p for k, p in blocks if k == "h1"), os.path.basename(base))

    want_docx = args.docx or args.all
    want_pdf = args.pdf or args.all
    want_html = args.html or args.all
    if not (want_docx or want_pdf or want_html):
        want_docx = want_pdf = True          # no flags: both real formats

    made = []
    if want_docx:
        to_docx(blocks, base + ".docx")
        made.append(base + ".docx")
    if want_pdf:
        pages = pdfwrite.write(blocks, base + ".pdf", title)
        made.append(f"{base}.pdf ({pages} page{'s' if pages != 1 else ''})")
    if want_html:
        to_html(blocks, base + ".html", title)
        made.append(base + ".html")

    for m in made:
        path = m.split(" (")[0]
        print(f"  wrote {m}  [{os.path.getsize(path):,} bytes]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
