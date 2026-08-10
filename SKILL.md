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
  criteria sheet. Refines an EXISTING draft - it never generates an assignment,
  and it flags anything needing the author's own position or evidence rather
  than inventing it.
argument-hint: "[document] [--criteria FILE] [--task FILE] [--style apa7] [--target 95] [--rounds 3] [--format both] [--source plots.py] [--budget FILE] [--report-only] [--quick] [--no-humanise] [--no-figures] [--no-backfill]"
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

## What this is, and what it is not

**Markpilot refines a draft you have already written. It does not write one.**

It needs an existing document at Step 0 and stops if there is none — there is no "generate
the assignment" path anywhere in this pipeline, by design. What it does is close the gap
between a draft and the rubric it will be marked against: find where a criterion is not
met, say so specifically, and tighten what is already there.

The line it will not cross: where closing a gap would need **a position the author has not
taken, evidence they have not gathered, or a source they have not read**, it flags that as
author-input-required and moves on. It does not supply the argument. Step 2c says this
plainly and every fix pass is bound by it, because the difference between refining someone's
work and writing it for them is exactly that line.

It also will not invent a source, a statistic, a quote or a page number; will not adjust a
data point to tidy a chart; and will not help conceal AI use where a declaration is
required. Those are not configurable.

Used as intended, the AI assistance here is drafting-and-editing support of the kind most
institutions permit **and require you to declare** — which is what Step 8 is for. Whether
that is allowed in your course is your course's call, not this tool's, and Step 8 goes and
reads the policy rather than assuming.

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

The grade gate comes first because it is the only step that changes the substance. The
steps after it are mechanical, and fixing them does not move a rubric criterion.

```
0  Intake            document, criteria sheet, task sheet, and the edit path
1  Constraints       extract every hard rule the task sheet states
2  GRADE GATE        independent graders -> fix -> fresh graders -> loop
3  References        cross-match, RESOLVE every link and DOI, check quotes, format
4  Word count        against the stated rule and its stated exclusions
5  Figures           numbering, cross-refs, charts that look pasted from a notebook
6  Humanise          the humanizer skill under the clamp, or inline and said so
7  Re-verify         humanising changed the prose AND the count - check both again
8  AI declaration    comply with the task sheet's policy
9  Report            what passed, what you changed, what is still on the user
```

Step 7 is not optional. Humanising rewrites sentences a marker will grade and changes
the word count, so skipping it means the numbers from steps 2 and 4 no longer describe
the file being submitted.

### Script exit codes

| Code | Meaning |
|---|---|
| `0` | checked, and clean |
| `1` | checked, and found problems that must be fixed |
| `2` | **could not check** — not a pass, and never reportable as one |

Unreadable input (a PDF, a corrupt `.docx`, a missing file) always exits `2`, in every
script: nothing was read, so nothing can be claimed. What each `2` means specifically:

| Script | `2` means |
|---|---|
| `citecheck` | no reference list found, or no citations detected |
| `linkcheck` | something needs a human (BLOCKED/TIMEOUT/SSL/NO-DNS/REDIRECTED/SOFT-404), **or** most of the reference list carried no identifier |
| `figcheck` | no figures detected, or a `--source` path was missing |
| `doifind` | entries left unmatched, or the whole list was grey literature |
| `quotecheck` | no quoted spans to compare, or some were too long/short to check |
| `doctext` | the file could not be read (it is an extractor; it does not judge) |

**`linkcheck` exiting `2` is the normal case for any document citing a paywalled
publisher**, because BLOCKED counts as needs-a-human. That is working correctly, not
failing — see the Step 3 gate.

---

## Step 0 — Intake

You need three things, plus one preference. **Ask in a single AskUserQuestion call** —
one call carrying several questions, not several calls. Do not ask them one at a time
across separate turns.

**Always ask the export format**, even when every input was found automatically. It is the
one thing that cannot be inferred, it decides what the user actually receives at Step 9,
and asking at the end means re-running the export after they have stopped paying attention.

