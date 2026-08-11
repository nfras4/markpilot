# markpilot

A pre-submission gate for graded written work, as a [Claude Code](https://claude.com/claude-code) skill.

It grades a draft against the marking rubric using independent agents, fixes what falls
short, re-grades with fresh agents, and only then runs the finishing passes: reference
cross-matching, resolving every link and DOI, word count against the stated rule, figure
numbering, prose humanising, and the task sheet's AI-use policy.

> ### It refines a draft. It never invents evidence.
>
> Markpilot requires an existing document and stops if there is none. There is no
> "generate the assignment" path in this pipeline, by design. It closes the gap between a
> draft and the rubric it will be marked against — finding where a criterion is not met,
> saying so specifically, and tightening what is already there.
>
> Two rules, and only the first one bends. Where closing a gap needs **evidence the author
> has not gathered or a source they have not read**, it flags that as author-input-required
> and moves on — it will not invent a source, a statistic, a quotation or a page number,
> ever, and no setting changes that. Where the gap can be closed from material already on
> the page, it may write the argument, and then it has to account for it.
>
> That accounting is enforced, not asserted. Every change records its word delta. Every
> agent-written passage is logged **verbatim** in `authored.md` with the criterion it
> closed, and carried into the Step 8 AI-use declaration —
> which is built from that file rather than from recollection. The report carries a
> mandatory `AUTHORED` row naming both what was written and what was left unwritten because
> only the author could supply it.
>
> The point is not that a tool refuses to help. It is that you can always see exactly which
> sentences are yours, and declare the rest accurately.
>
> It also runs *toward* your institution's AI policy rather than around it: Step 8 reads
> the policy and helps you comply with it, and humanising the prose is never treated as a
> substitute for declaring. Whether this kind of assistance is permitted is your course's
> call, not this tool's.

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
git clone https://github.com/nfras4/markpilot ~/.claude/skills/markpilot
```

Then in Claude Code:

```
/markpilot assignment.docx --criteria rubric.pdf --task brief.pdf
```

### Optional: a better Step 6

Step 6 uses the [humanizer](https://github.com/blader/humanizer) skill if you have it — a
much fuller catalogue of AI writing tells than the dozen in `references/prose.md`. It is a
**soft dependency**: markpilot runs the pass itself when it is absent, and either spelling
of the skill name (`humanizer` or `humaniser`) is detected.

```bash
git clone https://github.com/blader/humanizer ~/.claude/skills/humanizer
```

Two things this does *not* mean. It is tuned for general-audience prose, so it is always
invoked under the clamp in [`references/prose.md`](references/prose.md) — a de-AI editor
that treats every dash as a tell will rewrite `pp. 118–142` and `2019–2021` into reference
errors, in the document whose references Step 3 just verified. And the report says which
editor ran, because a report that reads the same either way is telling you nothing about
the pass it describes.

## Pipeline

```
0  Intake            discover.py finds the draft, the rubric and the task sheet
1  Constraints       extract every hard rule the task sheet states
2  GRADE GATE        independent graders -> fix -> fresh graders -> loop to target
3  References        cross-match, verify every source, check quotes, format
4  Word count        against the stated rule and its stated exclusions
5  Presentation      figures, tables, styling, and whether the template was used
6  Humanise          prose cleanup under an academic clamp
7  Re-verify         humanising changed the prose AND the count - check both again
8  AI declaration    comply with the policy, listing what the agent wrote
8b Write back        docxpatch puts the accumulated fixes into the real document
9  Report            what passed, what changed, what is still on the author
```

**On a `.docx`, steps 2c to 7 edit extracted text, not your file.** Word documents are
zips; nothing here can edit one in place. Step 8b is what closes that gap, writing the
accumulated fixes back into the real document and re-running the counts against it. Without
that step the score describes a text file you do not submit, which is the single most
misleading thing this tool could do.

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
| `discover.py` | Points at a folder and works out which file is the draft, the rubric and the task sheet, from content rather than filenames |
| `docxpatch.py` | Writes accumulated text fixes back into the original `.docx`, run-aware, so the score describes the file you actually submit |
| `tablecheck.py` | Table numbering, caption position, cross-references, ragged rows — structure that does not survive text extraction |
| `stylecheck.py` | Fonts, sizes, spacing, margins, whether Word heading styles were used at all, and required sections |
| `export.py` + `pdfwrite.py` | Turns any report into a real `.docx` and a real `.pdf` — both written directly, no pandoc, no browser |
| `testimonial.py` | One-time, opt-in feedback. Stores locally; asks *may I quote this* and *may I use your name* as separate questions, and hands back a pre-filled link that needs no account |
| `selftest.py` | Regression cases over the parsing regexes, plus `e2e.py` — run it, it prints the count |

```bash
python scripts/doctext.py   report.docx --count --limit 2000 --exclude-refs --exclude-intext
python scripts/citecheck.py report.docx --style apa7
python scripts/linkcheck.py report.docx --json links.json
python scripts/figcheck.py  report.docx --source analysis.py
python scripts/doifind.py   report.docx
python scripts/quotecheck.py report.docx --list
python scripts/export.py    .markpilot/report.md      # -> .docx and .pdf
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

## Using it in claude.ai instead

There is a cut-down edition in [`web/`](web/) for plain Claude, where there is no shell and
no subagents. The mechanical checks are ported to JavaScript for the Analysis tool so the
numbers stay real; grading becomes a single self-assessed pass rather than three
independent graders, and bulk reference verification is not possible at all. Both losses
are stated in its output rather than papered over. See [`web/README.md`](web/README.md).

## What it will not do

- **It will not write your assignment.** It needs a draft to start, and where a rubric gap
  needs a position you have not taken or evidence you have not gathered, it says so instead
  of inventing it.
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
