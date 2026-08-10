#!/usr/bin/env python3
"""citecheck.py - cross-check in-text citations against the reference list.

Stdlib only. Reads whatever doctext.py can read (.docx/.md/.txt/.html/.rtf), or a
plain-text dump you piped from a PDF.

  python citecheck.py FILE
  python citecheck.py FILE --style apa7
  python citecheck.py FILE --style ieee

Exit codes:
  0  checked, and everything resolved both ways
  1  findings: orphan citations, year mismatches, uncited entries
  2  COULD NOT CHECK - no reference list found, or no citations detected.
     This is NOT a pass. A document whose citations the parser cannot see looks
     identical to a document with no citation problems, and reporting the second
     when it was the first is the worst thing this script can do.

What it catches - the two failures that cost the most marks:
  ORPHAN CITE  cited in the body, missing from the reference list
  UNCITED REF  sits in the reference list, never cited in the body
Plus per-style format smells.

This is a MECHANICAL check. It cannot tell you whether a source is real.
Verifying that each reference actually exists is a separate, mandatory step -
run linkcheck.py and see the skill's Step 3. Fabricated references are the
highest-severity finding markpilot can produce and this script will happily pass
all of them.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doctext import (load, words, REFS_RE, APPENDIX_RE, norm,  # noqa: E402
                     is_section_break, die)

# The n.d. branch MUST require the periods. Written as `n\.?\s?d\.?` it matches the
# "nd" inside "and", so every "Smith and Jones, 2020" - in text and in the reference
# list - keys its year as n.d. and reports as a year mismatch against itself.
YEAR = r"(?:1[6-9]|20)\d{2}[a-z]?|\bn\.\s?d\.?"

# Author names are not ASCII. A bare [A-Z] lead class silently drops Öztürk,
# Álvarez and Nguyễn from narrative citations while the parenthetical form still
# matches them, so the same source keys differently in the two places and reports
# as both an orphan and an uncited reference.
UPPER = r"[A-ZÀ-ÖØ-ÞĀ-ſƁ-ɏ]"
LETTER = r"[^\W\d_]"
NAMECH = r"(?:" + LETTER + r"|['’\-])"

PAREN = re.compile(r"\(([^()]{2,300}?)\)")
NUMERIC = re.compile(r"\[\s*(\d+(?:\s*[-–—,;]\s*\d+)*)\s*\]")
NARRATIVE = re.compile(
    r"\b((?:" + UPPER + NAMECH + r"{1,})"                 # lead capitalised word
    r"(?:"                                                # co-authors, each needing
    r"\s*,\s*(?:(?:and|&)\s+)?" + UPPER + NAMECH + r"+"   #   a comma: ", Jones" ", and Lee"
    r"|\s+(?:and|&)\s+" + UPPER + NAMECH + r"+"           #   or an and/&: " and Jones"
    r")*)"
    r"(?:\s+et\s+al\.?)?"                                 # optional "et al."
    r"(?:['’]s)?"                                         # possessive after "et al."
    r"\s*\(\s*(" + YEAR + r")",
    re.UNICODE)

# These filter the NARRATIVE lead position only, where a sentence-opening
# connective can be mistaken for a surname ("However, Nguyen et al. (2021)").
# They must NOT be applied to the parenthetical form: "(An, 2021)" and
# "(So, 2019)" are ordinary surnames, and filtering them there makes the source
# invisible on BOTH sides at once - no orphan raised, and the reference dropped
# from the uncited check too.
CONNECTIVES = {
    "however", "therefore", "moreover", "furthermore", "thus", "hence",
    "additionally", "consequently", "nevertheless", "nonetheless", "although",
    "though", "whereas", "similarly", "conversely", "finally", "first",
    "firstly", "second", "secondly", "third", "thirdly", "overall", "indeed",
    "notably", "importantly", "specifically", "instead", "meanwhile",
    "accordingly", "subsequently", "in", "according", "recent", "recently",
    "research", "researchers", "studies", "study", "work", "evidence", "data",
    "results", "findings", "for", "as", "while", "since", "both", "many",
    "several", "other", "others", "such", "here", "there", "it", "they", "we",
    "one", "two", "by", "from", "at", "on", "an", "a", "and", "but", "or", "so",
    "yet", "if", "when", "where", "which", "the", "this", "that", "these",
    "those", "figure", "table", "see", "chapter", "section", "appendix", "note",
    "source", "adapted", "using", "based", "given", "each", "its", "their",
}
# Never a surname, in any position.
NEVER_NAME = {"figure", "fig", "table", "chart", "exhibit", "appendix", "section",
              "eg", "ie", "cf", "vol", "no", "pp", "p", "n"}

PARTICLES = {
    "van", "von", "de", "del", "della", "der", "den", "du", "da", "dos", "das",
    "di", "la", "le", "el", "al", "bin", "ibn", "ter", "ten", "op", "st", "san",
}


def surname(token):
    # Keep unicode letters, apostrophes and hyphens; drop everything else.
    t = re.sub(r"[^\w'’\-]", "", token, flags=re.UNICODE)
    t = re.sub(r"[\d_]", "", t)
    t = re.sub(r"['’]s?$", "", t)   # Hayes' / Hayes’s / Smith's
    return t.lower()


def lead_surname(phrase, drop_connectives=True):
    """First token in an author phrase that could be a surname.

    drop_connectives is True only for the narrative form, where the ambiguity is
    real. In a parenthetical the comma already disambiguates, so every token is a
    candidate and real surnames like An, So, Ho and Le survive."""
    toks = [t for t in re.split(r"[\s,&]+", phrase) if t]
    for i, tok in enumerate(toks):
        if tok.lower() in ("and", "et", "al", "al."):
            continue
        s = surname(tok)
        if not s or len(s) < 2 or s in NEVER_NAME:
            continue
        if drop_connectives and s in CONNECTIVES:
            continue
        if s in PARTICLES and i + 1 < len(toks):
            nxt = surname(toks[i + 1])
            if nxt and len(nxt) >= 2 and nxt not in NEVER_NAME:
                return toks[i + 1]
        return tok
    return ""


def split_sections(paras):
    """Body vs reference list.

    A sub-heading inside the reference section must not end it - the same
    heading-level rule the word count uses. Appendices commonly sit BEFORE the
    reference list, so an appendix heading returns to body, but only at a level at
    or above the one that opened the current section."""
    body, refs = [], []
    cur, level = body, 1
    for p in paras:
        t = p.text.strip()
        if is_section_break(t, "refs", p.in_table):
            cur = refs
            level = p.heading_level if p.is_heading else 1
            continue
        if is_section_break(t, "appendix", p.in_table):
            cur = body
            level = p.heading_level if p.is_heading else 1
            continue
        if cur is refs and p.is_heading and p.heading_level <= level:
            cur = body
        cur.append(p)
    return body, refs


# A line that starts a new reference entry, rather than continuing the previous
# one. Wrapped/hanging-indent lists put one entry across several lines; treating
# each line as an entry fragments them, which produces false UNCITED REFs, false
# "no year" smells, and - in linkcheck - a MISMATCH accusation against a
# perfectly correct source whose DOI sits on its own line.
ENTRY_START = re.compile(
    r"^\s*(?:van|von|de|del|della|der|den|du|da|dos|das|di|la|le|el|al|bin|ibn|ter|ten)?\s*(?:"
    r"\[\d+\]"                                                              # [1] IEEE
    r"|\d+[.)]\s+" + UPPER                                                  # 1. Vancouver
    + r"|" + UPPER + NAMECH + r"+\s*,\s*(?:" + UPPER + r"\.|" + UPPER + NAMECH + r"+)"
    + r"|" + UPPER + NAMECH + r"+\s+" + UPPER + r"{1,3}\s*,?\s*\(?(?:1[6-9]|20)\d{2}"
    + r"|" + UPPER + r"[\w&'’ .\-]{2,60}?\.\s*\(\s*(?:1[6-9]|20)\d{2}"      # Org. (2024).
    + r"|[—–-]{2,}"                                                         # repeated author
    + r")", re.UNICODE)


def ref_entries(refs_paras):
    """Join continuation lines so one entry is one string."""
    out, buf = [], []

    def flush():
        if buf:
            joined = " ".join(x.strip() for x in buf if x.strip())
            if len(words(joined)) >= 4:
                out.append(re.sub(r"\s+", " ", joined).strip())
            buf.clear()

    for p in refs_paras:
        t = p.text.strip()
        if not t:
            flush()
            continue
        if REFS_RE.match(t) or APPENDIX_RE.match(t):
            continue
        if ENTRY_START.match(t) or not buf:
            flush()
            buf.append(t)
        else:
            buf.append(t)
    flush()
    return out


def ref_key(entry):
    m = re.match(r"^\s*\[?\d+\]?[.)]?\s*", entry)
    head = entry[m.end():] if m else entry
    # IEEE and Vancouver put initials before the surname ("T. Nguyen, ..."). Drop
    # leading initials - the period is required, so APA's "Smith, J." is untouched.
    head = re.sub(r"^\s*(?:" + UPPER + r"\.\s*)+", "", head, flags=re.UNICODE)
    am = re.match(r"(" + NAMECH + r"{2,}(?:\s+" + NAMECH + r"{2,})?)", head.strip(),
                  flags=re.UNICODE)
    a = surname(lead_surname(am.group(1), drop_connectives=False)) if am else ""
    # Prefer a parenthesised year, then any year NOT part of a decade form.
    # A bare search lets "Rethinking the 1970s" win over the real 2019 - the
    # [a-z]? even swallows the trailing "s" - producing a false YEAR MISMATCH and
    # a false UNCITED REF on a correctly formatted entry.
    y = ""
    m2 = re.search(r"\(\s*((?:1[6-9]|20)\d{2}[a-z]?)\s*\)", entry)
    if m2:
        y = m2.group(1)
    else:
        for cand in re.finditer(r"(?:1[6-9]|20)\d{2}[a-z]?", entry):
            tok = cand.group(0)
            after = entry[cand.end():cand.end() + 1]
            if tok.endswith("s") or after == "s":       # 1970s / 1990s
                continue
            y = tok
            break
        if not y and re.search(r"n\.\s?d\.?", entry, re.I):
            y = "nd"
    y = re.sub(r"[^0-9a-z]", "", y.lower())
    return a, (y or "nd")


def entry_tokens(entry):
    """Whole words of a reference entry, lowercased, letters only."""
    return set(re.findall(r"[^\W\d_]{2,}", (entry or "").lower(), flags=re.UNICODE))


def author_matches(item, entry):
    """Does ANY author on the Crossref record appear in the entry, as a whole word?

    Two failures this exists to prevent, both of which shipped:

    1. A SUBSTRING test lets a short surname match anything. 'He' is inside 'the',
       'other', 'when', 'research'; 'Ma' is inside 'formal', 'primary'. A record by
       He et al. therefore 'matched' an entry authored by Smith, and the wrong DOI
       was reported LIVE / FOUND at exit 0 - the exact false pass this project
       exists to prevent.
    2. A record with NO author array must fail, not pass vacuously. That is how a
       regulator report matched a court case.

    Checking every author, not just the first, matters because students reorder
    authors and numeric styles put initials first."""
    authors = item.get("author") or []
    if not authors:
        return False
    toks = entry_tokens(entry)
    if not toks:
        return False
    for a in authors:
        fam = (a.get("family") or "").lower()
        if not fam:
            continue
        # Particle and hyphenated surnames: any substantive part matching as a
        # whole token is enough ("van Rooij" -> "rooij").
        for part in re.split(r"[\s\-'’]+", fam):
            part = re.sub(r"[^\w]", "", part, flags=re.UNICODE)
            if len(part) >= 2 and part in toks:
                return True
    return False


def org_letters(entry):
    """Lowercase letters of the organisational author name, before the year."""
    head = re.split(r"\(\s*(?:1[6-9]|20)\d{2}", entry)[0]
    return re.sub(r"[^a-z]", "", head.lower())


def is_subsequence(short, long):
    it = iter(long)
    return all(c in it for c in short)


def pair_abbreviations(orphans, uncited):
    """Match short all-caps citations to spelled-out organisational entries.

    "(ASIC, 2023)" in the body and "Australian Securities and Investments
    Commission. (2023)" in the list are the SAME source, correctly formatted. Left
    unpaired they report twice - once as an orphan citation and once as an uncited
    reference - which is four findings for two sources and buries the real ones.

    The genuine finding is narrower: APA 7 requires the abbreviation to be
    introduced at first mention, "Australian Securities and Investments Commission
    [ASIC] (2023)". So these are reported as a check-this, not as an error."""
    pairs, used_o, used_u = [], set(), set()
    for oi, (a, y, raw, n) in enumerate(orphans):
        if not (2 <= len(a) <= 6):
            continue
        for ui, e in enumerate(uncited):
            if ui in used_u:
                continue
            ey = ref_key(e)[1]
            if ey != y:
                continue
            letters = org_letters(e)
            if len(letters) < 8:            # a person's surname, not an organisation
                continue
            if is_subsequence(a, letters):
                pairs.append((a.upper(), y, e, raw, n))
                used_o.add(oi)
                used_u.add(ui)
                break
    return pairs, used_o, used_u