| Question | Options |
|---|---|
| How should the report be delivered? | **Word (.docx)** · **PDF** · **Both** · Markdown only |
| How many fix-and-regrade rounds? | **1 (one pass)** · **3 (default)** · **Until it clears the target (max 6)** · **0 — report only** |

Ask both **before the grade gate starts**, not after. Each round costs three graders and a
fix pass, and a user who wanted one pass should not discover that after four have run.
Skip the rounds question only if `--rounds` or `--report-only` was passed explicitly.

On the rounds options:

- **1** — grade, fix once, regrade. Enough to catch the obvious gaps.
- **3** — the default. Diminishing returns beyond it in practice.
- **Until it clears (max 6)** — the cap is not arbitrary. **Scores can go down**: a fix that
  closes one criterion can open another, so "keep going until it clears" is not monotonic
  and can oscillate. Keep the best-scoring draft (Step 2d) and stop at 6 regardless,
  reporting the best round rather than the last.
- **0** — behaves as `--report-only`: findings, no edits.

Record both answers in `constraints.md` and honour them. Notes on the export options:

- **Word** — a real `.docx`, editable, good if they want to paste findings into their own
  notes.
- **PDF** — a real `.pdf`, written directly, no browser step. Fixed layout, good for
  sending to someone or printing. Non-Latin characters degrade to ASCII, because base-14
  PDF fonts have no glyphs for them; if the report will contain any, add `--html` and let
  the browser's own PDF export handle it.
- **Both** is the safe default when they have no preference.
- **Markdown only** if they will read it in the terminal or a notes app.

Now the inputs:

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
| `.pdf` | the **Read** tool (`pages` for long ones). **No script here reads PDF** — they exit `2` (could not check), which is not a finding about the document |
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
- **`.docx` / `.pdf`** — you cannot write to it. From Step 2c the artefact you edit
  and re-grade is `.markpilot/<docname>/draft-round-N.txt`: the extracted text with
  that round's fixes applied. `changes.md` is then **derived from the diff** against
  `text.txt`, as an ordered find-this/replace-with-that list for the user to apply.

  This matters because without it the fix-and-regrade loop cannot run at all — round 2
  would re-grade byte-identical text and any improvement it reported would be noise.

  The report must carry a `SOURCE` line saying the user's file is unmodified and which
  working text the numbers describe. Do not silently convert their document to
  Markdown: that discards the formatting the task sheet requires.

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

### If there is no rubric at all

This is common and it is not a reason to stop. Many courses publish no A1 rubric; the
detail lives in the briefing deck instead. Do **not** invent criteria, and do **not**
report a percentage.

Build a **requirements checklist** from the task sheet instead — every "must contain",
every required section, every stated word budget, every named appendix — and run the
graders against that. Their question becomes *is each required element present and
adequate*, not *what mark is this*.

Report it as **requirements compliance, not a grade**, with no percentage anywhere, and
say plainly that no rubric was available and where you looked. A compliance pass is
genuinely useful — most marks lost on a proposal are lost to a missing required element,
not to weak argument — but it is a different claim, and presenting it as a grade would be
a fabrication.

Then tell the user the rubric is worth chasing, because the grade gate is the part of
this pipeline that actually predicts the mark.

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

Write each grader's output to its own file, `.markpilot/<docname>/grades-round-N-<stance>.md` (three parallel subagents cannot share one path). Step 7 needs the
per-criterion bands, and they cannot be reconstructed later.

**Verify the evidence before trusting the score.** The brief demands a quoted span for
every criterion; nothing stopped a grader inventing one, and invented evidence produces
output identical to real evidence.

```bash
python scripts/quotecheck.py .markpilot/<doc>/text.txt --claims .markpilot/<doc>/grades-round-N-<stance>.md
```

Exit `1` means a grader quoted something not in the document. Re-run that grading pass;
do not act on its findings. (Check first for an extraction artefact — a quote spanning a
table cell may be real but unreachable in the extracted text.)

**The governing score is the lowest of the three, not the average.** If any competent
marker would give it 88%, the work is at 88%. The target is `--target` (default 95);
state the target you used in the report, since a different one changes what "cleared"
means.

