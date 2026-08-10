# Changelog

## 0.1.0

First release.

Pipeline, scripts, and reference material as described in the README. Notable
decisions baked in from the start:

- **Exit `2` means "could not check", and is never a pass.** A parser handed an
  unreadable document otherwise produces output identical to a clean one.
- **`BLOCKED` links are never counted as verified**, and `NO-DNS` is separated from
  `DEAD` because a name that will not resolve is evidence about the network.
- **DOIs are matched on metadata, not just resolution** — a DOI that resolves to a
  different paper is treated as more severe than a dead link.
- **The grade is reported as an estimate**, and the governing figure is the lowest of
  three graders rather than the average.

### Fixed before release, found by running the scripts rather than reading them

Regression cases for all of these are in `scripts/selftest.py` (90 cases).

- `n.d.` written as `n\.?\s?d\.?` matched the "nd" inside **"and"**, so every
  `Smith and Jones, 2020` keyed its year as *n.d.* and mismatched against itself.
- Folding `et al.` into the co-author alternation lost every `Author et al. (Year)`.
- `summaris\b` cannot match "summarises"; the prose/caption test was inverted for a
  whole class of lines. The real discriminator is the separator after the number, not
  the word that follows it.
- Sentence connectives filtered against the whole citation made the surnames **An, So,
  Ho and Le** invisible on both sides at once.
- `[3]–[7]` ranges reported their interior numbers as uncited.
- Reading 60KB of a gzip stream raises `EOFError`, which is not an `OSError`, so live
  pages were reported as timeouts.
- Deduplicating DOIs by value meant the same DOI under two entries was checked against
  only one of them.

### Feedback: offer to file it, as a second decision

The pre-filled link still required a browser trip, which is where most people drop out. So
after saving, the skill now offers to post the issue directly — but as a **separate,
explicitly confirmed step**, never folded into the first answer.

`--preview` prints the exact title and body that would be posted, verbatim, and states
plainly that it would be a public issue on a public repository under the person's own
GitHub account. Only after they see that and say yes does `--file` run `gh issue create`.

The guards matter more than the feature:

- `--file` refuses outright if `gh` is missing or not authenticated, and prints the link
  instead. It will not post under whatever account happens to be configured — that would
  publish someone's words under a stranger's name. Verified by running it with `gh` off
  the PATH: exit 2, nothing sent.
- Declining the post does not re-ask. The local copy was already the win.
- "I'll send this for you" is a different act from "here is a link", so it gets its own
  consent rather than inheriting the first one.

The `testimonial` label did not exist on the repository, so the pre-filled link pointed at
a label GitHub would have dropped. Created.

### Feedback: pre-filled share link

Running the Step 10 flow for real immediately found a defect no unit case would have:
**"rating only, no comment" could not be recorded honestly.** `--save` required a comment,
so a rating-only answer had to be stored as `(rating only — no comment left)` — placed in
the file as a markdown blockquote, formatted exactly like something the person had said.
A fabricated quote, in the one file whose entire purpose is quoting people accurately.

`--save` now accepts a rating, a comment, or both, and renders a rating-only entry as
italic text rather than a quotation. It refuses only when there is nothing at all to save,
and a refusal does not consume the ask-once flag.


`testimonial.py` stored the comment locally and printed a bare "open an issue" URL, which
meant anyone who wanted to share it had to retype the whole thing — so in practice almost
nobody would. It now builds a GitHub *new issue* link with the title, attribution, rating
and comment already filled in.

The consent model is unchanged and deliberate: **pre-filled is not posted.** The link opens
a draft in the person's own browser, under their own account, and nothing reaches the
repository until they press Submit. The script still opens no network connection. That is
the difference between removing friction and removing the decision.

Truncates the comment to keep the URL inside 1,900 characters, because a link a browser
silently refuses to open is worse than a shortened one. `--share` reprints it later.

### The fix pass and round 2, run for real

The loop was completed end to end on the test fixture. Round 1 scored 71 / 70 / 67
(governing 67). The fix pass ran under the authorship rules, then **three fresh graders**
that never saw the change log scored 83 / 79 / 75 — governing **75**, up 8 points, on
+110 net authored words (under the 150 ceiling, which therefore did not fire).

Three things this confirmed and one it broke:

- **The fix pass moves the score, and round-2 graders are genuinely independent** — they
  found things round 1 did not, including a defect in the fix itself.
- **The author-input-required flag held.** The draft's core gap was "takes a defensible
  position", which Step 2c forbids the tool from supplying. It was flagged rather than
  written, and all three round-2 graders independently capped that criterion at exactly
  that point — "names the adjudication task and stops". The refusal was correct and
  visible in the marks.
