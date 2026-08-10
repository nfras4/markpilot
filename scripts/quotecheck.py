#!/usr/bin/env python3
"""quotecheck.py - verify that quoted text actually appears in the document.

Stdlib only. No network.

    python quotecheck.py DOCUMENT --claims grades-round-2.md
    python quotecheck.py DOCUMENT --list

Two jobs.

--claims FILE
    Every quoted span in FILE must appear in DOCUMENT. Use it on grader output.
    The grader brief demands quoted evidence for every score - "a score with no
    quoted evidence is not a score; it is an impression" - but nothing checked
    that the quotes were real, and a grader that invents a supporting quote
    produces output byte-identical to one that did not. This is the only place in
    the pipeline that takes a language model's word for something, so it is the
    one place worth mechanising.

--list
    List the DOCUMENT's own direct quotations, so the source-checking step in
    Step 3d has something concrete to work through rather than a instruction to
    "spot-check every quote". It does not verify them against their sources -
    nothing here can - it just makes sure none is missed.

Exit codes:
    0  every quote checked was found
    1  at least one quote was NOT found in the document
    2  COULD NOT CHECK - nothing to compare
"""

import argparse
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doctext import load, die  # noqa: E402

# Straight and curly pairs, plus the guillemets and low-9 forms that turn up when
# a .docx round-trips through a PDF.
# NOTE the absence of ("'", "'"): a pair of straight apostrophes is not a
# quotation. Ordinary possessives ("the board's ... the regulator's") produced
# fabricated quotations at exit 0 on documents containing none, and in --claims
# mode produced a fabricated NOT FOUND that would have discarded a valid grading
# pass. Missing a straight-single-quoted quotation is the safer error.
QUOTE_PAIRS = [('"', '"'), ('“', '”'), ('‘', '’'), ('«', '»'), ('„', '“')]
MIN_WORDS = 4          # shorter spans are terms of art, not quotations
MAX_CHARS = 2000       # block quotes run long; see extract_quotes' skip counter


def canon(s):
    """Fold everything that varies between a quote and its source without
    changing the words: smart quotes, dashes, ligatures, spacing, case."""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[‘’‚‛']", "'", s)
    s = re.sub(r"[“”„‟\"]", '"', s)
    s = re.sub(r"[‐-―−-]", "-", s)
    s = re.sub(r"[ \s]+", " ", s)
    return s.strip().lower()


def extract_quotes(text):
    """Returns (quotes, skipped) - skipped is what was seen but not checked.

    A span longer than the cap used to match nothing at all, so it never entered
    the denominator: a fabricated 471-character quote made a run report
    "1/1 quoted spans appear" at exit 0. Anything dropped is now counted and
    reported, because a silent skip is the same failure as a silent pass."""
    out, skipped = [], 0
    for op, cl in QUOTE_PAIRS:
        body = r"([^" + re.escape(cl) + r"]{8,%d})" % MAX_CHARS
        for m in re.finditer(re.escape(op) + body + re.escape(cl), text):
            q = m.group(1).strip()
            if len(q.split()) >= MIN_WORDS:
                out.append(q)
            else:
                skipped += 1
        # spans that blew the cap entirely
        over = r"([^" + re.escape(cl) + r"]{%d,})" % (MAX_CHARS + 1)
        skipped += len(re.findall(re.escape(op) + over + re.escape(cl), text))
    # de-duplicate, preserve order
    seen, uniq = set(), []
    for q in out:
        k = canon(q)
        if k and k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq, skipped


def read_text(path):
    if path.lower().endswith(".pdf"):
        die("error: this script does not read PDF. Extract the text first "
            "(see the skill's Step 0).")
    if path.lower().endswith((".docx", ".md", ".txt", ".html", ".htm", ".rtf")):
        return "\n".join(p.text for p in load(path))
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("document")
    ap.add_argument("--claims", default="", help="file whose quotes must appear in DOCUMENT")
    ap.add_argument("--list", action="store_true", help="list the document's own quotations")
    args = ap.parse_args()

    if not os.path.exists(args.document):
        die(f"error: no such file: {args.document}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    doc = canon(read_text(args.document))
    if not doc:
        print("COULD NOT CHECK - the document produced no text.")
        return 2

    if args.list and args.claims:
        die("error: pass --claims or --list, not both - they answer different "
            "questions, and running one silently discards the other.")
    if args.list or not args.claims:
        quotes, skipped = extract_quotes(read_text(args.document))
        print(f"DIRECT QUOTATIONS  -  {len(quotes)} found")
        if not quotes:
            print("  None detected. If the document quotes sources, the parser did not")
            print("  see it - check by hand. This is not a finding that there are none.")
            return 2
        print("  Each must be checked against its source: exact wording, and a page")
        print("  number in the citation. Nothing here verifies that; it lists the work.\n")
        for i, q in enumerate(quotes, 1):
            print(f"  {i:>3}. \"{q[:100]}{'...' if len(q) > 100 else ''}\"")
        if skipped:
            print(f"\n  !! {skipped} quoted span(s) were too short or too long to check")
            print("     and are NOT in the count above. Look at those by hand.")
        print(f"\n  {len(quotes)} to verify. Record how many you checked in the report.")
        return 2 if skipped else 0

    if not os.path.exists(args.claims):
        die(f"error: no such claims file: {args.claims}")
    claims, skipped = extract_quotes(read_text(args.claims))
    print(f"QUOTED EVIDENCE  -  {len(claims)} quoted spans in {os.path.basename(args.claims)}")
    if not claims:
        print("  COULD NOT CHECK - no quoted spans found in the claims file.")
        print("  The grader brief requires quoted evidence for every score. If there")
        print("  is none, the scores are impressions and should be re-run, not trusted.")
        return 2
    print()

    missing = []
    for q in claims:
        if canon(q) not in doc:
            missing.append(q)

    for q in claims:
        mark = "NOT FOUND" if q in missing else "  ok  "
        print(f"  [{mark:^11}] \"{q[:88]}{'...' if len(q) > 88 else ''}\"")

    print(f"\n  {len(claims) - len(missing)}/{len(claims)} quoted spans appear in the document.")
    if skipped:
        print(f"  !! {skipped} further span(s) were too short or too long to check.")
        print("     They are NOT in the ratio above - a silently skipped span is the")
        print("     same failure as a silently passed one.")
    if missing:
        print(f"\n  {len(missing)} DO NOT APPEAR. A grader that quotes evidence which is not")
        print("  in the document has not read it carefully, and its scores cannot be")
        print("  relied on. Re-run that grading pass rather than acting on its findings.")
        print("  (Check first for an extraction problem - a quote spanning a table cell")
        print("  or a footnote may be real but unreachable in the extracted text.)")
        return 1
    return 2 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