**If the three disagree by more than about 8 points, the disagreement is itself the
finding.** Something is ambiguous enough that markers read it differently — usually an
argument whose position is unclear, or a section whose purpose the reader must infer.
Fix the ambiguity rather than the score.

**Say what this number is.** It is three language models reading a rubric, not a
measurement. Report it as an estimate, and never present it in the same register as the
word count, which is a fact. Under `--quick` only one grader runs — use the **hostile second marker** stance, the
only one defensible alone — and the report must say "1 grader, indicative only"
and must not claim the work has cleared the gate.

### 2c. Fix

Work the gaps by `weight × band-gap`, highest cost first.

- Fix the substance before the sentences. A criterion sitting low because the analysis
  is descriptive is not fixed by better wording.
- Preserve the author's voice and argument. Where closing a gap needs a position they
  have not taken, evidence they have not gathered, or a source they have not read,
  **do not invent it** — flag it as author-input-required and move on. This is the line
  between refining the author's work and writing it for them, and it is not negotiable by
  flag or by how close the score is to the target.
- Never invent a source, statistic, quote or page number.
- **Never introduce a claim the document's own sources do not support.** This is a
  separate rule from the one above and it is the one that actually gets broken. Inventing a
  *source* feels like cheating and is easy to avoid; inventing a *synthesis* — "these two
  studies differ because they measure collaboration-heavy work" — feels like analysis, is
  exactly what the top band asks for, and can be flatly contradicted by the draft's own
  literature review. Every new sentence must trace to something already on the page.

  This is not hypothetical. In the first end-to-end test of this loop, the fix pass added a
  categorisation of that shape, and two of the three round-2 graders independently rejected
  it — "inference dressed as established fact", "asserted, not shown" — because one of the
  studies it grouped plainly did not fit. The fix *raised* the score while introducing a
  defect a careful marker would catch.

- **Read the next round's grades for damage, not just for progress.** If a fresh grader
  flags something the previous fix pass wrote, revert that change rather than defending it.
  The graders never saw the change log, so a finding that lands on new material is the
  cleanest possible signal that the material was wrong.
- Log every change to `.markpilot/<docname>/changes.md` with the criterion it targets
  **and its word delta** — `+18 / −4`, per change. The running total is what makes the
  next rule checkable instead of aspirational.
- Under `--report-only`, produce the change list and stop.

### The authorship ceiling — this is the enforcement, not the prose above

Tightening someone's sentence and writing their argument are both "edits", and an edit
count cannot tell them apart. So:

1. **Track net words authored** across all rounds: additions minus deletions, from
   `changes.md`. Carry it into the Step 9 `AUTHORED` row, which is mandatory.
2. **At +150 net words, stop and ask.** Use AskUserQuestion: show which criteria the new
   material closed and what it says, and let the author accept it, rewrite it themselves,
   or drop it. Do not resume adding until they answer.
3. **A criterion flagged author-input-required stays flagged.** Later rounds may not
   quietly close it by writing the missing position. If the author has not supplied it,
   it is still open at Step 9 and the score is reported with that criterion short.
4. **If the reported score depends on agent-written material, say so in the report** —
   name the criteria concerned on the `AUTHORED` row.

The failure this prevents is specific and easy to walk into: Step 2a tells you the top
band wants "an original position", Step 2c tells you to close the highest-weighted gap,
and the loop only stops when the score clears the target. Writing 400 words of evaluation
using sources the author already cited breaks none of the individual prohibitions and
lands squarely on the wrong side of the line the skill claims to hold. The ceiling is
what makes the claim true.

### 2d. Re-grade with fresh graders

New subagents, same brief, same three stances. They must not receive the change log, the
previous scores, or any argument about why the work is better.

Loop up to the number chosen at Step 0 (or `--rounds`, default 3), where one round is one
fix-and-regrade cycle — so 3 rounds is up to four grading passes including the first. An
explicit `--rounds` on the command line overrides the interview answer; say which governed
in the report.

If the user chose **until it clears**, stop at **6** regardless and report the best round.
The cap exists because the loop is not monotonic — see below.

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

