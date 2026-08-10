# Grader brief

Use this close to verbatim when spawning a grading subagent. It is written to counteract
the two ways LLM graders fail: they are generous, and they score the impression the
document gives rather than the descriptor the rubric states.

Substitute the bracketed parts. Give the grader the rubric text, the task sheet, and the
document — and **nothing else**.

Pass **extracted text**, not a path to a `.docx` or `.pdf`: a subagent handed one of
those gets nothing readable and will grade an empty document without saying so. Run
`python scripts/doctext.py FILE --text > .markpilot/<doc>/text.txt` once, and reuse that
same file for every round so rounds compare like with like. No change log, no previous scores, no explanation of
what was fixed, no argument for why it now meets the band. A grader that knows what you
were trying to achieve will confirm you achieved it.

---

## Template

> You are marking a student submission. You have never seen it before and you did not
> write any of it.
>
> **Your stance for this pass: [STANCE — see below].**
>
> ### Inputs
> - Criteria sheet: [paste the rubric text, or a path]
> - Task sheet / brief: [paste, or a path]
> - Submission: [path to the EXTRACTED TEXT, or paste it inline]
>
> ### How to mark
>
> Work criterion by criterion, in rubric order. For each one:
>
> 1. **Quote the band descriptor you are marking against** — the exact words from the
>    rubric for the band you are about to award. Not a paraphrase.
> 2. **Quote the evidence from the submission** that does or does not meet it. Give
>    section and, where you can, the sentence. A score with no quoted evidence is not a
>    score; it is an impression.
> 3. **Award the band and the mark**, out of that criterion's stated maximum.
> 4. **State the single highest-value change** that would move this criterion up a band.
>    Be specific enough to act on: "add a counter-argument in §3 addressing X" rather
>    than "deepen the analysis".
>
> ### Rules
>
> - **Award the top band only when the descriptor is fully met.** The top band is almost
>   never awarded for being correct. Check what it asks for beyond correctness —
>   critical evaluation over description, synthesis over listing, an original position,
>   engagement with counter-argument, application to this specific case. If that extra
>   thing is not present, it is not the top band, however well written the work is.
> - **Do not give credit for potential.** Mark what is on the page.
> - **Do not soften.** You are not giving feedback to a student; you are producing the
>   mark that will be recorded. If it is a 78, say 78.
> - **Check the work answers the question actually asked**, not an adjacent one. Quote
>   the task sheet's question and say whether it was answered. This is the most common
>   expensive failure and it is invisible from inside a well-written draft.
> - **Check every explicitly required element is present** — required sections, an
>   executive summary, a specified number of sources, a stated structure. A missing
>   required element is a hard deduction, not a stylistic note.
> - **Flag any claim presented as fact without support**, any statistic without a source,
>   and any reference that looks fabricated (implausible DOI, journal that does not
>   publish in that field, title that reads as invented). You are not expected to verify
>   sources — flag suspicion and move on.
> - Ignore formatting, word count, and reference style unless the rubric scores them.
>   Those are checked separately.
>
> ### Output
>
> A table: criterion | weight | band awarded | mark / max | descriptor quoted | evidence
> quoted | highest-value fix.
>
> Then: **weighted total as a percentage**, and a one-paragraph statement of the single
> biggest thing standing between this submission and full marks.
>
> Do not offer to help fix anything. Return the mark.

---

## The three stances

Run all three in parallel, in one message. The governing score is the **lowest**.

**1. Rubric literalist**
> You mark strictly to the descriptors and nothing else. You do not reward good writing
> that the rubric does not ask for, and you do not forgive a missing element because the
> rest is strong. For every score you must quote the descriptor language you matched.
> Where the submission is close to a band boundary, award the lower band and say what
> the exact wording of the higher one demanded.

**2. Subject marker**
> You are an experienced academic in [DISCIPLINE] marking to the standard of a
> [LEVEL, e.g. third-year undergraduate] course. Beyond the rubric, judge whether the
> argument is sound, the method appropriate, the evidence adequate for the claims, and
> the disciplinary conventions observed. Where the work is confidently wrong about
> something in your field, say so and mark it down — the rubric assumes correctness.

**3. Hostile second marker**
> You are moderating. The first marker gave this a high mark and you suspect they were
> generous. Your job is to find the defensible reason to moderate it down. Attack the
> weakest criterion first. Look for: description dressed as analysis, claims that sound
> supported but are not, sources cited but not actually engaged with, a conclusion that
> does not follow from the body, structural padding, and any requirement of the task
> sheet that has been quietly skipped. Do not manufacture faults — but do not extend
> charity either.

## The regression grader (step 7)

After humanising, run **one** grader with this instead:

> You marked nothing before; treat this as a fresh read. Here is the rubric and the
> submission. For each criterion, state the band it currently sits in with quoted
> evidence. Do not suggest improvements. I am checking whether any criterion has slipped
> below the band it needs — nothing else.

Compare band-by-band against the PER-CRITERION MINIMUM BAND across the three graders
from the final round of Step 2, read from grades-round-N.md. Not the overall
percentage - that cannot tell you which criterion moved. Any criterion that dropped means the
humanising pass removed something the rubric was rewarding; restore those specific
sentences.

## Why lowest-of-three, and not the average

Averaging assumes the graders are noisy measurements of one true score. They are not —
they are three different readings of an ambiguous document, and the real marker is one
person whose reading you cannot predict. If one competent grader can reach 88%, then 88%
is a possible outcome of submitting. The gate exists to make that outcome impossible,
which means clearing the harshest reading, not the mean one.

The corollary: if the three graders disagree by more than about 8 points, the disagreement
itself is the finding. Something in the work is ambiguous enough that markers read it
differently — usually an argument whose position is unclear, or a section whose purpose
the reader has to infer. Fix the ambiguity rather than the score.
