#!/usr/bin/env python3
"""figcheck.py - check figure/table numbering, cross-references, and chart-style tells.

Stdlib only. No network.

    python figcheck.py FILE
    python figcheck.py FILE --source analysis.py plots.ipynb

Two independent checks:

1. NUMBERING AND CROSS-REFERENCES (always). Every figure and table must be numbered
   sequentially with no gaps or duplicates, must carry a caption, and must be referred
   to at least once in the body text.

2. CHART-STYLE TELLS (--source). Two different signals, and the second matters more:
     a) explicit default palette hex values in the source;
     b) plotting calls with NO styling of any kind anywhere in the file.
   (b) is the one that catches an untouched chart. An unstyled matplotlib figure
   contains no hex literals at all - the colours come from rcParams, not the source -
   so scanning for hex codes alone reports "clean" on precisely the input this check
   exists to catch. Writing a hex value is evidence somebody made a colour DECISION;
   writing none is evidence nobody did.

Exit codes:
    0  nothing found
    1  numbering or cross-reference problems
    2  style tells only
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doctext import load, norm, is_section_break, is_caption_line  # noqa: E402

KINDS = r"(?:Figure|Fig\.?|Table|Chart|Exhibit|Graph)"
INTEXT_REF = re.compile(r"\b(" + KINDS + r")\s*([A-Z]?\d+(?:\.\d+)*)\b", re.I)

# Library default palettes: the actual constants the libraries emit.
PALETTES = {
    "matplotlib tab10 default": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                                 "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"],
    "seaborn deep default": ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3"],
    "Office/Excel default": ["#4472c4", "#ed7d31", "#a5a5a5", "#ffc000", "#5b9bd5"],
    "Plotly default": ["#636efa", "#ef553b", "#00cc96", "#ab63fa", "#ffa15a"],
}

PLOT_CALL = re.compile(
    r"(?i)\b(?:plt|pyplot|ax|axes|sns|seaborn|px|go|alt)\s*\.\s*"
    r"(?:plot|bar|barh|hist|scatter|pie|line|boxplot|violinplot|heatmap|imshow|"
    r"stackplot|fill_between|errorbar|subplots|figure)\b"
    r"|\.plot\s*\(|\bggplot\s*\(")
STYLING = re.compile(
    r"(?i)\brcParams\b|\bstyle\.use\s*\(\s*['\"][^'\"]+['\"]|\bset_theme\s*\([^)]*\w"
    r"|\bset_palette\b|\bcolor\s*=|\bcolors\s*=|\bcolour\s*=|\bc\s*=\s*['\"#]"
    r"|\bpalette\s*=|\bcmap\s*=|\bcolormap\s*=|\bset_style\s*\(|\bmpl\.style\b"
    r"|\bplt\.rc\s*\(|\bmatplotlibrc\b|\btheme\s*\(|\bset_prop_cycle\b")

SOURCE_TELLS = [
    (r"(?i)\bcmap\s*=\s*['\"](jet|rainbow|hsv)['\"]",
     "perceptually broken colormap (jet/rainbow) - use a sequential or diverging map"),
    (r"(?i)\b(?:plt|ax|sns)\w*\.pie\(",
     "pie chart - use a bar chart unless this is <=3 parts of a whole"),
    (r"(?i)projection\s*=\s*['\"]3d['\"]|Axes3D|\bexplode\s*=",
     "3D or exploded chart - reads as decoration, hurts accurate reading"),
    (r"(?i)\bsns\.set\(\s*\)|\bsns\.set_theme\(\s*\)|plt\.style\.use\(\s*['\"]seaborn[^'\"]*['\"]\s*\)",
     "bare seaborn theme call - applies the default palette untouched"),
    (r"(?i)cmap\s*=\s*['\"](viridis|plasma|magma|inferno)['\"].{0,80}?\b(bar|categor|pie)\b",
     "sequential colormap used for categorical data"),
    (r"(?i)\bdpi\s*=\s*(?:[1-9]\d?|1[0-4]\d)\b",
     "export DPI below 150 - will look soft next to body text; use 300"),
    (r"[\U0001F300-\U0001FAFF☀-➿]",
     "emoji in plotting source - never in graded work"),
]


def sections(paras):
    """Body paragraphs only - the reference list is not where figures live."""
    out = []
    for p in paras:
        if is_section_break(p.text, "refs"):
            break
        out.append(p)
    return out


def normnum(k, n):
    k = k.lower().rstrip(".")
    k = "figure" if k in ("fig", "figure", "graph", "chart") else k
    return k, n.upper()


def series_of(num):
    """Split a figure number into (series, parts).

    "2.1" is chapter numbering, not figure 2 - taking only the first integer
    invents gaps ("missing [1]") in every chapter-numbered report. "A1" is an
    appendix series and must not be folded into the main sequence."""
    m = re.match(r"^([A-Z]*)([\d.]+)$", num.upper())
    if not m:
        return num.upper(), ()
    alpha, digits = m.group(1), m.group(2)
    parts = tuple(int(x) for x in digits.split(".") if x != "")
    if len(parts) > 1:                       # 2.1 -> series "2", index 1
        return (alpha + str(parts[0])), parts[1:]
    return alpha, parts


def check_document(path):
    paras = sections(load(path))
    captions, cap_seen = {}, []
    cap_idx = {}       # paragraph index -> the key it captions
    for i, p in enumerate(paras):
        t = norm(p.text).strip()
        if not t:
            continue
        ok, kind, num, rest = is_caption_line(t)
        if ok:
            key = normnum(kind, num)
            captions.setdefault(key, rest)
            cap_seen.append(key)
            cap_idx[i] = key

    refs = {}
    for i, p in enumerate(paras):
        own = cap_idx.get(i)
        for m in INTEXT_REF.finditer(norm(p.text)):
            key = normnum(m.group(1), m.group(2))
            # A caption paragraph is not a cross-reference to ITSELF, but a caption
            # reading "Figure 3. Comparison against the baseline in Figure 2" IS a
            # reference to Figure 2. Dropping the whole paragraph loses that.
            if own is not None and key == own:
                continue
            refs[key] = refs.get(key, 0) + 1

    problems = []
    print("FIGURES AND TABLES")
    if not captions and not refs:
        print("  No figures or tables found.")
        return []

    for kind in ("figure", "table", "exhibit"):
        nums = [k[1] for k in captions if k[0] == kind]
        if not nums:
            continue
        nums.sort(key=lambda n: (series_of(n)[0], series_of(n)[1]))
        print(f"\n  {kind.title()}s captioned: {', '.join(nums)}")

        occ = [k[1] for k in cap_seen if k[0] == kind]
        dupes = sorted({n for n in occ if occ.count(n) > 1})
        if dupes:
            problems.append(
                f"{kind} number captioned more than once: "
                + ", ".join(f"{kind.title()} {d} (x{occ.count(d)})" for d in dupes))

        # Check sequence within each series independently.
        by_series = {}
        for n in nums:
            s, parts = series_of(n)
            if parts:
                by_series.setdefault(s, []).append(parts[0])
        for s, ints in sorted(by_series.items()):
            label = f"{kind} {s}.x" if s and s[0].isdigit() else (
                f"{kind} (appendix {s})" if s else kind)
            missing = sorted(set(range(1, max(ints) + 1)) - set(ints))
            if missing:
                problems.append(f"{label} numbering has gaps: missing {missing}")
            if 1 not in ints:
                problems.append(f"{label} numbering does not start at 1")

        for n in nums:
            key = (kind, n)
            if refs.get(key, 0) == 0:
                problems.append(
                    f"{kind.title()} {n} is never referred to in the body text - "
                    f"a figure the prose never mentions reads as padding")
            if not captions[key]:
                problems.append(f"{kind.title()} {n} has a number but no caption text")

    for key, count in sorted(refs.items()):
        if key not in captions:
            problems.append(
                f"body text refers to {key[0].title()} {key[1]} ({count}x) but no such "
                f"caption exists")

    if problems:
        print(f"\n  PROBLEMS ({len(problems)})")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  OK - numbered sequentially, all captioned, all cross-referenced")
    return problems


def notebook_source(raw):
    try:
        nb = json.loads(raw)
    except ValueError:
        return raw
    cells = nb.get("cells")
    if cells is None:                       # nbformat v3: worksheets[].cells, "input"
        cells = [c for ws in nb.get("worksheets", []) for c in ws.get("cells", [])]
    joined = "\n".join(
        "".join(c.get("source") or c.get("input") or []) for c in cells)
    return joined if joined.strip() else raw


def scan_source(paths):
    hits = []
    for path in paths:
        if not os.path.exists(path):
            print(f"  (skipped, not found: {path})")
            continue
        raw = open(path, "rb").read().decode("utf-8", "replace")
        if path.endswith(".ipynb"):
            raw = notebook_source(raw)
        low = raw.lower()

        for name, hexlist in PALETTES.items():
            found = [h for h in hexlist if h in low]
            if found:
                hits.append((path, f"{name} written out explicitly "
                                   f"({', '.join(found[:4])})"))

        # The important one: charts drawn with no styling anywhere in the file.
        if PLOT_CALL.search(raw) and not STYLING.search(raw):
            hits.append((path, "plotting calls with NO styling anywhere in the file - "
                               "this chart is pure library default (font, palette, "
                               "spines, size, DPI)"))

        for pat, msg in SOURCE_TELLS:
            if re.search(pat, raw):
                hits.append((path, msg))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--source", nargs="*", default=[],
                    help="plotting source to scan for default-styling tells")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        sys.exit(f"error: no such file: {args.file}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    problems = check_document(args.file)

    hits = []
    if args.source:
        print("\nCHART STYLE TELLS")
        hits = scan_source(args.source)
        if hits:
            for path, msg in hits:
                print(f"    - {os.path.basename(path)}: {msg}")
            print("\n  See references/charts.md. Do NOT redraw a chart you cannot")
            print("  reproduce from its data - report it and leave it to the author.")
        else:
            print("  No default-palette or default-styling tells found.")
            print("  NOTE: this only sees the source you passed. A chart pasted in as")
            print("  an image, or built in Excel, is not checked by anything here.")
    else:
        print("\n  (no --source given: chart styling was NOT checked)")

    return 1 if problems else (2 if hits else 0)


if __name__ == "__main__":
    sys.exit(main())