### 3c. Backfill missing identifiers

If REFERENCE COVERAGE is short, most of the list cannot be verified by anything. Close
that gap before deciding the references are sound:

```bash
python scripts/doifind.py FILE --json .markpilot/<docname>/doifind.json
```

It looks each identifier-less entry up in Crossref by its own text and reports what the
record says. Skip with `--no-backfill`. Every status it can emit:

| Status | Meaning | Do what |
|---|---|---|
| `FOUND` | a DOI, corroborated by the author plus at least one of year/volume/page/container | check it against the source, then add it |
| `YEAR-SPLIT` | published online and issued in different years | cite the **issue** year unless the style says otherwise; it prints both rather than asserting a correction |
| `YEAR-DIFFERS` | the entry's year matches no date on the record | read it before changing anything — the match itself may be wrong |
| `DOI-CONFLICT` | the entry already cites a DOI, and Crossref returns a different one | one of them is wrong; settle it by hand |
| `WEAK` / `NO-MATCH` | no confident match | leave it — a wrong DOI is worse than no DOI |
| `GREY-LIT` | regulator report, standard, statement | Crossref indexes almost none of these; verify the issuing body's own URL |
| `QUERY-FAILED` | Crossref unreachable after retries | re-run later; this says nothing about the reference |

A match needs the **author** to agree plus one more signal. Year, volume and page are
exactly the fields a fabricated entry copies from the paper it imitates, so they can all
agree while the work belongs to someone else.

**Nothing is applied automatically, and nothing should be.** Check each proposed DOI
against the source before it goes in the document. A confident-looking wrong DOI is the
`MISMATCH` case in 3b, arriving by a different route.

### 3d. Check what no script can

List the quotations first, so "spot-check every quote" is a finite task rather than an
instruction:

```bash
python scripts/quotecheck.py FILE --list
```

Then check **every direct quote and every statistic**: that the page range exists, that
the quoted sentence appears in the source, that the finding attributed to the source is
one it reports. Use WebSearch/WebFetch for anything without a DOI — a title in quotes
that returns nothing anywhere is very likely invented.

Record the tally, because an agent that skips this produces a report identical to one
that did it: how many quotes and statistics there are, how many you checked, and which
you could not. That count goes in the report.

**Then format**, against the exact style and edition from Step 1, using
`references/referencing.md`. Fix mechanical errors. Where a fix would change what a
citation claims, ask rather than guess.

**The gate:** step 3 passes when

- `citecheck.py` exits `0`; **and**
- `linkcheck.py` exits `0`, **or** exits `2` and every non-`LIVE` item has been
  individually opened and confirmed, each named in the report; **and**
- the quote/statistic tally has no unchecked entries; **and**
- the **REFERENCE COVERAGE** line accounts for every entry.

The `or exits 2` clause is not a loophole — it is the only way the gate can ever close
for a document citing Springer, Elsevier, JSTOR or Wiley, all of which return 403 to
anything that is not a browser. A gate that cannot close gets ignored, which is worse
than one with a stated escape hatch that requires naming what you opened.

Coverage is the one people miss. On a real 29-entry list, only 6 entries carried a DOI or
URL — so the run resolved 6/6 and read as a pass while 23 sources were checked by nothing
at all.
`linkcheck` now exits `2` when most of the list carries no identifier — treat that as
*could not check*, and either add the DOIs or verify those entries by hand. Anything short of that is reported as unconfirmed, by
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

**Headings and captions are almost never addressed by the task sheet, and they move the
number.** On a real 2,000-word proposal the difference was 2,063 with them and 2,008
without — over the limit either way, but by 63 or by 8, which are different problems.
Run it both ways and **report both**, saying which rule the task sheet actually states
(usually none). Do not silently pick the flattering one.

### Per-section budgets

If the task sheet gives a word budget per section — many briefing decks do — check it.
A total that lands on the limit can hide one section 30% over and another 30% under, and
the per-section budget is the rule the marker has in front of them.