def entry_number(entry):
    m = re.match(r"^\s*(?:\[(\d+)\]|(\d+)[.)])", entry)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def intext_authordate(body_text):
    """{(surname, year): [raw citation, ...]}"""
    found = {}

    def add(auth, yr, raw):
        a = surname(auth)
        if not a or a in NEVER_NAME or len(a) < 2:
            return
        y = re.sub(r"[^0-9a-z]", "", yr.lower()) or "nd"
        found.setdefault((a, y), []).append(raw.strip())

    for m in PAREN.finditer(body_text):
        inner = m.group(1)
        if not re.search(YEAR, inner):
            continue
        for chunk in re.split(r";", inner):
            # "(Brown, 1999, as cited in Smith, 2020)" - the citable source is the
            # SECONDARY one. Keying the primary raises a false orphan for Brown
            # and a false uncited-ref for Smith, both on a correctly formatted
            # secondary citation.
            sec = re.split(r"(?i)\bas\s+cited\s+in\b|\bcited\s+in\b|\bquoted\s+in\b", chunk)
            chunk = sec[-1]
            ym = re.search(YEAR, chunk)
            if not ym:
                continue
            head = chunk[: ym.start()]
            head = re.sub(r"(?i)\b(?:see|also|e\.g\.|i\.e\.|cf\.)\b", " ", head)
            tok = lead_surname(head, drop_connectives=False)
            # An author name is capitalised. Without this, a parenthetical date range
            # like "(early Sep - early Oct 2026)" keys "early" as a surname and
            # reports a phantom orphan citation.
            if tok and (tok[0].isupper() or surname(tok) in PARTICLES):
                add(tok, ym.group(0), chunk)

    for m in NARRATIVE.finditer(body_text):
        tok = lead_surname(m.group(1), drop_connectives=True)
        if tok:
            add(tok, m.group(2), m.group(0))
    return found


