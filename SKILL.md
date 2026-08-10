---
name: markpilot
description: |
  Pre-submission gate for an assignment, report, or graded piece of work. Grades the
  draft against the criteria sheet using independent agents, fixes what falls short,
  and re-grades with fresh graders, up to a set number of rounds, aiming to clear 95%.
  Then it runs the finishing passes: reference cross-matching, resolving every link
  and DOI to confirm the source is real and is the one cited, reference format, word
  count against the stated rule, figure numbering and charts that still look like
  untouched library output, humanising the prose, and complying with the task sheet's
  AI-use policy. Trigger on: "markpilot", "mark this", "grade this against the
  rubric", "is this ready to submit", "check this assignment", "will this get an HD",
  "pre-submission check", "run the rubric over this", or when handed a draft plus a
  criteria sheet.
argument-hint: "[document] [--criteria FILE] [--task FILE] [--style apa7] [--target 95] [--rounds 3] [--source plots.py] [--report-only] [--quick] [--no-humanise] [--no-figures]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - Agent
  - Skill
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# Markpilot

A draft is finished when an independent marker, holding the criteria sheet, cannot find
5% to take off it. Markpilot runs that check: it hands the work to graders who did not
write it, acts on what they find, re-checks with graders who have not seen the earlier
rounds, then clears the mechanical failures that sink otherwise-strong submissions.

## Two rules that govern everything below

**1. The grader is never the context that wrote or fixed the text.** Every grading pass
runs in a fresh subagent that receives only the criteria sheet, the task sheet, and the
document. It does not know what was changed or what the previous round scored. A context
that just spent twenty minutes fixing criterion 3 cannot then judge criterion 3.

**2. Never report as checked what was not checked.** Every script here can be handed a
document it cannot parse, and a parser that sees nothing produces output identical to a
clean document. That is why each one exits `2` for "could not check" — which is not a
pass — and why a step's report line must say what was actually confirmed rather than
what was attempted. If you are about to write "verified" about something nobody opened,
stop.

## Order of operations

The grade gate comes first: everything after it is polish, and polishing work that
scores 78% produces a well-polished 78%.

```
0  Intake            document, criteria sheet, task sheet, and the edit path
1  Constraints       extract every hard rule the task sheet states
2  GRADE GATE        independent graders -> fix -> fresh graders -> loop
3  References        cross-match, RESOLVE every link and DOI, check quotes, format
4  Word count        against the stated rule and its stated exclusions
5  Figures           numbering, cross-refs, charts that look pasted from a notebook
6  Humanise          /humaniser under the academic clamp
7  Re-verify         humanising changed the prose AND the count - check both again
8  AI declaration    comply with the task sheet's policy
9  Report            what passed, what you changed, what is still on the user
```

Step 7 is not optional. Humanising rewrites sentences a marker will grade and changes
the word count, so skipping it means the numbers from steps 2 and 4 no longer describe
the file being submitted.

### Script exit codes — the same contract everywhere

| Code | Meaning |
|---|---|
| `0` | checked, and clean |
| `1` | checked, and found problems that must be fixed |
| `2` | **could not check** — not a pass, and never reportable as one |

`doctext.py` is the exception: it is an extractor, not a checker, and only fails on an
unreadable file.

---

## Step 0 — Intake

You need three things. Ask for whatever is missing in one AskUserQuestion, not three.

| Input | Why | If absent |
|---|---|---|
| **The document** | the thing being graded | blocking — ask |
| **The criteria sheet / rubric** | the only definition of the target | blocking — ask. Never invent a rubric |
| **The task sheet / brief** | word limit, style, required sections, AI policy | ask once; if genuinely unavailable, mark steps 1, 4, 5 and 8 **unverified** in the report |

Look before you ask. Check the document's folder and its parent for `*rubric*`,
`*criteri*`, `*marking*`, `*task*`, `*brief*`, `*assessment*`, `*guide*`, `*spec*`.
Course material often lives outside the project directory — check OneDrive too.

### Reading each format

| Format | How |
|---|---|
| `.docx` | `python scripts/doctext.py FILE --text` and `--outline` |
| `.md` `.txt` `.html` `.rtf` | same |
| `.pdf` | the **Read** tool (`pages` for long ones). **No script here reads PDF** — they all exit 1 on one, which is not a finding about the document |
| `.doc` | not readable; ask for a `.docx` |
| a photo of a rubric | the Read tool reads images; transcribe the bands before grading |