- **The target was not reached and was reported as not reached** (75 against 95), which is
  the behaviour the round-budget rule exists to produce.
- **New rule, because the fix pass broke one that did not exist yet.** It introduced a
  categorisation — that the studies reporting losses "examine settings where output is
  measured against collaboration-heavy work" — which the draft's own literature review
  contradicts, since one of those studies measures calls answered per hour. Two of three
  graders rejected it unprompted as "inference dressed as established fact" and "asserted,
  not shown". The existing prohibitions cover inventing a source, statistic, quote or
  position; none covered inventing a **synthesis**, which feels like analysis and is exactly
  what a top band asks for. Step 2c now forbids it explicitly, and requires each round's
  grades to be read for damage to the previous round's additions, not only for progress.

### Intake interview, real PDF, and the grading loop verified end to end

- **`pdfwrite.py`** — a real `.pdf`, written directly, no browser and no dependencies.
  "Open the HTML and press Ctrl+P" was not a PDF. Uses the base-14 fonts every reader must
  provide, so nothing needs embedding, and breaks lines on the actual Helvetica advance
  widths rather than an averaged guess. Validated structurally: header, xref table,
  trailer, `startxref` resolving to `xref`, correct page count.
- **Step 0 now interviews the user** before any work starts, in one AskUserQuestion:
  *how should the report be delivered* (Word / PDF / both / markdown) and *how many
  fix-and-regrade rounds* (1 / 3 / until it clears, max 6 / report only). Both were
  previously assumed. Asking the export format at the end means re-running it after the
  user has stopped paying attention; asking the round count after four rounds have run is
  worse.
- The **until-it-clears cap is 6 and not optional**, because the loop is not monotonic: a
  fix that closes one criterion can open another, so the best round is not necessarily the
  last. Step 2d keeps the best-scoring draft and the report names which round it came from.

**The grading loop was executed for the first time, against a purpose-built fixture** (a
deliberately descriptive 294-word draft and a 4-criterion weighted rubric). Three graders
in fresh contexts returned the structured table with quoted band descriptors and quoted
evidence; they scored 71 / 70 / 67, so the governing score was 67 and the 4-point spread
sat under the 8-point ambiguity threshold; all three independently identified the same
criterion as the largest gap. `quotecheck` confirmed all four of the hostile marker's
quoted spans against the document, and rejected a fabricated one. The orchestration works
as documented.

### Reports in real formats, feedback capture, and a claude.ai edition

- **`export.py`** — `report.md` was the only output, which is not a deliverable. Writes
  `.docx` directly as an OOXML package and a print-ready `.html` (Ctrl+P → Save as PDF).
  Stdlib only, no pandoc. Verified by round-tripping the generated `.docx` back through
  `doctext.py`.
- **`testimonial.py`** — asks once, ever, and only after a run that actually completed.
  Writes to `~/.markpilot/testimonials.md` on the user's own machine and **opens no network
  connection**. Sharing it is the user's action, taken afterwards, with the text in front of
  them. This skill is published for other people to install; a tool that quietly uploaded
  someone's name and comments would be doing something they did not agree to.
- **`web/`** — a cut-down edition for claude.ai, where there is no shell, no filesystem and
  no subagents. The mechanical checks are ported to JavaScript for the Analysis tool so the
  numbers stay real. Grading degrades to a single self-assessed pass rather than three
  independent graders, and bulk reference verification is impossible without network. Both
  losses are stated in the edition's own output rather than papered over.
- The **"refines a draft, does not write one"** scope is now stated in the skill
  description, SKILL.md, and the README — and enforced by the authorship ceiling below.

### Third review round

**New:** `scripts/e2e.py` — 10 whole-document cases, run by `selftest.py`. Three review
rounds running, the defects that got through were invisible to unit cases because they
only appear when a whole script reads a whole file, and three of them were regressions
introduced by a fix for something else. Unit tests could not see that class; these can.

Five more exit-0-on-unverified paths, three of them regressions from the previous round:

- **A numbered reference list made `citecheck` abandon author-date checking.** `--style
  apa7` was overridden by inference whenever the body contained any `[n]` and the list was
  numbered — both routine. It printed "OK - every number resolves both ways" at exit 0 on a
  document with two orphan citations and an uncited reference, saying nothing about what it
  had skipped. An explicitly named style is now never overridden.
- **`quotecheck` manufactured quotations out of apostrophes.** A pair of straight
  apostrophes ("the board's … the regulator's") formed a "quotation", so a document with
  none reported three to verify at exit 0 — and in `--claims` mode produced a fabricated
  NOT FOUND that would have discarded a valid grading pass. The straight-single-quote pair
  is gone.