def style_smells(entries, style):
    out = []
    for i, e in enumerate(entries, 1):
        s = []
        if not re.search(YEAR, e):
            s.append("no year")
        if re.search(r"\bRetrieved from\b", e, re.I) and style == "apa7":
            s.append("'Retrieved from' - APA 7 drops it unless a retrieval date is needed")
        if (style in ("apa7", "harvard", "chicago", "mla")
                and re.search(r"https?://(?:dx\.)?doi\.org/", e) is None
                and re.search(r"\bdoi:\s*10\.", e, re.I)):
            s.append("bare 'doi:' - APA 7/Harvard want the full https://doi.org/ URL")
        if re.search(r"\bet al\b", e, re.I) and style in ("apa7", "harvard"):
            s.append("'et al.' in the reference list - list up to 20 authors in APA 7")
        if style == "apa7" and re.search(r"\bvol\.?\s*\d|\bno\.?\s*\d", e, re.I):
            s.append("'Vol./No.' labels - APA 7 uses 34(2), not Vol. 34, No. 2")
        if style == "ieee" and not re.match(r"^\s*\[\d+\]", e):
            s.append("IEEE entries must open with a bracketed number")
        if re.search(r"\b(accessed|viewed)\b", e, re.I) and style == "apa7":
            s.append("'Accessed/Viewed' is Harvard, not APA")
        if len(e) < 30:
            s.append("suspiciously short for a full reference")
        if s:
            out.append((i, e[:110], s))
    return out