**For a PDF, convert first.** Ask the user for the `.docx`, or extract the text with the
Read tool, save it as `.markpilot/<docname>/extracted.txt`, and run the scripts on that.
Say in the report that the checks ran on an extraction, because line and page fidelity
is lost.

### Settle the edit path before doing any work

Steps 2c, 3, 5 and 6 all modify the document. `Write`/`Edit` cannot modify a `.docx`
(it is a zip) or a `.pdf`. Decide now and tell the user which applies:

- **`.md` / `.txt` / `.html`** — edit in place. Copy to `<name>.markpilot-backup.<ext>`
  in the same folder **before the first edit**, which happens at Step 2c.
- **`.docx` / `.pdf`** — you cannot write to it. Produce
  `.markpilot/<docname>/changes.md` as an ordered, quotable list of edits — find-this,
  replace-with-that, with the section for each — for the user to apply. Say this at the
  start, not at the end. Do not silently convert their document to Markdown: that
  discards the formatting the task sheet requires.

Under `--report-only`, nothing is edited at any step; every step produces findings only.

Copy the rubric to `.markpilot/<docname>/rubric.md` before starting. Re-reading a PDF
every round wastes tokens and lets the criteria drift between rounds.

## Step 1 — Constraints

Write down every hard rule with the quote it came from, to
`.markpilot/<docname>/constraints.md`. Vague recall of a task sheet is how a submission
loses 10% to a formatting rule nobody re-read.

- **Word limit**, and — separately — **what it excludes**. "2000 words" and "2000 words
  excluding references and appendices" are different assignments. If exclusions are not
  stated, say so; do not assume references are excluded.
- **Whether the limit is hard or has a stated tolerance.** Most task sheets treat +10%
  as the penalty threshold, not a safe zone.
- **Referencing style**, exact edition. "APA" is not a style; APA 6 and APA 7 disagree.
- **Required sections**, and whether an executive summary, cover sheet or declaration
  is mandatory.
- **Format**: file type, spacing, font, margins, page limit, portal.
- **AI-use policy** — verbatim. See step 8.
- **Due date and late penalty.**
- **The actual question**, written out in full. A strong answer to a question that was
  not asked is the most expensive failure in graded work, and it is invisible from
  inside the draft.

## Step 2 — The grade gate

### 2a. Turn the rubric into a scoring table

Record per criterion: name, **weight**, and the **full text of the top band**.

Rubrics rarely award the top band for being correct. They award it for something extra —
critical evaluation over description, synthesis over listing, an original position,
engagement with counter-argument, application to this specific case. Note that extra
requirement per criterion; the gap between "correct" and "top band" is usually the whole
of the missing marks.

**If the rubric has no numeric weights** — bands only (HD/D/C/P), which is common — then
a percentage target is undefined. Say so, and convert the gate to: *every criterion sits
in the top band, and any that does not is named*. Do not invent weights to manufacture a
number.

### 2b. Grade with independent agents

Extract the text first: `python scripts/doctext.py FILE --text > .markpilot/<doc>/text.txt`.
Graders must receive readable text — a subagent handed a `.docx` path gets nothing —
and the same extraction must be reused every round so rounds compare like with like.

Spawn **three** graders in parallel, in one message, using `general-purpose`. Each gets
the brief from `references/grader-prompt.md`, close to verbatim, plus a distinct stance:

1. **Rubric literalist** — scores only what the descriptors say, quoting the descriptor
   matched for every score.
2. **Subject marker** — a domain expert judging whether the argument is sound, the
   evidence adequate, the method correct.
3. **Hostile second marker** — looking for the defensible reason to moderate *down*.

Write each grader's output to `.markpilot/<docname>/grades-round-N.md`. Step 7 needs the
per-criterion bands, and they cannot be reconstructed later.

**The governing score is the lowest of the three, not the average.** If any competent
marker would give it 88%, the work is at 88%.

**If the three disagree by more than about 8 points, the disagreement is itself the
finding.** Something is ambiguous enough that markers read it differently — usually an
argument whose position is unclear, or a section whose purpose the reader must infer.
Fix the ambiguity rather than the score.

**Say what this number is.** It is three language models reading a rubric, not a
measurement. Report it as an estimate, and never present it in the same register as the
word count, which is a fact. Under `--quick` only one grader runs; the report must then
say "1 grader, indicative only" and must not claim the work has cleared the gate.

