# Figures and charts

A first-draft chart is almost always library output that nobody looked at afterwards. It
is recognisable at a glance, and in a graded document it reads as "pasted from a
notebook" — which costs marks under any criterion about presentation, communication, or
professional standards, and undermines an analysis criterion by making the analysis look
unexamined.

The fix is not "make it prettier". It is: **make it look like it was made for this
document.**

## The tells, and why the hex codes matter

The single most reliable signal is the palette, because library defaults are fixed hex
values and therefore **greppable**. A marker who has read two hundred submissions
recognises `#1f77b4` on sight even without knowing its name.

| Hex | Source | What it says |
|---|---|---|
| `#1f77b4` `#ff7f0e` `#2ca02c` `#d62728` | matplotlib `tab10` default | untouched matplotlib |
| `#4C72B0` `#DD8452` `#55A868` `#C44E52` | seaborn `deep` default | untouched seaborn |
| `#4472C4` `#ED7D31` `#A5A5A5` `#FFC000` | Office 2007+ default | untouched Excel |
| `#636EFA` `#EF553B` `#00CC96` | Plotly default | untouched Plotly |
| viridis / plasma / magma on **categorical** data | notebook habit | a sequential colormap misused for categories |
| `jet` / `rainbow` anywhere | legacy default | perceptually broken; a hard no in most disciplines |

If you have the plotting source, scan it:

```bash
python scripts/figcheck.py FILE --source analysis.py notebook.ipynb
```

Other tells, in rough order of how quickly they give the chart away:

- **All four spines present**, with a box drawn round the plot area.
- **A gridline for every tick**, at full opacity, competing with the data.
- **A legend when direct labelling would do** — two or three series should be labelled at
  the line ends, not in a box the reader has to look back and forth to.
- **The title repeated in both the figure and the caption**, so it appears twice.
- **Title Case Everywhere**, including axis labels.
- **Axis labels that are variable names** — `total_rev_usd`, `pct_chg`, `Unnamed: 0`.
- **Default figure size** (`6.4 × 4.8 in`), pasted at whatever width it landed at, so the
  text ends up a different size from every other figure in the document.
- **Raster export at 72–100 DPI**, visibly soft next to the body text.
- **A pie chart**, especially with more than three slices, or in 3D, or exploded.
- **Emoji or ⭐ in labels.** Never in graded work.
- **Over-annotation**: every point labelled, arrows to nothing, a text box explaining what
  the reader can already see.
- **Truncated y-axis on a bar chart**, which is a correctness problem as much as a style
  one and is worth marks against you if a marker spots it.

## What to do instead

### 1. Match the document, not a design blog

This is the step that does most of the work and the one most often skipped.

- **Font family and size**: the chart's text should be the body font of the document at
  roughly caption size. A Times New Roman report with DejaVu Sans axis labels announces
  that the chart came from somewhere else.
- **Width**: size the figure to the text column so it needs **no rescaling** when placed.
  Rescaling after export is what makes figure text inconsistent across a document. A
  typical A4 report with 2.5 cm margins has a ~16 cm (6.3 in) text column; half-width is
  ~7.7 cm (3.0 in).
- **Consistency across figures**: same palette, same font, same line weights, same axis
  treatment in every figure. Three charts in three styles is worse than three plain ones.

```python
import matplotlib as mpl

mpl.rcParams.update({
    "figure.figsize": (6.3, 3.5),      # match your text column; halve for side-by-side
    "figure.dpi": 300, "savefig.dpi": 300,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "font.family": "serif",             # match the document body font
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y",
    "grid.alpha": 0.25, "grid.linewidth": 0.6,
    "axes.axisbelow": True,             # data draws over the grid, not under it
    "lines.linewidth": 1.6, "lines.markersize": 4,
    "legend.frameon": False,
})
```

Export **vector** (`.pdf` or `.svg`) whenever the target allows it; use `.png` at 300 DPI
only when it does not. Never screenshot a chart.

### 2. Choose a palette on purpose