def expand_numeric(body_text):
    nums = set()
    for m in NUMERIC.finditer(body_text):
        for part in re.split(r"[,;]", m.group(1)):
            got = [int(n) for n in re.findall(r"\d+", part)]
            if len(got) == 2 and re.search(r"[-–—]", part) and got[0] < got[1]:
                nums.update(range(got[0], got[1] + 1))
            else:
                nums.update(got)
    # "[3]-[7]" across two brackets means 3 through 7. Without expanding these,
    # every interior number reads as an uncited reference.
    for a, b in re.findall(r"\[\s*(\d+)\s*\]\s*[-–—]\s*\[\s*(\d+)\s*\]", body_text):
        if int(a) < int(b):
            nums.update(range(int(a), int(b) + 1))
    return sorted(nums)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--style", default="apa7",
                    choices=["apa7", "harvard", "ieee", "chicago", "mla", "vancouver",
                             "aglc", "unknown"])
    args = ap.parse_args()

    if not os.path.exists(args.file):
        die(f"error: no such file: {args.file}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    paras = load(args.file)
    body_p, refs_p = split_sections(paras)
    body_text = norm("\n".join(p.text for p in body_p))
    entries = ref_entries(refs_p)
    footnoted = any(p.is_footnote and p.text.strip() for p in paras)

    print(f"REFERENCE INTEGRITY  ({args.style})")
    print(f"  body paragraphs {len(body_p)}   reference entries {len(entries)}")
    if footnoted:
        print("  (document has footnotes/endnotes - they are included in the body text)")
    print()

    blocked = []
    if not refs_p:
        blocked.append("No reference-list heading found (References / Bibliography / "
                       "Works Cited).")
    if not entries:
        blocked.append("No reference entries were parsed.")

    numeric = expand_numeric(body_text)
    numbered_entries = [entry_number(e) for e in entries]
    use_numeric = (args.style in ("ieee", "vancouver")
                   or (numeric and any(n is not None for n in numbered_entries)))

    findings = 0
    if use_numeric:
        print("  Numbering mode (bracketed citations)")
        cited = set(numeric)
        # Read each entry's OWN number. Inferring membership from list position
        # cannot see a duplicated or out-of-range entry number.
        have, dupes = set(), set()
        for n in numbered_entries:
            if n is None:
                continue
            if n in have:
                dupes.add(n)
            have.add(n)
        unnumbered = sum(1 for n in numbered_entries if n is None)
        if unnumbered:
            print(f"    !! {unnumbered} entr{'y' if unnumbered == 1 else 'ies'} carry no "
                  f"bracketed number - cannot be matched")
            findings += 1
        if not cited:
            blocked.append("No bracketed in-text citations were detected.")
        missing = sorted(cited - have)
        unused = sorted(have - cited)
        if cited:
            print(f"    cited numbers   {min(cited)}..{max(cited)}  ({len(cited)} distinct)")
        if dupes:
            print(f"    DUPLICATE ENTRY numbers used twice in the list: {sorted(dupes)}")
            findings += 1
        if missing:
            print(f"    ORPHAN CITE     [{', '.join(map(str, missing))}] cited with no "
                  f"matching entry")
            findings += 1
        if unused:
            print(f"    UNCITED REF     entries {', '.join(map(str, unused))} never cited")
            findings += 1
        if cited and not (missing or unused or dupes or unnumbered):
            print("    OK - every number resolves both ways")
    else:
        cites = intext_authordate(body_text)
        if not cites:
            blocked.append("No in-text citations were detected in the body text.")
        keys = {ref_key(e) for e in entries}
        by_author = {}
        for a, y in keys:
            by_author.setdefault(a, set()).add(y)

        orphans, yearmiss = [], []
        for (a, y), raws in sorted(cites.items()):
            if a not in by_author:
                orphans.append((a, y, raws[0], len(raws)))
            elif y not in by_author[a] and y != "nd":
                yearmiss.append((a, y, sorted(by_author[a]), raws[0]))

        # Match uncited entries on (author, YEAR), not author alone. On author
        # alone, a second work by the same author - the 2020a/2020b case, and
        # every different-person-same-surname case - is never flagged.
        cited_keys = set(cites)
        uncited = []
        for e in entries:
            k = ref_key(e)
            if not k[0]:
                uncited.append((e, "author could not be parsed"))
            elif k not in cited_keys:
                uncited.append((e, None))

        print(f"  Distinct in-text citations: {len(cites)}")

        uncited_text = [e for e, _ in uncited]
        pairs, used_o, used_u = pair_abbreviations(orphans, uncited_text)
        if pairs:
            orphans = [o for i, o in enumerate(orphans) if i not in used_o]
            uncited = [u for i, u in enumerate(uncited) if i not in used_u]
            print(f"\n  LIKELY ABBREVIATION  ({len(pairs)}) - cited by initials, listed "
                  f"in full")
            for abbr, y, entry, raw, n in pairs:
                print(f"    ({abbr}, {y})  x{n}  ->  {entry[:66]}")
            print("    These are probably correct. APA 7 asks that the abbreviation be")
            print("    introduced at first mention - 'Full Name [ABBR] (year)' - so check")
            print("    the first use of each, then leave them alone.")

        if orphans:
            print(f"\n  ORPHAN CITE  ({len(orphans)}) - cited in the body, absent from the list")
            for a, y, raw, n in orphans:
                print(f"    {a} {y}   x{n}   e.g. {raw[:70]}")
            findings += 1
        if yearmiss:
            print(f"\n  YEAR MISMATCH  ({len(yearmiss)}) - author listed under a different year")
            for a, y, have, raw in yearmiss:
                print(f"    {a} cited as {y}, listed as {'/'.join(have)}   e.g. {raw[:60]}")
            findings += 1
        if uncited:
            print(f"\n  UNCITED REF  ({len(uncited)}) - in the list, never cited in the body")
            for e, why in uncited:
                print(f"    {e[:100]}" + (f"   [{why}]" if why else ""))
            findings += 1
        if cites and entries and not (orphans or yearmiss or uncited):
            print("  OK - every citation resolves both ways")

    smells = style_smells(entries, args.style)
    if smells:
        print(f"\n  FORMAT SMELLS  ({len(smells)} entries)")
        for i, e, ss in smells:
            print(f"    [{i}] {e}")
            for s in ss:
                print(f"         - {s}")

    if blocked:
        print("\n  COULD NOT CHECK - this is NOT a pass:")
        for b in blocked:
            print(f"    - {b}")
        print("    A document whose citations the parser cannot see looks exactly like")
        print("    a document with no citation problems. Read the reference section by")
        print("    hand before reporting anything about it.")

    print("\n  REMINDER: this check is mechanical. It cannot tell a real source from")
    print("  an invented one - run linkcheck.py, and see the skill's Step 3.")

    if blocked:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