- **`quotecheck` dropped over-long spans before forming the denominator**, so a fabricated
  471-character quote made a run report "1/1 quoted spans appear" at exit 0. Skipped spans
  are now counted and reported.
- **Every Chicago and MLA reference was classified as grey literature** and never looked
  up: the personal-name guard required an initial ("Smith, J."), so styles that spell the
  given name out fell through to the acronym branch.
- **The two-line-caption fix carried an ordinary body sentence** as a missing caption,
  turning a real finding into a pass. The carried line must now look like a title.

Also: the one `load()` failure path missed by the `die()` refactor still exited `1` while
printing "do NOT treat this as a pass"; `--budget` without `--count` silently did nothing;
one heading could satisfy two budget lines and be counted twice; `looks_like_reference`
treated length alone as evidence, swallowing the document tail; the unstyled-refs fix had
been applied to the word count but not to `citecheck`/`linkcheck`, so the scripts disagreed
about the same document; `_html_paras` never set `in_table` at all, leaving HTML and PDF
dumps hijackable; a missing `--source` was masked by a style-tell exit 1; and `linkcheck`'s
year check was satisfied by digits inside a DOI suffix.

**The "refines, does not write" claim is now enforced rather than asserted.** It was the
only load-bearing prohibition with no mechanical check behind it, and the pipeline actively
pushed against it: Step 2a names "an original position" as the top band, Step 2c says close
the highest-weighted gap, and the loop stops on the score. Every change now records its word
delta, the report carries a mandatory `AUTHORED` row, a +150 net-word ceiling stops and asks
the author, and a criterion flagged author-input-required cannot be quietly closed by a
later round.

### Second review round — everything the reviewers found

**New:** `quotecheck.py`. The grader brief demands a quoted span for every score, but
nothing checked the quotes were real, and an invented quote produces output identical to a
real one. `--claims` verifies grader evidence against the document; `--list` enumerates the
document's own quotations so "spot-check every quote" becomes a finite task.

Correctness:

- **`doifind` accepted a wrong DOI on corroborating fields a fabricator copies.** Year,
  volume and page are exactly what a fake entry lifts from the paper it imitates, so all
  three could agree while the work belonged to someone else. The author is the identity
  signal: a match now requires the author plus one more signal, or — where the record names
  no authors — three non-author signals.
- **Title scoring was carried by one- and two-word titles.** The denominator is record-title
  tokens, so "Trust" scored 1.0 against almost anything, and because the entry side includes
  the journal name a record matching the cited work's *container* also scored 1.0. Short
  titles are now capped below the threshold.
- **Only the top-scoring candidate was author-checked**, discarding a correct record at rank
  2 for a wrong one at rank 1. Candidates are now ranked by corroborating signals first.
- **`--all` never compared the DOI already in the entry** — the one thing re-checking is
  for. New `DOI-CONFLICT` status.
- **Grey-lit detection missed** acronym authors (OECD, WHO, CSIRO), bodies not ending in a
  listed noun (United Nations, Standards Australia), consultancies, and every numbered entry.
- **An unstyled `References` heading swallowed the rest of the file**, including the AI
  declaration Step 8 tells the agent to add — losing those words from the count.
- **The `in_table` guard was docx-only**, so the "Reference" table-header hijack still hit
  html, markdown and the PDF text dumps the skill routes through those readers.
- **`--budget` ignored every exclusion flag**, so sections summed to more than the document
  total; it also silently dropped all text before the first heading, and borrowed
  `--tolerance` from the overall limit. Now consistent, with its own `--budget-tolerance`.
- **APA 7's number-on-its-own-line figure caption** — the layout `references/charts.md`
  itself prescribes — was reported as "a number with no caption text".
- **Appendix figures after the reference list were invisible**, caption and cross-reference
  dropped together so nothing was reported wrong.
- Footnotes bypassed every other exclusion, so `--exclude-intext` removed nothing in
  AGLC/Chicago where the citations live in footnotes.
- The no-op warning printed flag names argparse rejects (`--references-section`).
- `linkcheck` sent a **spoofed Chrome User-Agent to Crossref's API** and claimed the polite
  pool with an unreachable mailto. Both replaced with an honest UA; 429/503 now retried.

### Fixed after an independent review round

Two CRITICAL false passes, both reproduced end to end, both regressions introduced by the
*previous* round's fix:

- **A substring author test let a short surname match anything.** `He` is inside "the",
  "other", "when"; `Ma` is inside "formal". A Crossref record by He et al. therefore
  "matched" an entry authored by Smith — so `linkcheck` reported a DOI resolving to a
  *different paper* as `LIVE` at exit `0` (passing the documented Step 3 gate), and
  `doifind` proposed that DOI at `FOUND` for a fabricated reference. Author matching is
  now whole-token, checks every author rather than only the first, and is shared by both
  scripts.
