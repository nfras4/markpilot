# Referencing checks

Confirm the **style and edition** from the task sheet before using any of this. "APA"
without an edition is ambiguous and APA 6 and APA 7 disagree on several of the rules
below. If the task sheet names a university style guide (UQ Harvard, for instance),
that guide overrides the generic form — house styles vary in punctuation and in whether
a place of publication is required.

## Check integrity before format

Run `python scripts/citecheck.py FILE --style <style>` first. Format errors cost a mark
or two. A citation that does not resolve, or a source that does not exist, is a
different category of problem.

Then resolve every link and DOI — mandatory, and scripted:

```bash
python scripts/linkcheck.py FILE
```

It fetches every URL and queries Crossref for every DOI, then compares the returned
title, first author and year against the words of the reference entry. That catches the
case a status code cannot: a DOI that resolves perfectly but to a different paper.

Read the statuses carefully. `BLOCKED` (403/429) means publisher bot protection, not a
broken link — those references are usually fine, but "usually fine" is not verified, so
open them. `LIVE` is the only status that counts as confirmed.

For sources without a DOI, search the exact title in quotes; a title that returns nothing
anywhere is very likely invented.

Common fabrication tells, in rough order of reliability:
- DOI prefix that does not belong to the named publisher, or a DOI that 404s
- a plausible journal, plausible authors, plausible title — but no combination of the
  three appears anywhere
- page ranges that do not exist in that volume, or a volume that predates the journal
- an author who works in the field but has never published on that topic
- everything in the list dated within two or three years of each other with no seminal
  older work — a strong smell in a literature review

---

## APA 7

**In-text.** `(Smith, 2020)` · `(Smith & Jones, 2020, p. 14)` · narrative:
`Smith and Jones (2020) found`. Ampersand inside parentheses, "and" outside.

- Three or more authors: `(Smith et al., 2020)` **from the first citation** — APA 7
  dropped APA 6's first-mention-lists-all rule.
- Two authors: always both, every time.
- Multiple works in one parenthesis: alphabetical, semicolon-separated.
- Same author, same year: `2020a`, `2020b`, ordered by title in the reference list.
- Direct quote: page number required. Paraphrase: page number encouraged, not required.

**Reference list.** Hanging indent, alphabetical by first author surname, double-spaced.

```
Author, A. A., & Author, B. B. (2020). Title of the article in sentence case.
    Journal Name in Title Case Italicised, 34(2), 118–142.
    https://doi.org/10.1000/xyz123

Author, A. A. (2019). Title of the book in sentence case and italicised (3rd ed.).
    Publisher.
```

Errors this catches most often:
- **"Retrieved from"** — dropped in APA 7 unless a retrieval date is genuinely needed
  (content designed to change, e.g. a wiki page).
- **Publisher location** — dropped in APA 7. `New York, NY: Routledge` is APA 6.
- **`Vol. 34, No. 2`** — APA uses `34(2)`, volume italicised, issue not.
- **`doi:10.1000/xyz`** — APA 7 wants the full `https://doi.org/10.1000/xyz`.
- **et al. in the reference list** — list up to 20 authors; with 21+, list the first 19,
  an ellipsis, then the final author.
- **Title case in article titles** — APA uses sentence case for article and book titles,
  title case for the journal name.
- Up to 20 authors listed in full; the ampersand goes before the last.

**Citing generative AI (APA 7).** APA treats it as software:

```
OpenAI. (2024). ChatGPT (Mar 14 version) [Large language model].
    https://chat.openai.com/chat
```
In-text: `(OpenAI, 2024)`. Anthropic's Claude takes the same shape with
`Anthropic. (2026). Claude (Opus 5) [Large language model]. https://claude.ai`.
Check the task sheet — many courses want the prompts and outputs in an appendix as well.

---

## Harvard (generic; check the local variant)

**In-text.** `(Smith 2020)` — **no comma** before the year in most Harvard variants,
though several university house styles do use one. Check the guide the course names.
Page: `(Smith 2020, p. 14)`.