If the user passed `--budget FILE`, use that file. Otherwise write the budget you
extracted in Step 1 to `.markpilot/<docname>/budget.txt`, one `Section prefix = N` per
line. Then:

```bash
python scripts/doctext.py FILE --count --limit 2000 --exclude-refs --exclude-appendix \
    --budget .markpilot/<docname>/budget.txt
```

It prints budget / actual / delta per section, flags anything outside tolerance, and
lists sections with no budget line so nothing is silently unaccounted for. A section
short of its budget is as much a finding as one over: it usually means a required
element is thin, and the graders in Step 2 should have said so independently.

**If the count is over**, cut from the lowest-value material, never from a criterion the
rubric weights. Padding hides in the introduction, restated topic sentences, and long
block quotes that could be paraphrased.

**If cutting touches material Step 2c added**, you are removing what the graders
rewarded. Re-run the full three-grader gate afterwards, not the single regression grader
at Step 7. This collision is built into the order of operations — Step 2c may add, Step 4
measures — so expect it rather than discovering it. If the additions that pushed it over
were agent-written rather than the author's, cutting them is the right resolution, not
re-grading around them.

**Termination.** Steps 4, 6 and 7 each change the word count, so they can oscillate. Cap
the whole cut-and-regrade cycle at **two** passes. If the document is still over the limit
after the second, stop and report it as an open item with the specific sections that would
have to lose words — an unbounded loop chasing a limit is how a working draft gets worse.

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

**Look for the plotting source before assuming there is none.** Figures usually arrive as
`.png` files in a `figures/` folder with the code that made them sitting elsewhere — a
notebook, a script, another repo. Check the document's folder and its siblings. If the
code genuinely does not exist (the chart was made in Excel, drawn by hand, or pasted from
a source), say **"chart styling not checked — no plotting source"** in the report rather
than letting a silent skip read as a pass. That is the same failure mode as everything
else here: nothing checked it, so nothing may claim it.

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

**`references/prose.md` is the brief for this step**, whoever carries it out. Read it
first. It names what to remove, what to keep because a marker rewards it, and what must
not be touched at all.

### Which editor is running

The humanizer skill is a **soft dependency**. It is a far better catalogue of AI tells than
this file could restate, so use it when it is there:

1. Check the available skills for one named **`humanizer` or `humaniser`**. Both spellings
   are in circulation — upstream is `humanizer`, and local adaptations are often renamed —
   so checking only one silently falls through to the weaker pass on a machine that has it.
2. **Available** → invoke it, passing `references/prose.md` as an explicit clamp on its
   defaults. It is tuned for general-audience prose and is wrong in a few specific places
   about graded academic writing; the clamp is what makes it safe here.
3. **Not available** → run the pass yourself, directly from `references/prose.md`. This is
   a weaker pass and it must be reported as one.

**Ask for file mode.** Upstream v2.9.1 defines three invocation modes, and the default —
pasted-text — returns a draft, audit bullets and a final rewrite into the conversation.
That is the wrong artefact here and it is expensive. Say *file mode: rewrite the document
in place and report a summary of what changed.*

**Do not assume the version.** Forks and renamed copies in circulation predate two things
that matter, so pass both explicitly rather than relying on the skill to hold them:

- the **never-invent-facts** rule, and the fabrication question in its audit step. Older
  copies ask only "what still reads as AI" and never "does the rewrite state a fact that is
  not in the source". Fabrication is the highest-severity defect this pipeline can produce.
- **Invocation Modes** themselves. A copy without them has no file mode, so it will return
  the three-version chat deliverable no matter how it is asked. Take the final rewrite from
  it and apply the edit yourself; do not paste a draft into the document.

Never silently substitute one for the other. The PROSE row names which ran:

```
PROSE      humanised via /humanizer · 12 tells removed
PROSE      humanised inline · 9 tells removed — no humanizer skill is installed,
           so this was a smaller catalogue than the full pass
```

A report that reads identically whether or not the better tool was present is exactly the
failure mode the rest of this pipeline is built to avoid.

### The clamp, in short

Full version in `references/prose.md`; these are the ones that bite.

