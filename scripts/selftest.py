#!/usr/bin/env python3
"""selftest.py - run before trusting citecheck.py after any edit to its regexes.

    python selftest.py

Every case below is a bug that was actually observed during development, not a
hypothetical. The citation regexes are the fragile part of this skill: a change
that looks harmless (adding a co-author branch, widening the year pattern) has
repeatedly broken an unrelated case. Nine of these were live defects.

Exits non-zero on failure.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402
import urllib.parse  # noqa: E402
from testimonial import (  # noqa: E402
    share_url, form_url, public_record, record, URL_BUDGET)
from docxpatch import (  # noqa: E402
    minimal_edit, apply_to_paragraph, visible_text, para_runs)
from tablecheck import analyse as tc_analyse  # noqa: E402
from stylecheck import analyse as sc_analyse  # noqa: E402
from discover import score as disc_score, offering as disc_offering  # noqa: E402
from citecheck import intext_authordate, ref_key, ENTRY_START  # noqa: E402
from doctext import (is_caption_line, strip_intext, words, REFS_RE,  # noqa: E402
                     looks_like_reference)
from doifind import looks_corporate  # noqa: E402
from citecheck import author_matches  # noqa: E402

INTEXT = {
    # basic forms
    "Smith (2020) found that": [("smith", "2020")],
    "Smith and Jones (2020) argue": [("smith", "2020")],
    "Smith & Jones (2020) argue": [("smith", "2020")],
    "as shown (Smith, 2020)": [("smith", "2020")],
    "(Smith & Jones, 2020, p. 14)": [("smith", "2020")],
    "(Smith, 2020, pp. 4-9) and later work": [("smith", "2020")],
    "(see Smith 2020; Jones 2021)": [("jones", "2021"), ("smith", "2020")],
    "reported by Jones (2020a)": [("jones", "2020a")],
    # "et al." must not be folded into the co-author alternation - doing so
    # loses every "Author et al. (Year)" and reports it as an uncited reference
    "Nguyen et al. (2021) argue": [("nguyen", "2021")],
    "(Nguyen et al., 2021)": [("nguyen", "2021")],
    "Smith et al.'s (2020) model": [("smith", "2020")],
    # a three-author narrative must key the FIRST surname, not the second
    "Smith, Jones, and Lee (2020) show": [("smith", "2020")],
    # possessives must not leak into the key
    "Smith's (2020) framework": [("smith", "2020")],
    "O'Brien (2020) noted": [("o'brien", "2020")],
    # sentence-opening connectives must not be read as the lead author
    "However, Nguyen et al. (2021) argue": [("nguyen", "2021")],
    "Therefore, Smith (2020) is wrong": [("smith", "2020")],
    "In addition, Chen and Lee (2019) found": [("chen", "2019")],
    "Recent studies (Smith, 2020) confirm": [("smith", "2020")],
    # nobiliary particles must key the same way the reference list does
    "Van Dijk (2018) argued": [("dijk", "2018")],
    "(van Dijk, 2018)": [("dijk", "2018")],
    "de Vries and Smith (2021)": [("vries", "2021")],
    # the n.d. branch must require its periods, or "and" matches it
    "(Smith and Jones, 2020)": [("smith", "2020")],
    "(Anderson and Nolan, 2019, p. 4)": [("anderson", "2019")],
    "(Wilson, n.d.)": [("wilson", "nd")],
    # non-citations
    "In Table 1 (2020) is not a citation": [],
    "(n.d.) alone": [],
    # Found on the first real submission this was run against:
    # a possessive with a curly apostrophe keyed "hayes’" and never matched
    "Hayes’ (2022) PROCESS macro": [("hayes", "2022")],
    "Hayes' (2022) PROCESS macro": [("hayes", "2022")],
    # a parenthetical date range keyed "early" as a surname
    "fielded (early Sep – early Oct 2026) online": [],
    "runs (mid Jan - late Feb 2025) overall": [],
}

# ref_entries must treat a lowercase nobiliary particle as the START of an entry.
# It did not, so "van Rooij, M., ... (2011)" was merged into the preceding entry and
# reported as an orphan citation plus a swallowed reference.
ENTRY_STARTS = {
    "van Rooij, M., Lusardi, A., & Alessie, R. (2011). Financial literacy.": True,
    "de Vries, A. (2021). Title. Journal, 1(1), 1-9.": True,
    "Smith, J. (2020). Title. Journal, 34(2), 118-142.": True,
    "[3] T. Nguyen, \"A survey,\" ACM, 2021.": True,
    "Australian Securities and Investments Commission. (2023). Review.": True,
    "stochastic parrots: Can language models be too big? Proceedings, 610-623.": False,
    "https://doi.org/10.1145/3442188.3445922": False,
    "Journal of Retail Studies, 34(2), 118-142.": False,
}

REFS = {
    "Smith, J. (2020). Title. Journal, 34(2), 118-142.": ("smith", "2020"),
    "Smith, J. and Jones, A. (2020). Title.": ("smith", "2020"),
    "Anderson, B. and Nolan, C. (2019). Title.": ("anderson", "2019"),
    "Smith, J., & Jones, A. (2020a). Title.": ("smith", "2020a"),
    "Van Dijk, J. (2018). Title.": ("dijk", "2018"),
    "van Dijk, J. (2018). Title.": ("dijk", "2018"),
    "de Vries, A. (2021). Title.": ("vries", "2021"),
    "O'Brien, K. (2020). Title.": ("o'brien", "2020"),
    "Wilson, K. (n.d.). Undated source. Some Journal.": ("wilson", "nd"),
    # A decade in the title must not beat the real year. "1970s" won, and the
    # [a-z]? even swallowed the trailing "s", producing a false YEAR MISMATCH and a
    # false UNCITED REF on a correctly formatted entry.
    "Jones, A. Rethinking the 1970s. Oxford University Press, 2019.": ("jones", "2019"),
    '[9] T. Nguyen, "A survey of 1990s methods," ACM, 2021.': ("nguyen", "2021"),
    # initials-first styles
    '[3] T. Nguyen, "A survey," ACM, 2021.': ("nguyen", "2021"),
    '[1] J. Smith and A. Jones, "Attention," IEEE, 2020.': ("smith", "2020"),
    # AI tools cited as software
    "OpenAI. (2024). ChatGPT [Large language model].": ("openai", "2024"),
    "Anthropic. (2026). Claude (Opus 5) [Large language model].": ("anthropic", "2026"),
}


# True  = this line is a real caption
# False = this line is prose that merely mentions the figure/table
# Misclassifying prose as a caption is doubly wrong: it steals the caption text AND
# removes the only cross-reference the figure had, so the figure then reports as
# "never referred to in the body". The stem-vs-word-boundary bug did exactly that.
CAPTIONS = {
    "Figure 1. Engagement rate by cohort over twelve months": True,
    "Table 1: Regression coefficients": True,
    "Figure 2 - Residual plot for the fitted model": True,
    "Table 2. Descriptive statistics": True,
    # Verb stems that open ordinary captions. The separator, not the word, is what
    # makes these captions - testing the following word alone marks them prose.
    "Figure 3. Comparison of revenue by region, 2019 to 2024": True,
    "Figure 4. Reported satisfaction scores by cohort": True,
    "Table 3. Detailed breakdown of costs by category": True,
    "Table 4: Listed holdings by asset class": True,
    "Figure 5. Summary of the fitted coefficients": True,
    "Figure 1 summarises the regression output.": False,
    "Table 1 summarises the regression output.": False,
    "Table 3 shows that engagement declined.": False,
    "Figure 4 illustrates the relationship.": False,
    "Table 5 reports the coefficients.": False,
    "Figure 6 demonstrates the effect clearly.": False,
    "Table 7 compares the two cohorts.": False,
    "Figure 8 highlights the outliers.": False,
    "Table 9 provides a breakdown by region.": False,
    "Figure 10 reveals a seasonal pattern.": False,
    "Table 2 below sets out the results.": False,
}


# A reference heading is routinely numbered. Failing to match it means the whole
# reference list is silently counted as body text and --exclude-refs removes nothing,
# with no error - the flag reads as applied when it did nothing at all.
REFS_HEADINGS = {
    "References": True,
    "REFERENCES": True,
    "Reference List": True,
    "Bibliography": True,
    "Works Cited": True,
    "References:": True,
    "6. References": True,
    "6 References": True,
    "Chapter 6: References": True,
    "7.1 References": True,
    "References and further reading": False,   # not a bare heading
    "The references below are indicative": False,
}

# strip_intext must remove citations and NOTHING else. Over-removal silently
# shrinks the word count, which is the direction that lets an over-length
# submission read as WITHIN.
INTEXT_STRIP = {
    "The result held (Smith, 2020) throughout.": 4,
    "Both agreed (Smith & Jones, 2020, p. 14) on this.": 4,
    "Several sources agree (see Smith 2020; Jones 2021).": 3,
    "Adoption grew (rising from 12 per cent in 2019 to 41 per cent by 2021) overall.": 16,
    "Two waves ran (wave one in March 2020, wave two in September 2020).": 13,
    "The figure (Table 3, 2024 update) is indicative.": 8,
    "Numeric styles cite like this [4] and this [7], [9].": 7,
}


# Grey literature must be routed away from Crossref, which indexes almost none of it.
# Both of the worst false matches were here: ASIC's 2023 report matched a 2013 court
# case, NHMRC's 2023 statement a 1993 article. Note the lowercase "and" in both - a
# capitalised-words-only pattern stops dead at it and classifies neither.
CORPORATE_CASES = {
    "Australian Securities and Investments Commission. (2023). Review.": True,
    "National Health and Medical Research Council. (2023). Statement.": True,
    "Australian Securities Exchange. (2023). ASX investor study.": True,
    "International Organization of Securities Commissions. (2025). DEP.": True,
    "Financial Conduct Authority. (2024). Digital engagement practices.": True,
    "Reserve Bank of Australia. (2024). Statement on monetary policy.": True,
    "Smith, J. (2020). Title. Journal, 34(2), 118-142.": False,
    "Hayes, A. F. (2022). Introduction to mediation.": False,
    "van Rooij, M., Lusardi, A., & Alessie, R. (2011). Financial literacy.": False,
    "Hollebeek, L. D. (2011a). Demystifying customer brand engagement.": False,
}

# A record with NO author array must FAIL the author check, not pass it vacuously.
# Returning True for "nothing to check against" is what let a court case be matched
# to a regulator report. Particle surnames must compare on letters only.
# A SUBSTRING test lets a short surname match anything: "He" is inside "the",
# "other", "when"; "Ma" is inside "formal". A record by He et al. therefore matched
# an entry authored by Smith, and linkcheck reported the wrong DOI as LIVE at exit 0
# while doifind proposed it at FOUND. Whole-token matching only.
_SMITH = ("Smith, J. (2016). A deep residual approach to the recognition of "
          "images. Journal of Vision Systems, 8(1), 10-25.")
AUTHOR_CASES = [
    ({"author": [{"family": "He"}]}, _SMITH, False),
    ({"author": [{"family": "Ma"}]}, _SMITH, False),
    ({"author": [{"family": "An"}]}, _SMITH, False),
    ({"author": [{"family": "Li"}]}, _SMITH, False),
    ({"author": [{"family": "Smith"}]}, _SMITH, True),
    # any author counts, not only the first - students reorder them
    ({"author": [{"family": "Zzz"}, {"family": "Smith"}]}, _SMITH, True),
    ({}, "Smith, J. (2020). Title.", False),
    ({"author": []}, "Smith, J. (2020). Title.", False),
    ({"author": [{"family": ""}]}, "Smith, J. (2020). Title.", False),
    ({"author": [{"family": "Smith"}]}, "Smith, J. (2020). Title.", True),
    ({"author": [{"family": "van Rooij"}]},
     "van Rooij, M., Lusardi, A. (2011). Financial literacy.", True),
    ({"author": [{"family": "Rooij"}]},
     "van Rooij, M., Lusardi, A. (2011). Financial literacy.", True),
    ({"author": [{"family": "Nguyen"}]}, "Smith, J. (2020). Title.", False),
]


# Grey literature must be routed away from Crossref. The keyword list alone missed
# acronym authors, bodies not ending in a listed noun, consultancies, and every
# numbered entry (a leading "[12]" defeated the anchor).
CORP2 = {
    "OECD. (2024). Digital finance report.": True,
    "WHO. (2023). Global report.": True,
    "CSIRO. (2022). Technology outlook.": True,
    "United Nations. (2023). Sustainable development goals report.": True,
    "Standards Australia. (2021). AS 1234:2021.": True,
    "Deloitte. (2024). Consumer tracker.": True,
    '[12] Australian Securities and Investments Commission, "Review," 2023.': True,
    "Oliver, R. L. (1999). Whence consumer loyalty? Journal of Marketing.": False,
}

# Where an UNSTYLED reference section ends. Without this the list ran to EOF and
# swallowed the AI declaration and acknowledgements that Step 8 tells the agent to
# add - losing those words from the count, in the unsafe direction.
LOOKS_REF = {
    "Smith, J. (2020). Widgets. Journal of Things, 4(2), 1-10.": True,
    "van Rooij, M., Lusardi, A., & Alessie, R. (2011). Financial literacy.": True,
    "[3] T. Nguyen, \"A survey,\" ACM, 2021.": True,
    "https://doi.org/10.1145/3442188.3445922": True,
    "Declaration of AI use": False,
    "Acknowledgements": False,
    "Appendix A": False,
}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fails = []

    for line, is_caption in CAPTIONS.items():
        got = is_caption_line(line)[0]
        if got != is_caption:
            fails.append(("caption", line, got, is_caption))

    for line, expected in REFS_HEADINGS.items():
        if bool(REFS_RE.match(line)) != expected:
            fails.append(("refs-heading", line, not expected, expected))

    for text, expected in INTEXT_STRIP.items():
        got = len(words(strip_intext(text)))
        if got != expected:
            fails.append(("strip_intext", text, got, expected))

    for line, expected in {**CORPORATE_CASES, **CORP2}.items():
        if looks_corporate(line) != expected:
            fails.append(("corporate", line, not expected, expected))

    for item, entry, expected in AUTHOR_CASES:
        if author_matches(item, entry) != expected:
            fails.append(("author-check", str(item)[:50], not expected, expected))

    for line, expected in LOOKS_REF.items():
        if looks_like_reference(line) != expected:
            fails.append(("looks-like-ref", line, not expected, expected))

    for line, expected in ENTRY_STARTS.items():
        if bool(ENTRY_START.match(line)) != expected:
            fails.append(("entry-start", line, not expected, expected))

    for text, expected in INTEXT.items():
        got = sorted(intext_authordate(text).keys())
        if got != sorted(expected):
            fails.append(("in-text", text, got, sorted(expected)))

    for entry, expected in REFS.items():
        got = ref_key(entry)
        if got != expected:
            fails.append(("ref_key", entry, got, expected))

    # End-to-end: whole script, whole document, exit code. Unit cases are blind to
    # the regression class that has now bitten three review rounds running.
    # The share link is pre-filled, never posted - so it must survive encoding
    # intact and must stay inside a length every browser will actually open.
    for n in (10, 500, 4000, 20000):
        u = share_url("A. Name", "role", "5", "x" * n, "1 Jan 2026")
        if len(u) > URL_BUDGET:
            fails.append(("share-url", f"comment of {n} chars", len(u), URL_BUDGET))
    # A rating with no comment must NOT emit a blockquote. Found by running the
    # Step 10 flow for real: "rating only" could not be stored without inventing a
    # comment, which then sat in the file formatted as something the user said.
    _r = share_url("A. Name", "role", "5", "", "1 Jan 2026")
    if "%3E" in _r:                       # an encoded ">" means a quote was emitted
        fails.append(("share-url", "rating-only must not emit a blockquote",
                      "quoted", "not quoted"))
    _u = share_url("Priya M.", "UQ finance", "5", "Caught a wrong DOI.", "1 Jan 2026")
    _q = urllib.parse.parse_qs(urllib.parse.urlsplit(_u).query)
    if "Caught a wrong DOI." not in _q.get("body", [""])[0]:
        fails.append(("share-url", "comment survives encoding", "no", "yes"))
    if _q.get("labels", [""])[0] != "testimonial":
        fails.append(("share-url", "labels", _q.get("labels"), "testimonial"))

    # Consent. The name must be absent from the publishable record by construction
    # on anything short of "named" - not filtered out later by a caller who has to
    # remember to. Each of these is one line of the promise the README makes.
    for _consent, _named in (("none", None), ("anon", False), ("named", True)):
        _rec = record("Priya M.", "UQ finance", "5", "Caught a wrong DOI.",
                      "1 Jan 2026", _consent)
        _pub = public_record(_rec)
        if _named is None:
            if _pub is not None:
                fails.append(("consent", "'none' must publish nothing",
                              _pub, None))
            continue
        if _pub is None:
            fails.append(("consent", f"'{_consent}' must be publishable", None, "a record"))
            continue
        if ("Priya M." in json.dumps(_pub)) != _named:
            fails.append(("consent", f"name under '{_consent}'",
                          _pub.get("name"), "Priya M." if _named else "Anonymous"))
        if "Caught a wrong DOI." not in json.dumps(_pub):
            fails.append(("consent", f"the words survive '{_consent}'", "lost", "kept"))
    # ...and must not ride along in the pre-filled link either, which is a second
    # place the name can escape and the one nobody looks at.
    _f = form_url("Priya M.", "UQ finance", "5", "Good.", "1 Jan 2026", "anon")
    if "Priya" in _f:
        fails.append(("consent", "anon form link carries the name", "leaked", "absent"))
    # A long comment must be trimmed, not deleted: subtracting the overflow once
    # cut roughly twice what was needed, because the comment appears twice.
    _long = form_url("A", "", "5", "word " * 400, "1 Jan 2026", "named")
    if len(_long) > URL_BUDGET or "word" not in _long:
        fails.append(("consent", "long comment trims rather than vanishes",
                      len(_long), f"<={URL_BUDGET} and non-empty"))

    # docxpatch. Both cases below are defects that reached working code and were
    # found by running the patcher against a real assignment, not by reading it.
    #
    # Word splits a reference across runs at every formatting change, so the journal
    # name and volume are italic and the issue, pages and DOI are not. The first
    # version replaced the whole matched span, which dumped all of it into the italic
    # run and silently italicised the page range and the DOI - an APA error created
    # by the tool that exists to fix APA errors.
    _SPLIT = ('<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">'
              'Journal of Service Research, 14</w:t></w:r>'
              '<w:r><w:t xml:space="preserve">(3), 252-271.</w:t></w:r>')
    _doi = " https://doi.org/10.1177/1094670511411703"
    _body, _hit = apply_to_paragraph(_SPLIT, "14(3), 252-271.", "14(3), 252-271." + _doi)
    _runs = [p["text"] for p in para_runs(_body)]
    if not _hit:
        fails.append(("docxpatch", "append across a run boundary", "no match", "applied"))
    elif _runs[0] != "Journal of Service Research, 14":
        fails.append(("docxpatch", "italic run must not absorb the append",
                      _runs[0], "Journal of Service Research, 14"))
    elif not _runs[1].endswith(_doi):
        fails.append(("docxpatch", "DOI lands in the roman run", _runs[1], "...+ doi"))

    # A pure insertion has zero width. The covered-run loop matched nothing at a run
    # boundary and reported failure while claiming success, which is the exact shape
    # of bug this whole skill is built to refuse.
    _b2, _h2 = apply_to_paragraph(_SPLIT, "(3), 252-271.", "(3), 252-271." + _doi)
    if not _h2 or _doi not in visible_text(_b2):
        fails.append(("docxpatch", "zero-width insertion at a run boundary",
                      _h2, "applied"))

    # Trimming to the minimal edit is what preserves the boundary; check it directly.
    for _o, _n, _want in (("abc", "abXc", (2, "", "X")),
                          ("2021", "2022", (3, "1", "2")),
                          ("same", "same", (4, "", ""))):
        _got = minimal_edit(_o, _n)
        if _got != _want:
            fails.append(("docxpatch", f"minimal_edit({_o!r},{_n!r})", _got, _want))

    # A substitution genuinely inside one run must still work, and must not disturb
    # its neighbour.
    _b3, _h3 = apply_to_paragraph(_SPLIT, "Service Research", "Service Marketing")
    if not _h3 or "Journal of Service Marketing, 14" not in visible_text(_b3) \
            or "(3), 252-271." not in visible_text(_b3):
        fails.append(("docxpatch", "substitution within one run", _h3, "applied cleanly"))

    # tablecheck. analyse() takes the flat document sequence, so the logic can be
    # exercised without building a .docx fixture for every case.
    def _seq(*items):
        out = []
        for it in items:
            out.append({"kind": "table", "rows": it[1]} if it[0] == "t"
                       else {"kind": "para", "text": it[1]})
        return out

    _ROWS = [["a", "b"], ["c", "d"]]
    _cases = [
        ("caption above is clean",
         _seq(("p", "Table 1. Results"), ("t", _ROWS), ("p", "See Table 1 for detail.")),
         0),
        ("caption below is a problem in APA",
         _seq(("t", _ROWS), ("p", "Table 1. Results"), ("p", "See Table 1 for detail.")),
         1),
        ("a table nobody refers to is flagged",
         _seq(("p", "Table 1. Results"), ("t", _ROWS), ("p", "Unrelated prose.")),
         1),
        ("ragged rows are flagged",
         _seq(("p", "Table 1. Results"), ("t", [["a", "b"], ["c"]]),
              ("p", "See Table 1.")), 1),
    ]
    for _label, _s, _want in _cases:
        _t, _p = tc_analyse(_s)
        if (len(_p) > 0) != bool(_want):
            fails.append(("tablecheck", _label, _p, "clean" if not _want else "a problem"))

    # Ten uncaptioned tables is ONE finding about the document, not ten about tables.
    # Reported per-table it buries the diagnosis under its own repetition.
    _many = []
    for i in range(4):
        _many += [{"kind": "para", "text": f"Appendix {i}"},
                  {"kind": "table", "rows": _ROWS}]
    _t, _p = tc_analyse(_many)
    if len(_p) != 1 or "NONE of the 4" not in _p[0]:
        fails.append(("tablecheck", "all-uncaptioned collapses to one finding",
                      len(_p), 1))
    # ...but a single missing caption among captioned tables must still be named.
    _mixed = _seq(("p", "Table 1. Good"), ("t", _ROWS), ("p", "See Table 1."),
                  ("p", "Some heading"), ("t", _ROWS))
    _t, _p = tc_analyse(_mixed)
    if not any("has no numbered caption" in x for x in _p):
        fails.append(("tablecheck", "one uncaptioned among captioned", _p, "named"))

    # stylecheck. A bold cell inside a table is not a hand-formatted heading; reading
    # it as one reported "Pass" and ".004" as headings on the first real document.
    def _p(text, bold=False, style="", in_table=False):
        return {"text": text, "style": style, "bold": bold,
                "words": len(text.split()), "in_table": in_table}

    _body = {"fonts": __import__("collections").Counter({"Calibri": 10}),
             "sizes": __import__("collections").Counter({11.0: 10}),
             "table_sizes": __import__("collections").Counter(),
             "spacings": __import__("collections").Counter({1.15: 5}),
             "margins": {}, "paras": [
                 _p("Results", bold=True, in_table=True),
                 _p("Some ordinary body prose that runs on for more than twelve words "
                    "so it reads as a paragraph."),
             ]}
    _pr, _ = sc_analyse(_body)
    if any("hand-formatted" in x or "heading styles" in x for x in _pr):
        fails.append(("stylecheck", "bold table cell is not a heading", _pr, "no finding"))

    # ...but a bold, unstyled, short paragraph followed by prose is one.
    _body2 = dict(_body, paras=[
        _p("Literature Review", bold=True),
        _p("Some ordinary body prose that runs on for more than twelve words so it "
           "reads as a paragraph."),
    ])
    _pr2, _ = sc_analyse(_body2)
    if not any("heading" in x for x in _pr2):
        fails.append(("stylecheck", "unstyled bold heading is flagged", _pr2, "flagged"))

    # A required section that is absent must be named.
    _pr3, _ = sc_analyse(_body, require=["Executive Summary"])
    if not any("Executive Summary" in x for x in _pr3):
        fails.append(("stylecheck", "missing required section named", _pr3, "named"))

    # discover. Both cases are misclassifications observed on the first real folder.
    #
    # Underscores are word characters, so \bproposal\b never matched inside
    # "RBUS3900_A1_Research_Proposal_DRAFT.docx" and the real draft scored no higher
    # than the research notes beside it.
    _txt = "Body text. " * 400 + "\nReferences\nSmith, J. (2020). Title. Journal."
    _r, _t, _d = disc_score("RBUS3900_A1_Research_Proposal_DRAFT.docx", _txt)
    _r2, _t2, _d2 = disc_score("A1-case5-scout.md", _txt)
    if _d <= _d2:
        fails.append(("discover", "underscored filename must score as a draft",
                      f"draft={_d} vs note={_d2}", "draft higher"))

    # A rubric must not be picked as the draft, however long it is.
    _rub = ("Criteria Exceptional Advanced Proficient Functional Unsatisfactory "
            "15% 25% 30% 15% 5% " + "band descriptor text " * 200)
    _r3, _t3, _d3 = disc_score("Assessment 1 Rubric.docx", _rub)
    if _r3 < 6 or _d3 >= _d:
        fails.append(("discover", "rubric must outscore as rubric, not as draft",
                      f"rubric={_r3} draft={_d3}", "rubric high, draft low"))

    # The offering is read from the text, because the filename lied on the real one.
    if disc_offering("RBUS3900 Semester 2, 2026\nAssessment 1") != "Semester 2, 2026":
        fails.append(("discover", "offering parsed from content",
                      disc_offering("RBUS3900 Semester 2, 2026"), "Semester 2, 2026"))

    fails.extend(e2e.run())

    total = (len(INTEXT) + len(REFS) + len(CAPTIONS) + len(REFS_HEADINGS)
             + len(INTEXT_STRIP) + len(ENTRY_STARTS) + len(CORPORATE_CASES)
             + len(CORP2) + len(AUTHOR_CASES) + len(LOOKS_REF) + e2e.total() + 33)
    print(f"markpilot selftest: {total - len(fails)}/{total} pass")
    for kind, src, got, exp in fails:
        print(f"  FAIL [{kind}] {src[:60]!r}")
        print(f"        got {got}   expected {exp}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