**Reference list.** Alphabetical, hanging indent.

```
Smith, J & Jones, A 2020, 'Title of the article in single quotes',
    Journal Name, vol. 34, no. 2, pp. 118–142.

Smith, J 2019, Title of the book in italics, 3rd edn, Publisher, Place.
```

- Harvard keeps `vol.`/`no.`/`pp.` labels — the opposite of APA.
- Article titles in single quotation marks; journal and book titles italicised.
- `&` between the final two authors, no comma before it in most variants.
- Web sources take an access date: `viewed 10 August 2026, <URL>`.
- Place of publication is usually still required.

---

## IEEE

**In-text.** Bracketed numbers in order of first appearance: `[1]`, `[2], [5]`,
`[3]–[7]`. The number belongs to the source permanently — reuse it, never renumber on
re-citation. Numbers sit inside the punctuation: `... as shown in [4].`

**Reference list.** Numerical order — **not** alphabetical.

```
[1] J. Smith and A. Jones, "Title of the paper in quotes," Journal Name Abbrev.,
    vol. 34, no. 2, pp. 118–142, Mar. 2020, doi: 10.1000/xyz123.
```

- Initials **before** surname: `J. Smith`, not `Smith, J.`
- Journal names abbreviated per IEEE's list.
- Six or more authors: first author then `et al.`
- Reordering the reference list means renumbering every in-text citation. Check both
  after any edit that adds or removes a source.

---

## Vancouver (health sciences)

Superscript or bracketed numbers in order of appearance; numbered reference list.

```
1. Smith J, Jones A. Title of the article in sentence case. Journal Abbrev.
   2020;34(2):118-42.
```

- No italics anywhere; no quotation marks around titles.
- No period after author initials, no ampersand — authors comma-separated.
- Journal abbreviations per NLM.
- Six authors then `et al.`
- Page ranges elide: `118-42`, not `118-142`.

---

## Chicago

Two systems that are not interchangeable — confirm which one the course wants.

**Notes-bibliography.** Superscript number → footnote. First note gives the full
citation; later notes shorten to `Smith, Title, 42.` Bibliography at the end,
alphabetical, hanging indent.

**Author-date.** `(Smith 2020, 14)` in text — no comma, no `p.` — with a reference list
headed "References".

---

## MLA 9

**In-text.** `(Smith 14)` — author and page, **no year, no comma**.

**Works Cited.** Alphabetical, hanging indent.

```
Smith, John, and Alice Jones. "Title of the Article in Title Case." Journal Name,
    vol. 34, no. 2, 2020, pp. 118-42.
```

- Three or more authors: first author then `et al.`
- Titles in title case; containers italicised.

---

## AGLC 4 (Australian law)

Footnotes only — there is no in-text citation and usually no bibliography unless the
task sheet asks for one.

```
1  Jane Smith, 'Title of the Article' (2020) 34(2) Journal Name 118, 121.
2  Mabo v Queensland (No 2) (1992) 175 CLR 1, 42.
3  Copyright Act 1968 (Cth) s 51(1).
```

- Pinpoint after the starting page, comma-separated: `118, 121`.
- Cases italicised; statutes not; jurisdiction in parentheses after the Act's year.
- Full stop at the end of every footnote.
- `Ibid` for the immediately preceding footnote; short form thereafter.

---

## Things to check regardless of style

- Every in-text citation appears in the list, and every list entry is cited. Run
  `citecheck.py` — do not eyeball it.
- Secondary citations are marked as such (`as cited in`) and not passed off as direct
  reading of the original.
- Direct quotes carry page numbers and the quoted words match the source exactly.
- Block-quote threshold observed (APA: 40+ words; Harvard: usually 30+).
- Hanging indent applied as a paragraph setting, not with manual spaces or tabs — manual
  spacing collapses on conversion and is visible to a marker.
- Alphabetical ordering is actually correct, including `Mac`/`Mc`, hyphenated surnames,
  and multiple works by the same first author.
- DOIs present wherever one exists. A missing DOI is a mark; an invented one is not.
