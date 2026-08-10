# Contributing

## Run the selftest first, and after

```bash
python scripts/selftest.py     # exits non-zero on failure
```

The parsing regexes are the fragile part of this project. Nearly every case in
`selftest.py` is a defect that reached working code and was caught by running the scripts
rather than reading them:

- `n.d.` written as `n\.?\s?d\.?` matched the **"nd" inside "and"**, so every
  `Smith and Jones, 2020` keyed its year as *n.d.* and reported a year mismatch against
  itself.
- Folding `et al.` into the co-author alternation lost **every** `Author et al. (Year)`
  citation, which then reported as an uncited reference.
- `summaris\b` cannot match "summarises" — there is no word boundary mid-word — so
  "Table 1 summarises…" was filed as a caption, stealing the caption text *and* removing
  the table's only cross-reference.
- Filtering sentence connectives against the whole citation made the surnames **An, So,
  Ho and Le** invisible on both sides at once: no orphan raised, and the reference
  dropped from the uncited check too.
- `[3]–[7]` ranges reported their interior numbers as uncited references.
- A `Heading2` inside an appendix ended the appendix, so the rest of it counted against
  the word limit. On a real submission that reported 3,287 words instead of 2,063.

If you change a regex in `doctext.py`, `citecheck.py` or `figcheck.py`, add the case that
made you change it. A regex here without a test is a regression waiting to happen.

## The rule the whole project is built on

**Never report as checked what was not checked.**

A parser handed a document it cannot read produces output identical to a clean document.
That asymmetry is the failure mode this tool exists to prevent, so:

- Every script exits `0` clean, `1` problems found, `2` **could not check**.
- `2` is never a pass. If a script finds zero citations, zero references or zero links, it
  says *could not check* rather than *OK*.
- `BLOCKED` (403/429 publisher bot protection) is never folded into the verified count. It
  is not a failure either — those references are usually fine, but "usually fine" is not
  verified.
- `NO-DNS` is separated from `DEAD` because a name that will not resolve is evidence about
  the network, not about the reference.

A patch that makes any of these quieter will be rejected, however much cleaner it reads.

## CI

There is no CI workflow in this repo. Not an oversight — pushing `.github/workflows/**`
needs the `workflow` OAuth scope, and the repo was published without granting it.

If you want CI, add it through the GitHub web UI (Actions → new workflow), which does not
need that scope. There is nothing to install:

```yaml
name: selftest
on: [push, pull_request]
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.8", "3.12", "3.13"]
        exclude:
          - {os: macos-latest, python: "3.8"}
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "${{ matrix.python }}"}
      # No install step on purpose: this project is standard library only, and a
      # dependency creeping in should break the build.
      - run: python scripts/selftest.py
      - run: python -m compileall -q scripts
```

## Style

- **Standard library only.** No dependencies, no `pip install`, no API keys. It has to run
  on a student laptop with whatever Python is already there (3.8+).
- Comments explain *why*, especially where a regex is subtle. If a line exists because of
  a specific bug, say which.
- Prefer a false positive to a false pass. Wasting someone's time is recoverable; letting
  them submit believing something was verified is not.

## Things worth doing

Known gaps, in rough order of value:

- A politeness delay for Crossref. At 6 workers a 40+ reference list can be throttled, and
  throttling currently surfaces as `BLOCKED`, which reads like a paywall.
- An offline mode. With no network everything becomes `NO-DNS`/`TIMEOUT` and the gate
  demands a human open every link.
- `figcheck` does not handle the Word layout where the number is on one line (`Figure 1`)
  and the caption on the next.
- Charts pasted in as images are checked by nothing; `--source` only sees plotting code.
- PDF text extraction. Every script deliberately refuses `.pdf` rather than guessing.
