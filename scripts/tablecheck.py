#!/usr/bin/env python3
"""tablecheck.py - table numbering, captions, cross-references and structure.

    python tablecheck.py FILE
    python tablecheck.py FILE --style apa7      caption ABOVE (default)
    python tablecheck.py FILE --caption-below   for styles that put it below
    python tablecheck.py FILE --json out.json

Exit codes:
    0  tables found and clean
    1  tables found with problems
    2  COULD NOT CHECK - unreadable, or no tables detected at all

WHY A SEPARATE SCRIPT
---------------------
`figcheck.py` reads captions as text, which is enough for figures because a figure is
an image with a caption near it. A table is a real structure in the file, and the
things that lose marks about it are structural: a caption that sits below when the
style wants it above, a row with fewer cells than the header, a numbering sequence
that skips because a table was deleted, and a table the prose never refers to.

None of that is visible in extracted text. `doctext.py` flattens a table to its cell
text in document order, so a ragged row and a complete one read identically.

THE CAPTION RULE IS NOT A DETAIL
--------------------------------
APA 7, Harvard and Chicago all put the table caption ABOVE the table and the figure
caption BELOW it. Getting it backwards is one of the cheapest marks to lose in a
rubric that scores presentation, and it is invisible to anyone reading their own
document, because it looks deliberate either way.
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

TABLE_CAPTION = re.compile(r"^\s*table\s+(\d+)\s*[.:—–-]?\s*(.*)$", re.I)
TABLE_REF = re.compile(r"\btable\s+(\d+)\b", re.I)


def para_text(p):
    parts = []
    for node in p.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
            parts.append(" ")
    return "".join(parts).strip()


def read_body(path):
    """(body_element, error). Never raises on a bad file - the caller reports exit 2."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        return None, f"{path} could not be read ({type(e).__name__})"
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return None, f"word/document.xml is not well-formed ({e})"
    body = root.find(f"{W}body")
    return (body if body is not None else root), None


def scan(body):
    """Walk the body in document order, recording paragraphs and tables as a flat
    sequence, so 'what sits immediately above this table' is answerable."""
    seq = []

    def walk(node, depth):
        for child in node:
            if child.tag == f"{W}tbl":
                rows = []
                for tr in child.iter(f"{W}tr"):
                    cells = []
                    for tc in tr.findall(f"{W}tc"):
                        cells.append(" ".join(
                            para_text(p) for p in tc.findall(f"{W}p")).strip())
                    rows.append(cells)
                seq.append({"kind": "table", "rows": rows, "depth": depth})
                # A nested table is a layout device, not a data table; do not recurse.
            elif child.tag == f"{W}p":
                seq.append({"kind": "para", "text": para_text(child)})
            elif len(child):
                walk(child, depth)

    walk(body, 0)
    return seq