### 2c. Fix

Work the gaps by `weight × band-gap`, highest cost first.

- Fix the substance before the sentences. A criterion sitting low because the analysis
  is descriptive is not fixed by better wording.
- Preserve the author's voice and argument. Where closing a gap needs a position they
  have not taken or evidence they have not gathered, **do not invent it** — flag it as
  author-input-required.
- Never invent a source, statistic, quote or page number.
- Log every change to `.markpilot/<docname>/changes.md` with the criterion it targets.
- Under `--report-only`, produce the change list and stop.

### 2d. Re-grade with fresh graders

New subagents, same brief, same three stances. They must not receive the change log, the
previous scores, or any argument about why the work is better.

Loop up to `--rounds` (default 3), where one round is one fix-and-regrade cycle — so the
default is up to four grading passes including the first.

**Keep the best draft.** Save each round's document alongside its score. Scores can go
down: a fix that closes one criterion can open another. If the final round scores lower
than an earlier one, restore the earlier version and say so.

**If it does not reach the target, say so plainly.** Report the governing score, the
criteria still short, and what each needs. Some gaps cannot be closed by editing —
missing primary data, a word limit that will not fit the required depth, a position only
the author can take. Name them. A skill that reports 95% because it ran out of rounds is
worse than useless.

## Step 3 — References

Three passes. The order matters, and the second is the one that catches fabrication.

### 3a. Cross-match

```bash
python scripts/citecheck.py FILE --style apa7
```

Cross-matches in-text citations against the reference list both ways: orphan citations,
year mismatches, uncited entries, duplicate entry numbers, per-style format smells. It
handles `et al.`, possessives, sentence-opening connectives, particle surnames
(`van Dijk`), non-ASCII names, wrapped/hanging-indent entries, secondary citations, and
initials-first styles.

Pass the **right `--style`**. An IEEE or Vancouver document run at the default `apa7`
can fall into author-date matching and report the entire reference list as uncited.

**Exit 2 means the parser found no citations or no reference list.** Read the reference
section by hand before saying anything about it.

### 3b. Resolve every link and DOI — mandatory, and a hard gate

```bash
python scripts/linkcheck.py FILE --json .markpilot/<docname>/links.json --timeout 20
```

Every URL is fetched and every DOI checked against Crossref, whose returned title, first
author and year are compared against the full reference entry — so this answers "does it
resolve to the source the entry claims", not merely "does it resolve".

| Status | Meaning | Verified? |
|---|---|---|
| `LIVE` | resolved; for a DOI, metadata matches the entry | **yes** |
| `DEAD` | 404/410 | no — fix or remove |
| `NOT-FOUND` | DOI not registered with Crossref — **likely fabricated** | no |
| `MISMATCH` | resolves to a *different* paper than the entry describes | no — worst kind |
| `SOFT-404` | HTTP 200 but the title reads as an error | no — open it |
| `REDIRECTED` | a deep link that landed on the site root | no — the cited page is probably gone |
| `BLOCKED` | 401/402/403/429/503 — bot protection or paywall | **no** — open it in a browser |
| `TIMEOUT` / `SSL` | no answer, 5xx, or a certificate failure | no — retry, then open it |
| `NO-DNS` | the host did not resolve | no — **check your own connection first** |

**`BLOCKED` is neither a pass nor a failure.** Springer, Elsevier, ScienceDirect, JSTOR,
Wiley and Taylor & Francis routinely return 403 to anything that is not a real browser.
Those references are usually fine — but "usually fine" is not verified. Never fold
`BLOCKED` into the LIVE count.

**If everything comes back `NO-DNS` or `TIMEOUT`, suspect the network, not the
document.** Say "reference resolution could not run" rather than reporting every source
as broken.

**`MISMATCH` outranks `DEAD` in severity.** A dead link is visibly broken. A DOI that
resolves cleanly to somebody else's paper looks perfect from every angle except the one
that matters.

### 3c. Check what no script can

Spot-check **every direct quote and every statistic**: that the page range exists, that
the quoted sentence appears in the source, that the finding attributed to the source is
one it reports. Use WebSearch/WebFetch for anything without a DOI — a title in quotes
that returns nothing anywhere is very likely invented.

Record the tally, because an agent that skips this produces a report identical to one
that did it: how many quotes and statistics there are, how many you checked, and which
you could not. That count goes in the report.

