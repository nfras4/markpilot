#!/usr/bin/env python3
"""doctext.py - extract text and count words from an assignment document.

Stdlib only. No pip install, no uv --with. Runs on any Python 3.8+.

Supported inputs: .docx, .md, .txt, .rtf (crude), .html/.htm
For .pdf, use the Read tool instead - this script deliberately does not
guess at PDF text extraction.

Usage:
  python doctext.py FILE --text                    # dump plain text to stdout
  python doctext.py FILE --outline                 # headings only, with word counts
  python doctext.py FILE --count [exclusions...]   # word count report

Exclusion flags (compose them to match the task sheet's stated rule):
  --exclude-refs        drop everything from the References/Bibliography heading on
  --exclude-appendix    drop everything from the first Appendix heading on
  --exclude-headings    drop heading paragraphs themselves
  --exclude-intext      drop parenthetical in-text citations, e.g. (Smith, 2020, p. 4)
  --exclude-tables      drop text inside tables (docx only)
  --exclude-quotes      drop block quotes (docx: Quote/IntenseQuote styles; md: > lines)
  --exclude-captions    drop Figure N / Table N caption paragraphs
  --exclude-footnotes   drop footnote and endnote text (docx)

Always report the UNEXCLUDED total alongside the excluded one. Markers report
what each flag removed so the number is auditable rather than asserted, and a
flag that removed NOTHING is reported too - a silent no-op on a manually
formatted document is how a word count ends up wrong in the safe-looking
direction.
"""

import argparse
import html
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

HEADING_RE = re.compile(r"^(heading|title|subtitle)", re.I)

# Section headings are matched WITH any numbering a student may have applied:
# "6. References", "Chapter 6: References", "6 References", "APPENDIX A".
# Requiring a bare "References" (the obvious spelling of this regex) means the
# reference list is silently counted as body text and --exclude-refs removes
# nothing at all, with no error.
_NUM = r"(?:(?:chapter|section|part)\s+)?(?:[0-9]+(?:\.[0-9]+)*\s*[.):]?\s+)?"
REFS_RE = re.compile(
    r"^\s*" + _NUM + r"(references?|reference\s+list|bibliography|works\s+cited|"
    r"source\s+list|list\s+of\s+references)\s*:?\s*$", re.I)
APPENDIX_RE = re.compile(r"^\s*" + _NUM + r"(appendix|appendices|annexure|annex)\b", re.I)

CAPTION_RE = re.compile(
    r"^\s*(figure|fig\.?|table|chart|exhibit|graph)\s*([A-Z]?\d+(?:\.\d+)*)\s*"
    r"([.:—–-])?\s*(.*)$", re.I)

# A paragraph opening "Table 3 shows that..." is PROSE that mentions the table,
# not the table's caption. Stems need \w* rather than \b - "summaris\b" cannot
# match "summarises" because there is no word boundary mid-word.
#
# Every stem here must be followed by something that makes it a VERB. Bare
# prefixes match the opening noun of ordinary captions - "Comparison of revenue"
# starts with "compar", "Detailed breakdown" with "detail", "Reported scores"
# with "report" - and those are real captions, not prose.
_PROSE_VERBS = (r"shows?|showed|presents?|presented|summarises?|summarizes?|summarised|"
                r"summarized|illustrates?|illustrated|reports?|reported|displays?|"
                r"displayed|indicates?|indicated|provides?|provided|gives?|given|"
                r"compares?|compared|lists?|listed|outlines?|outlined|details?|detailed|"
                r"highlights?|highlighted|demonstrates?|demonstrated|confirms?|confirmed|"
                r"suggests?|suggested|contains?|contained|reveals?|revealed|sets? out|"
                r"plots?|plotted|maps?|mapped|breaks? down|records?|recorded")
PROSE_OPENER = re.compile(
    r"(?i)^(?:and\s|below\b|above\b|overleaf\b|opposite\b|in\s+(?:the\s+)?appendix\b|"
    r"(?:" + _PROSE_VERBS + r")(?:\s|$))")