def analyse(seq, caption_above=True):
    tables, problems = [], []
    body_text = " ".join(s["text"] for s in seq if s["kind"] == "para")

    # Captions, wherever they are, and which table they sit next to.
    caption_idx = {}
    for i, item in enumerate(seq):
        if item["kind"] != "para":
            continue
        m = TABLE_CAPTION.match(item["text"])
        if m and item["text"]:
            caption_idx[i] = int(m.group(1))

    t_positions = [i for i, s in enumerate(seq) if s["kind"] == "table"]
    for n, i in enumerate(t_positions, start=1):
        rows = seq[i]["rows"]
        # Nearest caption directly above / below, skipping blank paragraphs.
        above = below = None
        j = i - 1
        while j >= 0 and seq[j]["kind"] == "para" and not seq[j]["text"]:
            j -= 1
        if j >= 0 and j in caption_idx:
            above = caption_idx[j]
        k = i + 1
        while k < len(seq) and seq[k]["kind"] == "para" and not seq[k]["text"]:
            k += 1
        if k < len(seq) and k in caption_idx:
            below = caption_idx[k]

        # What the table actually sits under, so an uncaptioned one is locatable.
        heading = ""
        j2 = i - 1
        while j2 >= 0 and seq[j2]["kind"] == "para":
            if seq[j2]["text"]:
                heading = seq[j2]["text"][:60]
                break
            j2 -= 1

        widths = [len(r) for r in rows]
        empty_rows = sum(1 for r in rows if not any(c.strip() for c in r))
        tables.append({
            "index": n, "rows": len(rows),
            "cols": max(widths) if widths else 0,
            "caption_above": above, "caption_below": below,
            "ragged": len(set(widths)) > 1 if widths else False,
            "empty_rows": empty_rows, "under": heading,
        })

    uncaptioned = [t for t in tables
                   if t["caption_above"] is None and t["caption_below"] is None]
    if len(uncaptioned) == len(tables) and tables:
        # Every table unlabelled is one finding, not N. Repeating it per table buries
        # the diagnosis, which is that the document is using section headings where
        # the style wants numbered table captions.
        problems.append(
            f"NONE of the {len(tables)} tables carries a numbered caption. Each sits "
            f"directly under a section heading instead. APA 7 wants 'Table N' on its "
            f"own line above the table, with an italic title beneath it, and a rubric "
            f"scoring appendices or presentation reads unnumbered tables as incomplete")
    elif uncaptioned:
        for t in uncaptioned:
            problems.append(
                f"The table under \"{t['under']}\" has no numbered caption")

    for t in tables:
        num = t["caption_above"] if t["caption_above"] is not None else t["caption_below"]
        where = "above" if t["caption_above"] is not None else (
            "below" if t["caption_below"] is not None else None)
        if where is None:
            pass                                    # already reported, once, above
        elif caption_above and where == "below":
            problems.append(
                f"Table {num} caption is BELOW the table - APA 7, Harvard and Chicago "
                f"all put table captions above")
        elif not caption_above and where == "above":
            problems.append(f"Table {num} caption is ABOVE the table - this style wants below")
        if t["ragged"]:
            problems.append(
                f"Table {num or t['index']} has rows of differing cell counts "
                f"({t['rows']} rows, widest {t['cols']}) - a merged or missing cell")
        if t["empty_rows"]:
            problems.append(
                f"Table {num or t['index']} has {t['empty_rows']} completely empty row(s)")

    numbers = [t["caption_above"] or t["caption_below"] for t in tables]
    numbers = [n for n in numbers if n]
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"Table numbering is not sequential: {numbers}")

    # Cross-references. A caption line mentioning "Table 3" is not a reference to it.
    caption_lines = {i for i in caption_idx}
    prose = " ".join(s["text"] for i, s in enumerate(seq)
                     if s["kind"] == "para" and i not in caption_lines)
    referred = {int(m) for m in TABLE_REF.findall(prose)}
    for n in numbers:
        if n not in referred:
            problems.append(
                f"Table {n} is never referred to in the body text - a table the prose "
                f"never mentions reads as padding")
    return tables, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--style", default="apa7")
    ap.add_argument("--caption-below", action="store_true",
                    help="this style puts table captions below")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.file.lower().endswith(".docx"):
        print("COULD NOT CHECK - tablecheck reads .docx only (a table is a structure, "
              "not text)", file=sys.stderr)
        return 2

    body, err = read_body(args.file)
    if err:
        print(f"COULD NOT CHECK - {err}", file=sys.stderr)
        return 2

    seq = scan(body)
    tables, problems = analyse(seq, caption_above=not args.caption_below)

    print("TABLES\n")
    if not tables:
        print("  COULD NOT CHECK - no tables found in this document.")
        print("  That is a pass only if the document is meant to have none.")
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump({"tables": [], "problems": []}, f, indent=2)
        return 2

    for t in tables:
        num = t["caption_above"] or t["caption_below"]
        label = f"Table {num}" if num else f"(untitled #{t['index']})"
        pos = ("caption above" if t["caption_above"] else
               "caption below" if t["caption_below"] else "no caption")
        under = f'  under "{t["under"]}"' if t["under"] else ""
        print(f"  {label}: {t['rows']} rows x {t['cols']} cols, {pos}{under}")
    if problems:
        print(f"\n  PROBLEMS ({len(problems)})")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  OK - numbered, captioned, cross-referenced, no ragged rows")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"tables": tables, "problems": problems}, f, indent=2)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