Colourblind-safe, and **legible in greyscale** — markers print submissions, and a chart
whose three series are indistinguishable in black and white has failed at the one job it
had. Test it: desaturate the image and see whether you can still read it. If not, vary
line style and marker as well as hue.

Okabe–Ito (Wong 2011, *Nature Methods*) is the standard safe set:

```
#E69F00  #56B4E9  #009E73  #F0E442  #0072B2  #D55E00  #CC79A7  #000000
```

Two cautions. It is now common enough to be its own mild tell if used unmodified for
everything — a restrained two- or three-colour subset chosen for your data usually looks
more considered than all eight. And **use the fewest colours the data needs**: one series
needs one colour, and a categorical axis usually needs one colour with a single
highlighted category, not a rainbow. Colour that encodes nothing is decoration.

Reserve a saturated colour for the thing the reader should look at, and grey out the rest
(`#B0BEC5` works well as a neutral). A chart with one highlighted series and four grey
ones communicates a point; five bright series communicate a spreadsheet.

### 3. Fix the labelling

- Axis labels in sentence case with **units**: `Revenue (AUD, millions)`, not `total_rev`.
- Drop the in-figure title when the document has a caption — say it once.
- Direct-label two or three series at their right-hand end instead of using a legend.
- Round tick labels to a sensible precision; `0.0`–`1.0` at two decimals is noise.
- Thousands separators on large numbers.

### 4. Choose the right chart

Position is read more accurately than length, length more than angle, angle more than
area, area more than colour. Bars beat pies; pies beat nothing.

- **Pie**: only for parts of a whole, only with ≤3 slices, never 3D, never exploded. A bar
  chart is nearly always better and no marker has ever complained about one.
- **Bar**: baseline at zero, always. Sort by value unless the category order is meaningful
  (time, ordinal scale).
- **Line**: continuous or time data only — never for unordered categories.
- **Dual y-axes**: avoid. The relationship between the two series can be manufactured by
  choosing the scales, and a careful marker knows it.
- **Stacked bar**: fine for composition, poor for comparing anything but the bottom
  segment.
- **Scatter with a fitted line**: report what the line is and its fit; an unlabelled
  trendline invites the question you do not want asked.

For deeper guidance on chart selection, colour systems, and layout, load the bundled
**`dataviz`** skill — it covers the perceptual rules and palette construction in far more
detail than this file, and it applies to any output medium.

## Captions, numbering and cross-references

This is mechanical, it is worth real marks, and it is checkable:

```bash
python scripts/figcheck.py FILE
```

It verifies that figures and tables are numbered sequentially with no gaps or duplicates,
that each one is referred to at least once in the body text, and that each has a caption.

The conventions:

- **Figure captions go below** the figure. **Table captions go above** the table. This is
  near-universal and getting it backwards is noticed.
- Every figure must be **referred to in the text** — "as Figure 3 shows" — before or at the
  point it appears. A figure the prose never mentions reads as padding.
- Number sequentially in order of first mention: Figure 1, Figure 2, …
- **Cite the data source** under any chart built from someone else's data, in the document's
  referencing style. A chart is a claim; an uncited chart is an unsupported one.
- If the figure is reproduced or adapted from a source, say so: APA 7 wants a `Note.` under
  the figure with the full citation and, for a direct reproduction, a copyright statement.

**APA 7 figure format** (figcheck reads the number-on-its-own-line layout correctly):

```
Figure 1                                    <- bold, own line
Engagement Rate by Cohort Over Twelve Months  <- italic, title case, own line
[the figure]
Note. Adapted from Smith (2020). Data collected March–June 2025.
```

**Harvard / most report styles:**

```
[the figure]
Figure 1: Engagement rate by cohort over twelve months (Smith 2020)
```

Check the task sheet — a course template overrides both.

## What not to do

Do not regenerate a chart you cannot reproduce. If the underlying data or plotting code is
not available, restyling means redrawing from the numbers in the document, and that risks
changing what the chart claims. In that case, report the tells and leave the figure alone
for the author to redo. **Never adjust a data point, an axis range, or a trendline to make
a chart look tidier** — that is falsification, not formatting.