def is_caption_line(text):
    """(is_caption, kind, number, caption_text) for a paragraph.

    The discriminator between a caption and prose that opens by naming a figure is
    the SEPARATOR after the number, not the word that follows it:

        "Figure 2. Reported satisfaction scores"   caption  (separator present)
        "Table 3 reports the coefficients."        prose    (no separator, verb)

    Testing the following word alone cannot tell those apart - "Reported",
    "Detailed", "Comparison" and "Listed" all open perfectly ordinary captions
    while also being verb stems. Getting this backwards is expensive twice over:
    the caption's text is stolen, and the figure loses the only cross-reference it
    had, so it then reports as "never referred to in the body"."""
    t = (text or "").strip()
    if not t or len(t) >= 300:
        return False, "", "", ""
    m = CAPTION_RE.match(t)
    if not m:
        return False, "", "", ""
    kind, num, sep, rest = m.group(1), m.group(2), m.group(3), m.group(4).strip()
    if sep:
        return True, kind, num, rest
    if PROSE_OPENER.match(rest):
        return False, "", "", ""
    return True, kind, num, rest

# A parenthetical is only stripped as a citation when its ENTIRE content parses
# as one. A pattern that merely looks for a year inside brackets eats ordinary
# prose asides - "(rising from 12 per cent in 2019 to 41 per cent by 2021)" - and
# a word count that quietly deletes body text errs in the direction that lets an
# over-length submission read as WITHIN.
_YEAR = r"(?:1[6-9]|20)\d{2}[a-z]?"
_NAME = r"[A-ZÀ-ÞĀ-ſ][\w'’.\-]*"
CITE_CHUNK = re.compile(
    r"^\s*(?:(?:see\s+also|see|e\.?g\.?|i\.?e\.?|cf\.?|as\s+cited\s+in|in|and)\s*,?\s*)*"
    r"(?:" + _NAME + r"(?:\s*(?:,|&|and|et\s+al\.?)\s*)*)+"
    r",?\s*\(?(?:" + _YEAR + r"|n\.\s?d\.?)\)?"
    r"(?:\s*[,;]\s*(?:pp?\.|paras?\.|ch\.|sec\.|s\.)\s*[\divxlcIVXLC]+"
    r"(?:\s*[-–—]\s*[\divxlcIVXLC]+)?)*\s*$",
    re.I | re.UNICODE)
PAREN_RE = re.compile(r"\(([^()]{1,300})\)")
NUMERIC_CITE_RE = re.compile(r"\[\s*\d+(?:\s*[-–—,;]\s*\d+)*\s*\]")


class Para:
    __slots__ = ("text", "style", "in_table", "is_quote", "is_footnote")

    def __init__(self, text, style="", in_table=False, is_quote=False, is_footnote=False):
        self.text = text
        self.style = style
        self.in_table = in_table
        self.is_quote = is_quote
        self.is_footnote = is_footnote

    @property
    def is_heading(self):
        return bool(HEADING_RE.match(self.style or ""))


def is_section_break(text, kind):
    """Section boundaries must be detectable WITHOUT paragraph styles.

    Students routinely format headings by hand - bold, larger font, no style
    applied. Requiring p.is_heading means `in_refs` never turns off again, so an
    appendix after the reference list gets counted as part of it."""
    t = text.strip()
    if not t or len(t) > 90:
        return False
    return bool((REFS_RE if kind == "refs" else APPENDIX_RE).match(t))


# ---------------------------------------------------------------- extraction


def _docx_part(z, name):
    try:
        return z.read(name)
    except KeyError:
        return None


