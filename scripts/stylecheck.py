#!/usr/bin/env python3
"""stylecheck.py - document styling, template use, and required sections.

    python stylecheck.py FILE
    python stylecheck.py FILE --require "Executive Summary,Literature Review,References"
    python stylecheck.py FILE --font "Times New Roman" --size 12 --spacing 2.0
    python stylecheck.py FILE --json out.json

Exit codes:
    0  consistent, and every required section found
    1  problems found
    2  COULD NOT CHECK - unreadable, or not a .docx

WHY THIS EXISTS
---------------
Rubrics score this directly. The one this was built against gives 5% to Mechanics and
Professionalism, whose top band reads "It is clearly structured using the provided
template" - so whether Word's heading styles were used is worth marks on its own,
independently of anything the prose says.

It is also the one class of defect the author cannot see. A document where every
heading is hand-bolded 14pt text looks identical on screen to one built on Heading 1,
and reads as identical in extracted text, so no other check in this skill can tell
them apart. The difference shows up in the navigation pane, the table of contents, and
in a marker's impression of whether the template was followed.

WHAT IT DOES NOT DO
-------------------
It reports; it does not restyle. Applying styles means rewriting paragraph properties
across a whole document, which is a different and much riskier operation than the
text substitution `docxpatch.py` performs, and it is not worth the chance of mangling
somebody's submission to save them ten minutes in the Styles pane.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

def ensure_parent(path):
    """Create the directory an output file is about to be written into.

    The skill's own first prescribed command writes `.markpilot/inputs.json` into a
    directory nothing had created, which raised an uncaught FileNotFoundError while
    the process still exited 0 - a caller gating on the exit code saw success and got
    no file. Every script that accepts an output path creates its parent."""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    return path


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEADING_STYLE = re.compile(r"^(heading|title|subtitle)", re.I)


def part(z, name):
    try:
        return z.read(name)
    except KeyError:
        return None


def para_text(p):
    return "".join(n.text or "" for n in p.iter() if n.tag == f"{W}t").strip()


def para_style(p):
    ppr = p.find(f"{W}pPr")
    if ppr is None:
        return ""
    st = ppr.find(f"{W}pStyle")
    return (st.get(f"{W}val", "") or "") if st is not None else ""


def is_bold(p):
    """True when every run carrying text is bold. A partially bold paragraph is
    emphasis inside a sentence, not a heading pretending to be one."""
    runs = [r for r in p.iter(f"{W}r") if any(t.text for t in r.iter(f"{W}t"))]
    if not runs:
        return False
    for r in runs:
        rpr = r.find(f"{W}rPr")
        if rpr is None or rpr.find(f"{W}b") is None:
            return False
    return True


def collect(z):
    xml = part(z, "word/document.xml")
    if xml is None:
        return None, "no word/document.xml"
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return None, f"document.xml is not well-formed ({e})"

    fonts, sizes, spacings, paras = Counter(), Counter(), Counter(), []
    table_sizes = Counter()

    # Walk in document order tracking table membership. Using root.iter() instead
    # reported a bold table header cell and a bold p-value ("Pass", ".004") as
    # hand-formatted headings, and folded 9pt table text into the body size spread -
    # two false positives on the first real document, both from the same cause.
    ordered = []

    def walk(node, in_table):
        for child in node:
            if child.tag == f"{W}tbl":
                walk(child, True)
            elif child.tag == f"{W}p":
                ordered.append((child, in_table))
            elif len(child):
                walk(child, in_table)

    body = root.find(f"{W}body")
    walk(body if body is not None else root, False)

    for p, in_table in ordered:
        text = para_text(p)
        style = para_style(p)
        ppr = p.find(f"{W}pPr")
        if ppr is not None:
            sp = ppr.find(f"{W}spacing")
            if sp is not None and sp.get(f"{W}line"):
                try:
                    spacings[round(int(sp.get(f"{W}line")) / 240, 2)] += 1
                except ValueError:
                    pass
        for r in p.iter(f"{W}r"):
            if not any(t.text for t in r.iter(f"{W}t")):
                continue
            rpr = r.find(f"{W}rPr")
            if rpr is None:
                continue
            rf = rpr.find(f"{W}rFonts")
            if rf is not None:
                name = rf.get(f"{W}ascii") or rf.get(f"{W}hAnsi")
                if name:
                    fonts[name] += 1
            sz = rpr.find(f"{W}sz")
            if sz is not None and sz.get(f"{W}val"):
                try:
                    val = int(sz.get(f"{W}val")) / 2
                    # Headings are meant to differ in size; counting them as
                    # inconsistency flags every correctly-styled document.
                    if in_table:
                        table_sizes[val] += 1
                    elif not HEADING_STYLE.match(style):
                        sizes[val] += 1
                except ValueError:
                    pass
        if text:
            paras.append({"text": text, "style": style, "bold": is_bold(p),
                          "words": len(text.split()), "in_table": in_table})

    margins = {}
    for sect in root.iter(f"{W}sectPr"):
        pg = sect.find(f"{W}pgMar")
        if pg is not None:
            for side in ("top", "right", "bottom", "left"):
                v = pg.get(f"{W}{side}")
                if v:
                    try:                       # twentieths of a point -> cm
                        margins[side] = round(int(v) / 1440 * 2.54, 2)
                    except ValueError:
                        pass
            break
    return {"fonts": fonts, "sizes": sizes, "table_sizes": table_sizes,
            "spacings": spacings, "paras": paras, "margins": margins}, None


def analyse(d, want_font=None, want_size=None, want_spacing=None, require=()):
    problems, notes = [], []
    paras = d["paras"]

    styled = [p for p in paras if HEADING_STYLE.match(p["style"])]
    # A short, fully bold, unstyled paragraph immediately followed by body text is a
    # heading someone typed rather than applied.
    manual = []
    for i, p in enumerate(paras):
        if p.get("in_table"):
            continue          # a bold header cell is not a heading
        if HEADING_STYLE.match(p["style"]) or not p["bold"] or p["words"] > 12:
            continue
        nxt = paras[i + 1] if i + 1 < len(paras) else None
        if nxt and not nxt["bold"] and nxt["words"] > 12:
            manual.append(p["text"][:60])

    if not styled and manual:
        problems.append(
            f"No Word heading styles are used anywhere, but {len(manual)} paragraphs "
            f"are formatted to look like headings. A rubric that scores use of the "
            f"provided template reads this as the template not being used")
    elif manual:
        problems.append(
            f"{len(manual)} heading(s) are hand-formatted rather than styled, so they "
            f"will not appear in the navigation pane or a generated contents page: "
            + "; ".join(manual[:3]) + ("; ..." if len(manual) > 3 else ""))

    if len(d["fonts"]) > 2:
        top = ", ".join(f"{k} ({v})" for k, v in d["fonts"].most_common(4))
        problems.append(f"{len(d['fonts'])} different fonts in the body text: {top}")
    if len(d["sizes"]) > 3:
        top = ", ".join(f"{k}pt ({v})" for k, v in d["sizes"].most_common(5))
        problems.append(f"{len(d['sizes'])} different font sizes: {top}")

    if want_font and d["fonts"]:
        main = d["fonts"].most_common(1)[0][0]
        if main.lower() != want_font.lower():
            problems.append(f"Body font is {main}; the task sheet asks for {want_font}")
    if want_size and d["sizes"]:
        main = d["sizes"].most_common(1)[0][0]
        if abs(main - want_size) > 0.01:
            problems.append(f"Body size is {main}pt; the task sheet asks for {want_size}pt")
    if want_spacing and d["spacings"]:
        main = d["spacings"].most_common(1)[0][0]
        if abs(main - want_spacing) > 0.06:
            problems.append(
                f"Dominant line spacing is {main}; the task sheet asks for {want_spacing}")

    lowered = [p["text"].lower() for p in paras]
    for name in require:
        name = name.strip()
        if not name:
            continue
        if not any(t.startswith(name.lower()) or name.lower() in t[:80]
                   for t in lowered):
            problems.append(f"Required section not found: \"{name}\"")
        else:
            notes.append(f"required section present: {name}")
    return problems, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--require", default="", help="comma-separated required section names")
    ap.add_argument("--font")
    ap.add_argument("--size", type=float)
    ap.add_argument("--spacing", type=float)
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.file.lower().endswith(".docx"):
        print("COULD NOT CHECK - stylecheck reads .docx only; styling does not survive "
              "text extraction", file=sys.stderr)
        return 2
    try:
        with zipfile.ZipFile(args.file) as z:
            d, err = collect(z)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"COULD NOT CHECK - {args.file} ({type(e).__name__})", file=sys.stderr)
        return 2
    if err:
        print(f"COULD NOT CHECK - {err}", file=sys.stderr)
        return 2

    problems, notes = analyse(
        d, args.font, args.size, args.spacing,
        [s for s in args.require.split(",") if s.strip()])

    print("STYLE AND TEMPLATE\n")
    print(f"  Fonts        {', '.join(f'{k} ({v})' for k, v in d['fonts'].most_common(4)) or 'none declared (all inherited from the default style)'}")
    print(f"  Sizes        {', '.join(f'{k}pt ({v})' for k, v in d['sizes'].most_common(4)) or 'all inherited'}   (body prose only)")
    if d["table_sizes"]:
        print(f"  In tables    {', '.join(f'{k}pt ({v})' for k, v in d['table_sizes'].most_common(3))}   (not counted above)")
    print(f"  Line spacing {', '.join(f'{k} ({v})' for k, v in d['spacings'].most_common(3)) or 'all inherited'}")
    if d["margins"]:
        print("  Margins      " + ", ".join(f"{k} {v}cm" for k, v in d["margins"].items()))
    styled = sum(1 for p in d["paras"] if HEADING_STYLE.match(p["style"]))
    print(f"  Headings     {styled} paragraph(s) use a Word heading style")

    if problems:
        print(f"\n  PROBLEMS ({len(problems)})")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  OK - consistent, and every required section was found")

    if args.json_out:
        with open(ensure_parent(args.json_out), "w", encoding="utf-8") as f:
            json.dump({"fonts": dict(d["fonts"]), "sizes": dict(d["sizes"]),
                       "spacings": {str(k): v for k, v in d["spacings"].items()},
                       "margins": d["margins"], "problems": problems,
                       "styled_headings": styled}, f, indent=2)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