- **Body prose only.** Never quotations, citations, reference entries, data, captions or
  headings, and not the abstract unless the rubric scores its style.
- **En dashes are not em dashes.** A general-purpose "the final text contains no em or en
  dashes" rule will destroy `118–142`, `2019–2021`, `a 20–30% increase` and `[3]–[7]` —
  formatting that APA, Harvard, IEEE and Vancouver all require, in the same document whose
  references Step 3 just verified. Cut em dashes used as connectors. Leave en dashes in
  ranges and coordinate compounds alone.
- **Keep hedging on empirical claims.** "The results suggest" is accurate, not weak;
  overclaiming loses marks that caution does not. Cut only stacked hedges.
- **Keep structural signposting** where the rubric or discipline expects it. Some criteria
  award marks for exactly the "This section examines…" sentences it would cut.
- **Keep formal register, discipline terminology, and passive voice in methods.**
- **Leave curly quotes, and bold or title-case headings** that the style guide mandates.
  APA 7 requires bold headings and title case at levels 1–3.
- **Do not change the word count materially** — flag it if a rewrite would.

### The deliverable

The edited document and entries in `changes.md`. Not a draft, an audit and a final version
to choose between: this is a pass over a file, and Step 7 is the independent check that a
self-review loop cannot be.

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

**Every row below is mandatory.** A row whose check did not run says **NOT RUN** or
**NOT CHECKED** and why — never a blank, and never omission. Each row names what produced
it: a script and its exit code, or `by hand`. A claim with no named source is one nobody
can check, which is the thing this skill exists to prevent.

```
MARKPILOT — <document>
──────────────────────────────────────────────────────────────────────
SOURCE     graded on .markpilot/<doc>/draft-round-2.txt (4,690 words extracted)
           your .docx is UNMODIFIED — apply changes.md to it
TARGET     95% (--target) · 3 rounds (chosen at intake) · export: both

GRADE      96% estimated  (round 2 of 3; LOWEST of 3 graders; spread 4 pts)   by agents
           lit-review 14/15 · analysis 29/30 · evidence 19/20 · structure 10/10
           An LLM panel's estimate against the rubric. Not a measurement.
EVIDENCE   18/18 grader-quoted spans found in the document          quotecheck exit 0

WORDS      1,847 / 2,000 headings in · 1,802 / 2,000 headings out    doctext exit 0
           (rule: excl. references + appendices, task sheet p.2; no tolerance stated)
SECTIONS   5/5 within their per-section budget                       doctext --budget
REFS       18 entries · 0 orphans · 0 uncited · 2 format fixes      citecheck exit 0
LINKS      16/18 LIVE · 0 dead · 0 mismatched          linkcheck exit 2 (2 BLOCKED)
           2 BLOCKED (Wiley, JSTOR) opened in a browser and confirmed   by hand
           REFERENCE COVERAGE 18/18 entries carried an identifier
DOIS       0 missing · 0 year questions · 0 conflicts                doifind exit 0
QUOTES     7 quotes + 4 statistics · 11/11 checked against source       by hand
FIGURES    3 figures · 1 table · numbered, captioned, cross-referenced  figcheck exit 1
           2 charts were pure library default → corrected code in changes.md
PROSE      humanised via /humanizer · 12 tells removed
           regression grader: 3/4 criteria re-confirmed at baseline band;
           `evidence` dropped D→C, the two sentences carrying it restored
AI POLICY  declaration required (task sheet §4) → drafted, on the coversheet

AUTHORED   +64 / -121 net words across 2 rounds (author-written: the rest)
           new material closed: `analysis` (one added paragraph, §3.2)
           nothing exceeded the +150 ceiling; no criterion closed for the author
CHANGED    <n> edits, logged in .markpilot/<doc>/changes.md
NOT CHECKED
  · <every check that did not run, and why>
STILL ON YOU
  · <thing only the author can decide or supply>
  · <anything left unconfirmed, by name>
```

Variants that must be used when they apply:

- **No rubric** → `GRADE  NOT RUN — no rubric published; requirements compliance only`,
  and **no percentage anywhere** in the report.