def _docx_paras(path):
    """Walk document.xml in document order so table membership is knowable,
    then append footnote and endnote text, which live in separate parts."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        sys.exit(
            f"error: {path} is not a valid .docx (it is not a zip archive).\n"
            "  A legacy .doc renamed to .docx does this, as does a truncated download.\n"
            "  Ask the user to open it in Word and Save As .docx."
        )
    with z:
        xml = _docx_part(z, "word/document.xml")
        if xml is None:
            sys.exit(f"error: {path} has no word/document.xml - is it a real .docx?")
        out = _walk_docx(xml, path, "word/document.xml")
        for part in ("word/footnotes.xml", "word/endnotes.xml"):
            raw = _docx_part(z, part)
            if raw:
                for p in _walk_docx(raw, path, part):
                    p.is_footnote = True
                    out.append(p)
    return out


def _walk_docx(xml, path, partname):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        sys.exit(
            f"error: {partname} in {path} is not well-formed XML ({e}).\n"
            "  Word does not normally emit this. The file is most likely corrupt, or "
            "was produced by a tool that failed to escape & < > in the text.\n"
            "  Ask the user to open it in Word and re-save."
        )
    body = root.find(f"{W}body")
    container = body if body is not None else root
    out = []

    def walk(node, in_table):
        for child in node:
            tag = child.tag
            if tag == f"{W}tbl":
                walk(child, True)
            elif tag == f"{W}p":
                out.append(_docx_para(child, in_table))
            elif len(child):
                walk(child, in_table)

    walk(container, False)
    return out


def _docx_para(p, in_table):
    style = ""
    ppr = p.find(f"{W}pPr")
    if ppr is not None:
        st = ppr.find(f"{W}pStyle")
        if st is not None:
            style = st.get(f"{W}val", "") or ""
    parts = []
    for node in p.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag == f"{W}tab":
            parts.append(" ")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append(" ")
    text = "".join(parts)
    is_quote = bool(re.match(r"^(quote|intensequote|blockquote)", style, re.I))
    return Para(text, style, in_table, is_quote)


def _md_paras(text):
    out = []
    for line in text.splitlines():
        s = line.rstrip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            out.append(Para(m.group(2), "Heading" + str(len(m.group(1)))))
            continue
        if s.startswith(">"):
            out.append(Para(s.lstrip("> ").rstrip(), "Quote", is_quote=True))
            continue
        out.append(Para(s))
    return out


def _html_paras(text):
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    # Use a sentinel that cannot be eaten by the tag-stripping regex below.
    # "<<H>>" is NOT safe: <[^>]+> matches its first four characters, leaving
    # ">Heading", which then fails every heading and section-boundary test.
    text = re.sub(r"(?i)<h([1-6])[^>]*>(.*?)</h\1>", "\n\x00HEAD\x00\\2\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("\x00HEAD\x00"):
            out.append(Para(s[len("\x00HEAD\x00"):].strip(), "Heading1"))
        else:
            out.append(Para(s))
    return out


def _rtf_paras(text):
    text = re.sub(r"\\par[d]?\b", "\n", text)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d*\s?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return [Para(l.strip()) for l in text.splitlines()]


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        sys.exit(
            "error: this script does not read PDF. Use the Read tool on the PDF "
            "instead, or ask the user for the .docx."
        )
    if ext == ".docx":
        paras = _docx_paras(path)
        if not any(p.text.strip() for p in paras) and os.path.getsize(path) > 0:
            sys.exit(
                f"error: {path} parsed as a .docx but yielded no text at all.\n"
                "  Do NOT treat this as an empty document or as a pass - the body "
                "could not be read.\n"
                "  Ask the user to re-save it from Word, or export to PDF and use "
                "the Read tool."
            )
        return paras
    if ext == ".doc":
        sys.exit(
            "error: legacy .doc is not readable without Word. Ask the user to "
            "re-save as .docx or export to PDF."
        )
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if ext in (".html", ".htm"):
        return _html_paras(text)
    if ext == ".rtf":
        return _rtf_paras(text)
    return _md_paras(text)


# ------------------------------------------------------------------ counting


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\u00a0\u2007\u202f]", " ", s)


def words(s):
    """Count the way a marker's word processor does: whitespace-delimited tokens
    that contain at least one alphanumeric character. Hyphenated compounds and
    'e.g.' count as one; a bare em dash between spaces counts as none."""
    return [t for t in norm(s).split() if re.search(r"[0-9A-Za-z\u00c0-\u024f]", t)]


def strip_intext(text):
    """Remove parentheticals that parse WHOLLY as citations. Anything else - a
    prose aside that happens to contain a year, a figure reference, a range - is
    left alone."""
    def repl(m):
        inner = m.group(1)
        chunks = [c for c in re.split(r";", inner) if c.strip()]
        if chunks and all(CITE_CHUNK.match(c) for c in chunks):
            return " "
        return m.group(0)
    return NUMERIC_CITE_RE.sub(" ", PAREN_RE.sub(repl, text))


def count_report(paras, args):
    total_all = 0
    counted = 0
    removed = {k: 0 for k in ("references section", "appendix section", "headings",
                              "tables", "block quotes", "captions", "footnotes",
                              "in-text citations")}
    in_refs = False
    in_appendix = False
    ref_entries = 0
    styled_headings = any(p.is_heading for p in paras)

    for p in paras:
        t = p.text.strip()
        n = len(words(t))
        total_all += n
        if not t:
            continue

        # Section boundaries are detected with or without paragraph styles.
        if is_section_break(t, "refs"):
            in_refs, in_appendix = True, False
        elif is_section_break(t, "appendix"):
            in_appendix, in_refs = True, False
        elif p.is_heading:
            in_refs = in_appendix = False

        if p.is_footnote:
            if args.exclude_footnotes:
                removed["footnotes"] += n
                continue
            counted += n
            continue

        if in_refs:
            if not (p.is_heading or REFS_RE.match(t)) and n > 3:
                ref_entries += 1
            if args.exclude_refs:
                removed["references section"] += n
                continue
        if in_appendix and args.exclude_appendix:
            removed["appendix section"] += n
            continue
        if args.exclude_headings and p.is_heading:
            removed["headings"] += n
            continue
        if args.exclude_tables and p.in_table:
            removed["tables"] += n
            continue
        if args.exclude_quotes and p.is_quote:
            removed["block quotes"] += n
            continue
        if args.exclude_captions and is_caption_line(t)[0]:
            removed["captions"] += n
            continue

        if args.exclude_intext:
            stripped = strip_intext(t)
            gone = n - len(words(stripped))
            removed["in-text citations"] += gone
            counted += len(words(stripped))
        else:
            counted += n

    return total_all, counted, removed, ref_entries, styled_headings


FLAG_LABEL = {
    "exclude_refs": "references section", "exclude_appendix": "appendix section",
    "exclude_headings": "headings", "exclude_tables": "tables",
    "exclude_quotes": "block quotes", "exclude_captions": "captions",
    "exclude_footnotes": "footnotes", "exclude_intext": "in-text citations",
}


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("file")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--outline", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="stated word limit, for a verdict")
    ap.add_argument("--tolerance", type=float, default=0.0,
                    help="percent leeway either side, default 0 (a stated limit is a limit)")
    ap.add_argument("--exclude-refs", action="store_true")
    ap.add_argument("--exclude-appendix", action="store_true")
    ap.add_argument("--exclude-headings", action="store_true")
    ap.add_argument("--exclude-intext", action="store_true")
    ap.add_argument("--exclude-tables", action="store_true")
    ap.add_argument("--exclude-quotes", action="store_true")
    ap.add_argument("--exclude-captions", action="store_true")
    ap.add_argument("--exclude-footnotes", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        sys.exit(f"error: no such file: {args.file}")
    paras = load(args.file)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.text or not (args.outline or args.count):
        for p in paras:
            if p.text.strip():
                print(p.text)
        if not args.count and not args.outline:
            return 0

    if args.outline:
        print("OUTLINE")
        cur, acc = None, 0
        for p in paras:
            if p.is_heading and p.text.strip():
                if cur is not None:
                    print(f"    ({acc} words)")
                print(f"  {p.style:<12} {p.text.strip()[:80]}", end="")
                cur, acc = p.text, 0
            else:
                acc += len(words(p.text))
        if cur is not None:
            print(f"    ({acc} words)")
        else:
            print("  (no styled headings found - document may use manual formatting)")
        print()

    if args.count:
        total, counted, removed, refs, styled = count_report(paras, args)
        print("WORD COUNT")
        print(f"  Everything in the file      {total:>7,}")
        for k, v in removed.items():
            if v:
                print(f"    - {k:<24} {v:>7,}")
        print(f"  Counted against the limit   {counted:>7,}")
        print(f"  Reference-list entries      {refs:>7,}")

        # A flag that removed nothing is reported. Silence here reads as "the
        # exclusion was applied", when what happened is that the section was
        # never found - typically a manually formatted heading.
        noop = [FLAG_LABEL[f] for f in FLAG_LABEL
                if getattr(args, f, False) and not removed[FLAG_LABEL[f]]]
        if noop:
            print("\n  !! These exclusions removed NOTHING:")
            for lbl in noop:
                print(f"       --{lbl.replace(' ', '-')}  ->  0 words")
            print("     Either the document genuinely has none, or the section was")
            print("     not recognised. Check --outline and the document's headings")
            print("     before reporting this count.")
            if not styled:
                print("     This document has NO styled headings, which makes a")
                print("     missed section very likely.")

        if args.limit:
            lo = int(args.limit * (1 - args.tolerance / 100))
            hi = int(args.limit * (1 + args.tolerance / 100))
            pct = 100.0 * counted / args.limit
            verdict = "WITHIN" if lo <= counted <= hi else ("UNDER" if counted < lo else "OVER")
            tol = f" (+/-{args.tolerance:g}% = {lo:,}-{hi:,})" if args.tolerance else ""
            print(f"\n  Limit {args.limit:,}{tol}")
            print(f"  -> {verdict}  ({pct:.1f}% of limit, {counted - args.limit:+,} vs stated)")
            if args.tolerance:
                print("     NOTE: tolerance was supplied by you, not by the document.")
                print("     Most task sheets treat +10% as the PENALTY threshold, not")
                print("     a safe zone. The signed delta above is the honest number.")
        print()
        print("  NOTE: exclusions applied were only the ones you passed as flags.")
        print("  Confirm them against the task sheet's own wording before reporting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