**Then format**, against the exact style and edition from Step 1, using
`references/referencing.md`. Fix mechanical errors. Where a fix would change what a
citation claims, ask rather than guess.

**The gate:** step 3 passes when `citecheck.py` and `linkcheck.py` both exit `0`, every
non-`LIVE` item has been individually opened and confirmed, and the quote/statistic
tally has no unchecked entries. Anything short of that is reported as unconfirmed, by
name. Never reformat an entry you could not verify — a well-formatted invented source is
still an invented source.

## Step 4 — Word count

```bash
python scripts/doctext.py FILE --count --limit 2000 --exclude-refs --exclude-intext
```

Available exclusions — pass **only** those the task sheet states, and say in the report
which rule you applied:

`--exclude-refs` `--exclude-appendix` `--exclude-headings` `--exclude-tables`
`--exclude-quotes` `--exclude-captions` `--exclude-footnotes` `--exclude-intext`

The count reports what each flag removed, **and warns when a flag removed nothing** —
usually a manually formatted heading the parser did not recognise. Investigate that
warning; do not report the number until you have.

There is no default tolerance: a stated limit is a limit. `--tolerance N` exists but
only use it when the task sheet states one, and report the signed delta as authoritative
over the WITHIN/OVER word. Do not use Word's own count as the authority — it counts
headings, captions, table contents and the reference list.

**If the count is over**, cut from the lowest-value material, never from a criterion the
rubric weights. Padding hides in the introduction, restated topic sentences, and long
block quotes that could be paraphrased.

**If cutting touches material Step 2c added**, you are removing what the graders
rewarded. Re-run the full three-grader gate afterwards, not the single regression grader
at Step 7. This collision is built into the order of operations — Step 2c adds, Step 4
measures — so expect it rather than discovering it.

## Step 5 — Figures and charts

Skip with `--no-figures`.

```bash
python scripts/figcheck.py FILE --source analysis.py notebook.ipynb
```

**Numbering and cross-references** (always): sequential numbers with no gaps or
duplicates, every figure captioned, every figure actually referred to in the prose.
Chapter numbering (`2.1`) and appendix series (`A1`) are handled as separate sequences.

**Chart-style tells** (with `--source`): explicit default-palette hex values, and — the
one that matters — plotting calls with *no styling anywhere in the file*. An untouched
matplotlib figure contains no hex literals at all, because the colours come from
rcParams rather than the source, so scanning for hex codes alone reports clean on
exactly the input this check exists to catch. Without `--source` nothing about styling
is checked, and the report must say so.

Then read `references/charts.md`, which is authoritative on chart styling. The headline
points: match the document's body font and text-column width so the figure needs no
rescaling; stay legible in greyscale because markers print; captions below figures and
above tables, each cited in the text and carrying a source citation when the data is
someone else's.

For chart selection and colour theory beyond that, load the bundled **`dataviz`** skill.

**The limits of this step.** A restyled chart has to be re-exported and re-inserted, and
neither is possible for a `.docx` or `.pdf` from here — produce the corrected plotting
code and the instruction in `changes.md` and let the author re-run it. Do not regenerate
a chart you cannot reproduce: without the plotting code or the data, restyling means
redrawing from numbers read off the page, which risks changing what the chart claims.
**Never adjust a data point, an axis range, or a trendline to make a chart look
tidier** — that is falsification, not formatting, and it is the one edit in this pipeline
that turns a presentation problem into a misconduct finding.

## Step 6 — Humanise

Skip with `--no-humanise` (which also skips the re-grade in Step 7).

Invoke the `humaniser` skill on the body prose — the argument, discussion and
conclusion. **Not** the abstract or executive summary unless the rubric scores its
style, and never quotations, citations, reference entries, data, captions or headings.

**Under the academic clamp.** Humaniser is tuned for natural, general-audience writing
and strips several things academic marking rewards. Pass these constraints explicitly:

- **Keep hedging on empirical claims.** "The results suggest" is accurate, not weak;
  overclaiming loses marks that caution does not.
- **Keep structural signposting** where the rubric or discipline expects it. Some
  criteria award marks for exactly the "This section examines…" sentences it would cut.
- **Keep formal register and discipline terminology.** Precision is being graded.
- **Keep passive voice in methods** where the convention calls for it.
- **Do not change the word count materially** — flag it if a rewrite would.

