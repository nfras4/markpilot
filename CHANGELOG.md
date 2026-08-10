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
