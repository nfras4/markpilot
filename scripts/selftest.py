#!/usr/bin/env python3
"""selftest.py - run before trusting citecheck.py after any edit to its regexes.

    python selftest.py

Every case below is a bug that was actually observed during development, not a
hypothetical. The citation regexes are the fragile part of this skill: a change
that looks harmless (adding a co-author branch, widening the year pattern) has
repeatedly broken an unrelated case. Nine of these were live defects.

Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e  # noqa: E402
import urllib.parse  # noqa: E402
from testimonial import share_url, URL_BUDGET  # noqa: E402
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

    fails.extend(e2e.run())

    total = (len(INTEXT) + len(REFS) + len(CAPTIONS) + len(REFS_HEADINGS)
             + len(INTEXT_STRIP) + len(ENTRY_STARTS) + len(CORPORATE_CASES)
             + len(CORP2) + len(AUTHOR_CASES) + len(LOOKS_REF) + len(e2e.CASES) + 7)
    print(f"markpilot selftest: {total - len(fails)}/{total} pass")
    for kind, src, got, exp in fails:
        print(f"  FAIL [{kind}] {src[:60]!r}")
        print(f"        got {got}   expected {exp}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