What it should remove is real and worth removing: em-dash overuse, "delve", "tapestry",
"testament to", "underscores the importance of", rule-of-three cadence, promotional
filler, and empty paragraphs that restate the previous three.

## Step 7 — Re-verify

Humanising changed the graded prose and the word count. So:

1. Re-run the word count.
2. Run **one** fresh grader with the regression brief in `references/grader-prompt.md`.

**The baseline is the per-criterion minimum band across the three graders from the final
round of Step 2** — read it from `grades-round-N.md`, not from memory, and not from the
overall percentage, which cannot tell you which criterion moved.

Any criterion the regression grader does not re-confirm at its baseline band gets named
in the report. Do not print a blanket "no criterion dropped": a lenient single grader
produces that sentence for free. If one dropped, restore the specific sentences that
carried it — the rubric beats style every time.

## Step 8 — AI-use declaration

Find the policy in the task sheet or course profile and quote it verbatim.

| Policy | What to do |
|---|---|
| **AI prohibited** | Say so plainly. The work has had AI assistance through this pipeline and the user needs to know before submitting. Do not proceed as though the policy said something else. |
| **Permitted with declaration** | Draft the declaration in the required format and location, accurately describing what was used and for what — drafting, editing, grading, reference checking. |
| **Permitted, must be cited** | Cite the tool as a source (APA 7 has a form; see `references/referencing.md`). |
| **No policy found** | Say no policy was found, name where you looked, recommend checking the course profile. Do not assume permission. |

**Markpilot helps you declare AI use. It does not help you hide it.** If a declaration
is required, the finishing passes here — humanising in particular — are not a substitute
for making one, and the report must say so. That line is not negotiable by flag.

## Step 9 — Report

```
MARKPILOT — <document>
──────────────────────────────────────────────
GRADE      96% estimated  (round 2 of 3; lowest of 3 independent graders; spread 4pts)
           lit-review 14/15 · analysis 29/30 · evidence 19/20 · structure 10/10
           An LLM panel's estimate against the rubric, not a measurement.

WORDS      1,847 / 2,000  (rule: excl. references, per task sheet p.2; no tolerance)
REFS       18 entries · 0 orphans · 0 uncited · 2 format fixes        citecheck exit 0
LINKS      16/18 LIVE · 2 BLOCKED, opened by hand and confirmed (Wiley, JSTOR)
           0 dead · 0 mismatched · 0 unconfirmed                     linkcheck exit 0
QUOTES     7 direct quotes, 4 statistics · 11/11 checked against source
FIGURES    3 figures · 1 table · numbered, captioned, all cross-referenced
           2 charts were pure library default → corrected code in changes.md
PROSE      humanised · 12 tells removed · all criteria re-confirmed at baseline band
AI POLICY  declaration required (task sheet §4) → drafted, in appendix A

CHANGED    <n> edits, logged in .markpilot/<doc>/changes.md
STILL ON YOU
  · <thing only the author can decide or supply>
  · <anything left unconfirmed, by name>
```

Report the governing (lowest) score, not the flattering one. The LINKS numerator can
never exceed the script's `LIVE` count. Any step skipped, or run under `--report-only`,
or that exited `2`, appears in the report as such — never as a pass.

## Flags

| Flag | Effect |
|---|---|
| `--criteria FILE` | path to the rubric, if not auto-found |
| `--task FILE` | path to the assignment brief |
| `--style` | `apa7`, `harvard`, `ieee`, `chicago`, `mla`, `vancouver`, `aglc`, `unknown` |
| `--target N` | gate threshold, default 95. Used in 2a/2d and stated in the report |
| `--rounds N` | max fix-and-regrade cycles, default 3 |
| `--source FILE…` | plotting source to scan in step 5 |
| `--report-only` | change nothing at any step; findings only |
| `--quick` | one grader instead of three. Report must say "indicative only" and must not claim the gate was cleared |
| `--no-humanise` | skip step 6 and its re-grade |
| `--no-figures` | skip step 5 |
| `--link-timeout N` | seconds per fetch, default 20 — raise on a slow connection |

## Files

Written under `.markpilot/<docname>/`: `rubric.md`, `constraints.md`, `text.txt`,
`grades-round-N.md`, `links.json`, `changes.md`, `report.md`.

`scripts/selftest.py` (78 cases) guards the parsing regexes, which are the fragile part
of this skill — several of those cases are defects that reached working code. Run it
after editing any regex in `doctext.py`, `citecheck.py` or `figcheck.py`.
