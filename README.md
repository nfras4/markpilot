# markpilot

A pre-submission gate for graded written work, as a [Claude Code](https://claude.com/claude-code) skill.

It grades a draft against the marking rubric using independent agents, fixes what falls
short, re-grades with fresh agents, and only then runs the finishing passes: reference
cross-matching, resolving every link and DOI, word count against the stated rule, figure
numbering, prose humanising, and the task sheet's AI-use policy.

Everything mechanical is a script. Python 3.8+, standard library only — no `pip install`,
no dependencies, no API keys. Only link resolution and DOI lookup touch the network.

---

## The two rules it is built around

**The grader is never the context that wrote the text.** Every grading pass runs in a
fresh subagent that receives only the rubric, the task sheet and the document — no change
log, no previous score, no argument for why it is better now. A context that just spent
twenty minutes fixing criterion 3 cannot then judge criterion 3.

**Never report as checked what was not checked.** A parser handed a document it cannot
read produces output identical to a clean document. So every script exits `2` for *could
not check*, which is not a pass, and each step reports what was actually confirmed rather
than what was attempted. `BLOCKED` links are never folded into the verified count.

## Install

Clone into your Claude Code skills directory:

```bash
git clone https://github.com/<you>/markpilot ~/.claude/skills/markpilot
```

Then in Claude Code:

```
/markpilot assignment.docx --criteria rubric.pdf --task brief.pdf
```

## Pipeline

```
0  Intake            document, criteria sheet, task sheet, and the edit path
1  Constraints       extract every hard rule the task sheet states
2  GRADE GATE        independent graders -> fix -> fresh graders -> loop
3  References        cross-match, RESOLVE every link and DOI, check quotes, format
4  Word count        against the stated rule and its stated exclusions
5  Figures           numbering, cross-refs, charts that look pasted from a notebook
6  Humanise          prose cleanup under an academic clamp
7  Re-verify         humanising changed the prose AND the count - check both again
8  AI declaration    comply with the task sheet's policy
9  Report            what passed, what changed, what is still on the author
```

The grade gate runs first because it is the only step that changes the substance. The
steps after it are mechanical, and fixing them does not move a rubric criterion.

## The scripts

All of them take a `.docx`, `.md`, `.txt`, `.html` or `.rtf`. None reads PDF — convert first.

| Script | Does |
|---|---|
| `doctext.py` | Text extraction, document outline, and structure-aware word counts with itemised exclusions |
| `citecheck.py` | Cross-matches in-text citations against the reference list, both directions |
| `linkcheck.py` | Resolves every URL and DOI; compares Crossref metadata against the reference entry |
| `figcheck.py` | Figure/table numbering and cross-references; default-chart-styling tells |
| `doifind.py` | Looks up missing DOIs in Crossref and flags online-vs-issue year splits |
| `quotecheck.py` | Verifies quoted evidence exists in the document; lists the document's own quotations |
| `selftest.py` | Regression cases over the parsing regexes — run it, it prints the count |

```bash
python scripts/doctext.py   report.docx --count --limit 2000 --exclude-refs --exclude-intext
python scripts/citecheck.py report.docx --style apa7
python scripts/linkcheck.py report.docx --json links.json
python scripts/figcheck.py  report.docx --source analysis.py
python scripts/doifind.py   report.docx
python scripts/quotecheck.py report.docx --list
```

Exit codes: `0` clean, `1` problems found, `2` **could not check** — which is never a
pass. Unreadable input always exits `2`, because nothing was read and so nothing can be
claimed. `linkcheck` exiting `2` is routine for any document citing a paywalled
publisher: `BLOCKED` means a human must open it, not that the link is broken.

### Link and DOI resolution

DOIs are checked against Crossref rather than by fetching `doi.org`, because Crossref
returns the record's real title, first author and year. Those are compared against the
reference entry, so the check answers *does this resolve to the source the entry claims* —
not merely *does this resolve*.

A DOI that resolves cleanly to somebody else's paper is treated as more severe than a
dead link. A dead link is visibly broken; a mismatched one looks perfect from every angle
except the one that matters.

Status categories are kept deliberately separate:

| Status | Verified? |
|---|---|
| `LIVE` | **yes** |
| `DEAD` `NOT-FOUND` `MISMATCH` | no — must be fixed |
| `SOFT-404` `REDIRECTED` `BLOCKED` `TIMEOUT` `SSL` `NO-DNS` | no — a human must open it |

`BLOCKED` (401/402/403/429/503) is neither a pass nor a failure. Springer, Elsevier,
ScienceDirect, JSTOR, Wiley and Taylor & Francis routinely return 403 to anything that is
not a real browser. Those references are usually fine — but "usually fine" is not
verified, so they never count toward the LIVE total. `NO-DNS` is separated for the same
reason in reverse: a name that will not resolve is evidence about your network, not about
the reference.

### Chart-styling detection

Two signals, and the second is the one that matters:

1. Library default palette hex values written out explicitly (`#1f77b4` matplotlib,
   `#4C72B0` seaborn, `#4472C4` Excel, `#636EFA` Plotly).
2. **Plotting calls with no styling anywhere in the file.**

An untouched matplotlib figure contains no hex literals at all — the colours come from
rcParams, not the source — so scanning for hex codes alone reports "clean" on precisely
the input the check exists to catch. Writing a hex value is evidence somebody made a
colour decision. Writing none is evidence nobody did.

## What it will not do

- **It will not help hide AI use.** Step 8 finds the task sheet's AI policy and helps you
  comply with it. If a declaration is required, the report says so, and humanising the
  prose is not treated as a substitute for making one.
- **It will not touch your data.** Charts are restyled, never re-plotted from numbers read
  off the page, and no data point, axis range or trendline is ever adjusted to make a
  chart look tidier.
- **It will not invent a source, a statistic, a quote or a page number**, and it will not
  reformat a reference it could not verify — a well-formatted invented source is still an
  invented source.
- **It will not claim a score it did not get.** If the work does not reach the target
  within the round budget, it reports the real number and what each short criterion needs.

## On the grade itself

The score is three language models reading a rubric. It is an estimate, not a
measurement, and the report says so. The governing figure is the **lowest** of the three,
not the average — if one competent grader can reach 88%, then 88% is a possible outcome
of submitting.

The three graders are the same model under three prompt stances, so they are correlated
rather than independent, and the minimum buys less spread than it appears to. The hedge:
when they disagree by more than about 8 points, that disagreement is itself the finding —
something in the work is ambiguous enough that markers read it differently.

## Contributing

The parsing regexes are the fragile part. Run `python scripts/selftest.py` after touching
any of them. Most cases are defects that reached working code:
`n.d.` matching the "nd" inside "and", `Nguyen et al. (2021)` going undetected entirely,
`However, Nguyen…` keying on "However", `summaris\b` failing to match "summarises",
surnames like An, So and Ho being filtered out as stopwords, and `[3]–[7]` ranges
reporting their interior numbers as uncited.

## Licence

MIT. See [LICENSE](LICENSE).

Referencing guidance is drawn from the published style manuals (APA 7, Harvard, IEEE,
Vancouver, Chicago, MLA, AGLC 4). The colourblind-safe palette in `references/charts.md`
is Okabe–Ito, as published in Wong, B. (2011), *Nature Methods*, 8(6), 441.
