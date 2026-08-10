#!/usr/bin/env python3
"""pdfwrite.py - write a real PDF, with no dependencies.

Used by export.py. Uses the base-14 fonts (Helvetica, Helvetica-Bold, Courier)
that every PDF reader is required to provide, so nothing has to be embedded --
which is what makes a dependency-free PDF possible at all.

"Open the HTML and press Ctrl+P" is not a PDF. This produces a .pdf file.
"""

import io
import re

# Helvetica advance widths, units per 1000, for ASCII 32..126. Line breaking needs
# the real widths: an averaged guess overruns the right margin on any line with
# several wide characters, and under-fills every line without them.
HELV_W = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]

# Characters WinAnsi base-14 cannot render. Substituted, never dropped: a missing
# en dash is a typo, but a page of black diamonds is a bug report.
SUBS = {
    "—": "--", "–": "-", "‘": "'", "’": "'", "“": '"',
    "”": '"', "…": "...", " ": " ", "→": "->", "←": "<-",
    "•": "*", "·": "-", "─": "-", "│": "|", "★": "*",
    "☆": "o", "✓": "y", "✗": "x", "×": "x", "≥": ">=",
    "≤": "<=", "≠": "!=", "±": "+/-", "‑": "-", "é": "e",
    "−": "-", "▸": ">", "➔": "->", "‹": "<", "›": ">",
}
INLINE = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|\*(.+?)\*")


def flatten(s):
    return INLINE.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or "", s)


def sanitise(s):
    for k, v in SUBS.items():
        s = s.replace(k, v)
    return "".join(c if 32 <= ord(c) <= 126 else "?" for c in s)


def width(s, size, mono=False, bold=False):
    if mono:
        return len(s) * size * 0.6                       # Courier is monospace
    total = sum(HELV_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in s)
    return total / 1000.0 * size * (1.06 if bold else 1.0)


def wrap(s, size, avail, mono=False, bold=False):
    out, cur = [], ""
    for w in s.split(" "):
        trial = w if not cur else cur + " " + w
        if width(trial, size, mono, bold) <= avail or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w
    out.append(cur)
    return out or [""]


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write(blocks, path, title="report"):
    PW, PH, M = 595.28, 841.89, 51.0          # A4, ~18mm margins
    avail = PW - 2 * M
    pages, cur = [], []
    y = [PH - M]

    def newpage():
        pages.append(cur[:])
        cur.clear()
        y[0] = PH - M

    def emit(txt, size, font, indent=0.0, before=0.0, after=3.0):
        mono, bold = font == "F3", font == "F2"
        y[0] -= before
        for ln in wrap(sanitise(txt), size, avail - indent, mono, bold):
            if y[0] - size < M:
                newpage()
            y[0] -= size * 1.32
            cur.append(f"BT /{font} {size:.1f} Tf 1 0 0 1 {M + indent:.1f} "
                       f"{y[0]:.1f} Tm ({esc(ln)}) Tj ET")
        y[0] -= after

    for kind, payload in blocks:
        if kind == "h1":
            emit(flatten(payload), 17, "F2", before=6, after=8)
        elif kind == "h2":
            emit(flatten(payload), 13, "F2", before=14, after=4)
        elif kind in ("h3", "h4", "h5", "h6"):
            emit(flatten(payload), 11.5, "F2", before=10, after=3)
        elif kind == "p":
            emit(flatten(payload), 10, "F1")
        elif kind == "quote":
            emit(flatten(payload), 10, "F1", indent=16)
        elif kind == "hr":
            y[0] -= 5
            cur.append(f"0.82 G 0.6 w {M} {y[0]:.1f} m {PW - M} {y[0]:.1f} l S 0 G")
            y[0] -= 9
        elif kind == "code":
            for ln in payload:
                emit(ln if ln.strip() else " ", 8, "F3", after=0)
            y[0] -= 6
        elif kind in ("ul", "ol"):
            for n, it in enumerate(payload, 1):
                emit(("* " if kind == "ul" else f"{n}. ") + flatten(it),
                     10, "F1", indent=12, after=1)
            y[0] -= 4
        elif kind == "table":
            if not payload:
                continue
            cols = max(len(r) for r in payload)
            cw = avail / cols
            for r_i, row in enumerate(payload):
                fnt = "F2" if r_i == 0 else "F1"
                cells = [wrap(sanitise(flatten(c)), 9, cw - 6, False, r_i == 0)
                         for c in row]
                need = max(len(c) for c in cells) * 11.5 + 5
                if y[0] - need < M:
                    newpage()
                top = y[0]
                for i, lines in enumerate(cells):
                    yy = top
                    for ln in lines:
                        yy -= 11.5
                        cur.append(f"BT /{fnt} 9 Tf 1 0 0 1 {M + i * cw + 3:.1f} "
                                   f"{yy:.1f} Tm ({esc(ln)}) Tj ET")
                y[0] = top - need
                cur.append(f"0.85 G 0.5 w {M} {y[0] + 3:.1f} m {PW - M} "
                           f"{y[0] + 3:.1f} l S 0 G")
            y[0] -= 7
    pages.append(cur[:])

    n = len(pages)
    content0 = 7                       # 1 catalog, 2 pages, 3 spare, 4-6 fonts
    page0 = content0 + n
    objs = {}
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page0 + i} 0 R" for i in range(n))
    objs[2] = f"<< /Type /Pages /Count {n} /Kids [{kids}] >>".encode()
    objs[3] = b"<< >>"
    for num, base in ((4, "Helvetica"), (5, "Helvetica-Bold"), (6, "Courier")):
        objs[num] = (f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                     f"/Encoding /WinAnsiEncoding >>").encode()
    for i, ops in enumerate(pages):
        st = "\n".join(ops).encode("latin-1", "replace")
        objs[content0 + i] = (b"<< /Length " + str(len(st)).encode() + b" >>\nstream\n"
                              + st + b"\nendstream")
        objs[page0 + i] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW:.2f} {PH:.2f}] "
            f"/Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> "
            f"/Contents {content0 + i} 0 R >>").encode()

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = buf.tell()
        buf.write(f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n")
    xref = buf.tell()
    top = max(objs) + 1
    buf.write(f"xref\n0 {top}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for i in range(1, top):
        buf.write(f"{offsets.get(i, 0):010d} 00000 n \n".encode())
    buf.write((f"trailer\n<< /Size {top} /Root 1 0 R /Info << "
               f"/Title ({esc(sanitise(title))}) /Producer (markpilot) >> >>\n"
               f"startxref\n{xref}\n%%EOF\n").encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return n
