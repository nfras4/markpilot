# Prose — the academic clamp

Step 6 delegates to the [humanizer](https://github.com/blader/humanizer) skill when it is
installed — under either spelling of its name, `humanizer` or `humaniser`. This file is
what that skill is handed as its brief, and what Step 6 runs from directly when no such
skill is present.

It exists because general-purpose de-AI editing and graded academic writing disagree in
specific, checkable places. A humaniser tuned for blog prose is right about almost
everything and wrong about a handful of things that cost marks — and one of them will
silently undo a check markpilot ran three steps earlier.

## Scope

Run on **body prose only**: the argument, discussion and conclusion.

Never on: quotations, in-text citations, reference entries, tables, data, figure captions,
headings, or an abstract or executive summary — unless the rubric explicitly scores the
style of one of those.

That exclusion list is doing real work. It is the only thing standing between a
general-purpose "remove every em and en dash" rule and a reference list that no longer
matches APA 7.

## Never invent

**The rewrite must not contain a fact, name, number, date, quote or citation that is not in
the source text.** Replacing a vague claim with a specific one is allowed only when the
specific already appears in the document. If a sentence needs a detail to work and the
document does not have it, flag it as author-input-required and write the plain version.

This is stated here rather than assumed because it is not in every version of the editor.
Upstream humanizer carries it as a governing rule and audits for it before returning a
rewrite; older and renamed copies of the skill do not have it at all, and will happily make
a limp sentence specific by supplying the specifics. In a graded submission that is not a
style improvement, it is fabricated evidence, and it is the one defect in this whole
pipeline that a marker treats as misconduct rather than a lost mark.

Pass it explicitly every time, whichever editor is running.

## Remove

These are worth removing and cost nothing academically.

- **AI vocabulary**: delve, tapestry, testament to, underscores the importance of, pivotal,
  crucial, robust (as filler), navigate the complexities, plays a vital role, it is worth
  noting that.
- **Em dashes** used as a general-purpose connector. Replace with a full stop, a comma, a
  colon, or parentheses, whichever the sentence actually wants. (En dashes: see below —
  they are **not** the same problem.)
- **Rule-of-three cadence** where the third item carries no information: "clear, concise
  and compelling", "efficient, effective and equitable".
- **Promotional register**: groundbreaking, game-changing, revolutionary, cutting-edge,
  seamlessly. Rare in student work but arrives with AI drafting.
- **Empty summary paragraphs** that restate the preceding three without adding a claim.
- **Generic upbeat conclusions**: "the future looks bright", "an exciting step forward".
  A conclusion should state what follows from the evidence.
- **Vague attribution**: "experts argue", "studies show", "it is widely believed" with no
  citation attached. In graded work this is not just a tell, it is an unsupported claim —
  either attach the source or flag it as author-input-required.
- **Copula avoidance**: "X serves as a mechanism for" → "X is". "The findings act as an
  indication that" → "The findings indicate".
- **Negative parallelism**: "It is not merely X, it is Y" as a rhetorical reflex.
- **Elegant variation**: cycling synonyms for a defined term. In academic writing a term
  should be the *same term* every time; consistency is being graded, variety is not.

## Keep

A general-audience humaniser strips these. Every one of them earns marks.

- **Hedging on empirical claims.** "The results suggest" is accurate, not weak. Overclaiming
  loses marks that caution does not. Only cut *stacked* hedges — "may possibly
  potentially" — down to one.
- **Structural signposting.** "This section examines…" is a tutorial-script tell in a blog
  post and a rubric criterion in a report. Check the rubric before cutting any of it.
- **Formal register and discipline terminology.** Precision is the thing being assessed.
  Do not simplify a technical term into a friendlier near-synonym.
- **Passive voice in methods**, where the convention calls for it.
- **Nominalisation** where the field uses it as standard phrasing.
- **Paragraph count and structure.** A rewrite covers everything the original covered, and
  keeps the shape it covered it in: five paragraphs making five moves stay five paragraphs.

  This is a deliberate override, not an oversight. Upstream humanizer says the opposite —
  "merge or split paragraphs freely… when keeping the information and mirroring the
  original's structure pull in different directions, the information wins" — which is right
  for prose that will be read and wrong for prose that will be marked. Here the structure is
  frequently a rubric criterion in its own right, the word count is a hard constraint, and
  Step 2 already graded the document in the shape it is in. Restructuring at Step 6 silently
  invalidates the score at Step 2.

## Do not touch

Each of these looks like an AI tell to a general-purpose rule and is not one here.

- **En dashes in numeric and page ranges** — `118–142`, `2019–2021`, `a 20–30% increase`,
  `[3]–[7]`. APA 7, Harvard, IEEE and Vancouver all require the en dash here, and
  `references/referencing.md` specifies it. A blanket "the final text contains no en
  dashes" rule will convert correct formatting into an error, in the same document whose
  reference formatting Step 3 just verified. Em dashes and en dashes are different
  characters doing different jobs; only the em dash is the tell.
- **En dashes joining coordinate terms** — Okabe–Ito, Cobb–Douglas, cost–benefit. That is
  a compound of two names, not punctuation.
- **Curly quotes and apostrophes.** Word produces them by default. Converting a document to
  straight quotes changes hundreds of characters, matches nothing else in the file, and
  fixes nothing a marker can see. If a document is already consistent, leave it.
- **Bold and title case in headings** where the style guide mandates them. APA 7 requires
  bold headings, and title case at levels 1–3. "Headings should be sentence case and
  unbolded" is a Wikipedia house rule, not a general truth.
- **Quoted material, ever.** Editing inside quotation marks is falsifying evidence, and
  `quotecheck.py` will report the quote as no longer present in the source.

## Word count

Rewrites drift. Step 4 already established the count against a stated limit, so a Step 6
that quietly adds 80 words has broken a constraint the report claims to have checked.

Keep the net change near zero, and if a rewrite genuinely cannot be made without moving the
count materially, say so rather than doing it silently. Step 7 re-runs the count regardless.

## Output

The deliverable is **the edited document**, plus the per-change log entries in
`changes.md`. Not a draft, a critique and a final version to choose between — Step 6 is a
pass over a file, not a chat exchange, and Step 7 supplies the independent audit that a
self-review loop cannot.