- Three more **exit-0-on-nothing-checked** paths: `doifind` with an all-grey-literature
  list, `figcheck` with no figures detected, and `figcheck` with a `--source` path that
  does not exist. All now exit `2`.

Also:

- Unreadable input exited `1` ("problems found") in every script, including the path that
  printed *"Do NOT treat this as an empty document or as a pass"*. Now `2` everywhere.
- `figcheck`'s `2` meant "style tells found", contradicting the global contract. Style
  tells are a finding (`1`); `2` is reserved for could-not-check.
- One stray `color=` **in a comment** disabled the no-styling chart check for the whole
  file. Comments and docstrings are stripped first.
- `ref_key` took the first year-shaped token anywhere, so "Rethinking the 1970s … 2019"
  keyed `1970s` — the `[a-z]?` even swallowed the trailing `s` — producing a false
  YEAR MISMATCH plus a false UNCITED REF on a correct entry.
- **SKILL.md's report template modelled an impossible state**: `linkcheck exit 0` beside
  two BLOCKED links, when BLOCKED always yields `2`. And the Step 3 gate required both
  scripts to exit `0`, which no document citing Springer, Elsevier, JSTOR or Wiley can
  ever satisfy. The gate now states the triaged-`2` path explicitly.
- The template also printed the blanket "all criteria re-confirmed" sentence that Step 7
  explicitly forbids.
- The selftest count was quoted as 78, 90 and 107 in three different files. The docs no
  longer hard-code it.

### Added after the first real run

- **`doifind.py`** — looks up reference entries that carry no DOI, in Crossref, by their
  own text. `linkcheck` could report that 23 of 29 entries were unverifiable but could do
  nothing about it; this closes the loop. Reports `FOUND`, `YEAR-SPLIT` (online and issue
  years differ — the commonest citation error in student work), `WEAK`/`NO-MATCH` (left
  for a human), and `GREY-LIT`. Applies nothing automatically.

Three defects in it were caught on its own first run:

- A record with **no author array passed the author check vacuously** — `if not authors:
  return True`. That is how ASIC's 2023 report matched *ASIC v Ingleby*, a 2013 court
  case, and NHMRC's 2023 statement matched a 1993 article, both then reported as
  confident year corrections. No authors now fails the check.
- Particle surnames failed the substring test, so the **correct** DOI for van Rooij et al.
  (2011) was demoted to a weak match. Comparison is now on letters only.
- Grey literature was queried at all. Regulator reports and standards are not in
  Crossref, so any match is a different document sharing the organisation's name. They
  are now detected and routed to the issuing body instead — and the detector has to allow
  a lowercase "and", since both worst cases contained one.

### Workflow gaps found by the first real run

- **Reference coverage was not reported at all.** A list where only 6 of 29 entries
  carried a DOI or URL produced "6/6 confirmed to resolve" and exit `0`, so the Step 3
  gate passed while 23 sources were checked by nothing. `linkcheck` now prints a
  REFERENCE COVERAGE line and exits `2` when most of the list has no identifier.
- **Only the total word count was checked.** Where a task sheet gives a per-section
  budget, a total that lands on the limit can hide one section well over and another
  well under. `doctext --budget FILE` now checks each section.
- **Headings and captions were silently in or out.** They moved a real count from 2,063
  to 2,008 against a 2,000 limit. The skill now requires reporting both.
- **No path when the course publishes no rubric.** The grade gate simply could not run.
  There is now a documented fallback: build a requirements checklist from the task sheet
  and report compliance, explicitly not a grade and with no percentage.
- **A missing `--source` read as a clean chart check.** Now reported as not checked.

### Fixed on the first real submission it was run against

- A `Heading2` inside an appendix ended the appendix, so the rest counted against the
  word limit — **3,287 words reported instead of 2,063**.
- A one-word table header reading **"Reference"** (the required column of an APA
  conceptual-definitions table) matched the reference-section regex and hijacked the
  document from that point on, pulling 26 table rows into the reference list.
- A lowercase nobiliary particle (`van Rooij, M., …`) failed every entry-start branch,
  so the entry was merged into the previous reference.
- A curly-apostrophe possessive (`Hayes’ (2022)`) keyed `hayes’` and never matched.
- A parenthetical date range (`early Sep – early Oct 2026`) keyed "early" as a surname.
- Organisational authors cited by initials — `(ASIC, 2023)` against
  `Australian Securities and Investments Commission. (2023)` — reported twice, once as
  an orphan and once as an uncited entry. They are now paired and reported as a
  check-this, since APA 7 only requires the abbreviation be introduced at first mention.