- **`--quick`** → `GRADE  84% indicative only (1 grader) — the gate was NOT cleared`.
- **PDF input** → add to `SOURCE`: `checks ran on a text extraction; page fidelity lost`.
- **No plotting source** → `FIGURES … chart styling NOT CHECKED — no plotting source`.
- **`--report-only`** → `CHANGED  nothing (--report-only)`.
- **No humanizer skill installed** → `PROSE  humanised inline · <n> tells removed — no
  humanizer skill is installed, so this was a smaller catalogue than the full pass`. Name
  the skill that *did* run when one did: `humanised via /humanizer`, `via /humaniser`.
- **`--no-humanise`** → `PROSE  NOT RUN (--no-humanise)`, and Step 7's regression grade
  says `NOT RUN` for the same reason.
- **Similarity** → markpilot does **not** check text-matching or plagiarism, and Turnitin
  is not run here. Say so under NOT CHECKED rather than letting a reader assume it was
  covered.

### Export it

`report.md` is not a deliverable on its own. Convert it:

Use the format they chose at Step 0:

```bash
python scripts/export.py .markpilot/<doc>/report.md            # .docx + .pdf
python scripts/export.py .markpilot/<doc>/report.md --docx     # Word only
python scripts/export.py .markpilot/<doc>/report.md --pdf      # PDF only
python scripts/export.py .markpilot/<doc>/report.md --all      # + print-ready .html
```

Both the `.docx` and the `.pdf` are written directly, with no dependencies. Do the same
for `changes.md`, `reference-dois.md` and the AI declaration whenever the user will act on
them away from the terminal — a change list they cannot open in Word is a change list they
will not apply. Then tell them the paths.

Skip this only if they chose *Markdown only*.

Report the governing (lowest) score, not the flattering one. The LINKS numerator can
never exceed the script's `LIVE` count. Any step skipped, or run under `--report-only`,
or that exited `2`, appears in the report as such — never as a pass.

## Step 10 — Feedback (once, ever)

```bash
python scripts/testimonial.py --check     # exit 0 = ask, exit 1 = stay quiet
```

**Only run this when all of the following hold.** Otherwise skip it silently and say
nothing:

- the pipeline completed through Step 9;
- nothing exited `2` unresolved, and the user was not left with a blocked gate;
- `--check` returned `0`;
- this is not a `--report-only` or `--quick` run.

Asking for a recommendation after a run that failed, stalled, or could not check half the
references is worse than never asking.

If it returns `0`, ask **once** — a single AskUserQuestion call carrying **two** questions,
never a sequence of prompts:

| Question | Options |
|---|---|
| *How did this go?* | `★★★★★ nailed it` · `★★★★ good` · `★★★ mixed` · `★★ or less — it got in the way` |
| *If you'd like it quoted somewhere* | `quote me by name` · `quote it, but anonymously` · `keep it private` · `no feedback, thanks` |

Free text from *Other* on the first question becomes `--comment`. The bottom rating is a
bucket rather than a value because AskUserQuestion allows four options; the form the link
opens has a real 1–5 widget, so anyone who wants to say *1* can correct it there.

**The second question is the one that matters.** "You may quote this" and "you may use my
name" are separate permissions, and running them together is how people end up on a website
they did not expect to be on. Ask both. Default to the private answer if they skip.

```bash
python scripts/testimonial.py --save --rating 5 --consent named \
    --name "..." --role "..." --stamp "<today>" --comment "..."
python scripts/testimonial.py --decline          # if they said no feedback
```

`--consent` is `none` (the default), `anon`, or `named`. Pass what they actually chose.
Either branch marks the state, so it never asks again on any future run, in any project.

**What it does with the answer:** writes it to `~/.markpilot/testimonials.md` and
`testimonials.jsonl` on the user's own machine, then prints **one** pre-filled link to the
web form.

**Pre-filled is not submitted.** The link opens the form with their answers already in it,
in their own browser; nothing is sent until they press Submit, and they can change anything
there first — including the consent. Say that when you show the link — a URL that looks
like it might already have sent something is worse than no link at all. The script itself
opens no network connection.

