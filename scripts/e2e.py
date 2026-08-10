#!/usr/bin/env python3
"""e2e.py - end-to-end cases: document in, exit code out.

    python e2e.py            (or let selftest.py call run())

Why this exists separately from selftest.py
-------------------------------------------
selftest.py exercises functions in isolation against APA-shaped strings. Three
separate rounds of review found defects it could not possibly see, because the
failure only appears when a whole script reads a whole file:

  - a numbered reference list made citecheck abandon author-date checking and
    print "OK" on a document with three real defects;
  - a Chicago reference (given name spelled out) was classified as grey
    literature and never looked up;
  - a two-line-caption fix carried an ordinary body sentence and turned a real
    finding into a pass;
  - an unstyled reference section swallowed the AI declaration after it.

Each of the last three was a REGRESSION introduced by a fix for something else.
Isolated unit cases are blind to that class, so every one of them gets a whole
document here.

Network scripts (linkcheck.py, doifind.py) are deliberately excluded: this must
run offline and be safe to call in a loop.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CASES = [
    # (label, filename, content, argv-after-script, expected exit)
    (
        "numbered APA list must not silently switch to numeric mode",
        "numbered.md",
        "# Body\n"
        "Smith (2020) found an effect. Jones (2019) disagreed, as did Lee (2018).\n"
        "The instrument is in Appendix [1] and Appendix [2].\n"
        "# References\n"
        "1. Smith, J. (2020). Widgets and things. Journal of Things, 4(2), 1-10.\n"
        "2. Nobody, X. (2001). A source never cited anywhere in the body.\n",
        ["citecheck.py", "{f}", "--style", "apa7"], 1,
    ),
    (
        "an unstyled reference section ends at the AI declaration after it",
        "unstyled.txt",
        "Body words here (Smith, 2020) and more prose to count.\n"
        "References\n"
        "Smith, J. (2020). Widgets. Journal of Things, 4(2), 1-10.\n"
        "Declaration of AI use\n"
        "Generative AI was used to check grammar only and no generated text "
        "appears anywhere in this submission.\n",
        ["citecheck.py", "{f}", "--style", "apa7"], 0,
    ),
    (
        "an html table cell reading 'Reference' must not hijack the document",
        "table.html",
        "<html><body><h1>Intro</h1><p>Body words here and some more prose.</p>"
        "<table><tr><td>Reference</td><td>Definition</td></tr>"
        "<tr><td>Smith 2020</td><td>a thing</td></tr></table></body></html>\n",
        ["doctext.py", "{f}", "--count", "--exclude-tables"], 0,
    ),
    (
        "possessive apostrophes are not quotations",
        "apos.md",
        "The board's strategy shifted after the regulator's review of the "
        "firm's segments.\n",
        ["quotecheck.py", "{f}", "--list"], 2,
    ),
    (
        "a body sentence must not be carried as a missing caption",
        "captheft.md",
        "See Figure 1.\n\nFigure 1\n\nThis is an ordinary body sentence that "
        "follows the figure and is definitely not its caption at all.\n",
        ["figcheck.py", "{f}"], 1,
    ),
    (
        "a real APA caption on the following line IS carried",
        "apacap.md",
        "See Figure 1.\n\nFigure 1\nEngagement Rate by Cohort\n",
        ["figcheck.py", "{f}"], 0,
    ),
    (
        "no figures detected is could-not-check, not clean",
        "nofig.md",
        "Just prose, nothing numbered here at all.\n",
        ["figcheck.py", "{f}"], 2,
    ),
    (
        "--claims and --list together must refuse, not discard one",
        "both.md",
        "Some prose with \"a quoted span of several words here\" in it.\n",
        ["quotecheck.py", "{f}", "--claims", "{f}", "--list"], 2,
    ),
    (
        "a missing --source path is could-not-check, not a clean chart bill",
        "src.md",
        "See Figure 1.\n\nFigure 1. A caption\n",
        ["figcheck.py", "{f}", "--source", "does_not_exist_anywhere.py"], 2,
    ),
    (
        "testimonial --save refuses when there is nothing to save",
        "unused.md", "x\n",
        ["testimonial.py", "--save", "--name", "X"], 2,
    ),
    (
        "an unreadable document exits 2, never 1",
        "broken.docx",
        "this is not a zip archive\n",
        ["doctext.py", "{f}", "--count"], 2,
    ),
]


def run():
    """Returns a list of (kind, label, got, expected) failures."""
    fails = []
    with tempfile.TemporaryDirectory() as d:
        for label, name, content, argv, expect in CASES:
            path = os.path.join(d, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            cmd = [sys.executable, os.path.join(HERE, argv[0])]
            cmd += [a.format(f=path) for a in argv[1:]]
            got = subprocess.run(cmd, capture_output=True).returncode
            if got != expect:
                fails.append(("e2e", label, got, expect))
    return fails


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bad = run()
    print(f"e2e: {len(CASES) - len(bad)}/{len(CASES)} pass")
    for _, label, got, exp in bad:
        print(f"  FAIL {label}\n        exit {got}, expected {exp}")
    sys.exit(1 if bad else 0)