The form needs **no account and no sign-in**, which is the whole reason it is the door
being offered. Do not talk them into a different one.

### Consent governs what leaves the machine

The script enforces this; do not work around it.

- `none` → no link is printed at all. There is nothing to send, and that is a complete
  answer. Do not offer an "anonymous version anyway".
- `anon` → the words travel, the name does not. It is dropped from the link, the copy
  block and `--wall` — not hidden at the end, never copied in at the start.
- `named` → the name travels exactly as given.

`python scripts/testimonial.py --doors` reprints every way to send it — the form, a GitHub
issue, and a plain block to copy — if they close the terminal or would rather use another.
Only reach for it if they ask.

### If they would rather file it on GitHub

Some people prefer it. Offer only on request, and as a **second, separate decision**:

```bash
python scripts/testimonial.py --preview --consent named --name "..." --rating 5 \
    --stamp "<today>" --comment "..."
```

Show that output **verbatim** — it prints the exact title and body and says plainly that it
would be a public issue under their own account. Only on an explicit yes:

```bash
python scripts/testimonial.py --file --consent named --name "..." ...   # same arguments
```

Rules that are not negotiable:

- **Never run `--file` without showing `--preview` first and getting a yes.** "I'll send
  this for you" is a different act from "here is a link", and it needs its own consent.
- `--preview` and `--file` refuse outright under `--consent none`. Do not re-run them with
  a consent they did not give.
- **Never re-ask** if they decline the posting. They already gave you the testimonial; the
  local copy is the win.
- If `gh` is missing or not logged in, `--file` refuses and prints the other doors instead.
  It will not post under some other account that happens to be configured — that would put
  their words under a stranger's name.
- Do not offer this at all when the run itself was blocked or incomplete, same as the
  original ask.

That constraint is not squeamishness. This skill is published for other people to install,
and a tool that quietly uploaded someone's name and comments would be doing something they
did not agree to. Do not add a send step, do not offer to email it, and do not ask a second
time if they decline.

## Flags

| Flag | Effect |
|---|---|
| `--criteria FILE` | path to the rubric, if not auto-found |
| `--task FILE` | path to the assignment brief |
| `--style` | `apa7`, `harvard`, `ieee`, `chicago`, `mla`, `vancouver`, `aglc`, `unknown` |
| `--target N` | gate threshold, default 95. Used in 2a/2d and stated in the report |
| `--format` | `docx` / `pdf` / `both` / `md` — overrides the Step 0 answer for step 9 |
| `--rounds N` | max fix-and-regrade cycles. Overrides the Step 0 answer; default 3, hard cap 6 |
| `--source FILE…` | plotting source to scan in step 5 |
| `--report-only` | change nothing at any step; findings only |
| `--quick` | one grader (hostile second marker stance). Report says "indicative only"; the gate is not cleared |
| `--no-humanise` | skip step 6 and step 7's regression grade. The word count in step 7 still re-runs if step 4 changed anything |
| `--no-figures` | skip step 5 |
| `--link-timeout N` | seconds per fetch, passed to `linkcheck --timeout` (default 20) |
| `--budget FILE` | per-section word budget for step 4. Takes precedence over the budget written from step 1 |
| `--no-backfill` | skip the DOI lookup in step 3c |

## Files

Written under `.markpilot/<docname>/`: `rubric.md`, `constraints.md`, `text.txt`,
`grades-round-N-<stance>.md`, `draft-round-N.txt`, `budget.txt`, `links.json`,
`doifind.json`, `changes.md`, `report.md` — plus the `.docx` / `.html` that
`export.py` makes from them.

State that must outlive a reinstall (the Step 10 flag) lives in `~/.markpilot/`,
outside the skill directory and outside git.

`scripts/selftest.py` (which also runs `scripts/e2e.py`) guards the parsing regexes,
which are the fragile part
of this skill — several of those cases are defects that reached working code. Run it
after editing any regex in `doctext.py`, `citecheck.py` or `figcheck.py`.
