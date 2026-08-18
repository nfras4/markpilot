# TODO

## AI-writing-tell detector + gate  (buildable — DO THIS ONE)

Add a detector that scans the draft for the stylistic tells that mark text as
AI-written — em-dash overuse, AI vocabulary (delve/tapestry/testament/vibrant/
underscore), rule-of-three cadence, hedging, sycophancy, signposting, uniform
paragraph rhythm, copula avoidance — and wire it in as a **gate**, not just a
report: the pre-submission run fails/flags until the draft passes, the same way
the other checks gate.

Notes:
- This is the *verification* counterpart to the existing humanising pass:
  humanising rewrites, the detector proves the rewrite worked. Keep them as
  separate passes (writer lane vs checker lane).
- Standalone script like the other checks: exit non-zero on findings, never
  report clean on a file it couldn't read (per the "never report as checked
  what was not checked" rule).
- Score per-section so one clean section doesn't mask a dirty one.
- Overlaps heavily with the OMC `humaniser` skill's rule list — reuse that
  taxonomy rather than inventing a new one.

## SynthID statistical watermark  (BLOCKED — do NOT promise removal)

Separate, harder problem — do not conflate with the style-tell detector above.

Since 2026-08-02 Anthropic embeds a **SynthID-Text** watermark (Google DeepMind,
Nature 2024) into Claude/Claude Code output. Key facts, researched 2026-08-18:

- It is a **statistical signal in the model's token choices**, NOT invisible
  Unicode characters bolted on afterward. Stripping weird code points does
  nothing to it. It survives light editing and follows the text.
- **Anthropic has not released a detector or spec.** Therefore NO tool can prove
  it removed the mark. Every "watermark remover" online is currently
  unfalsifiable (see BleepingComputer: "almost none can prove they work").
- Plausible disruption requires a **substantial rewrite through a NON-Claude
  model** — which we can't do inside a Claude-only skill, and which flattens
  tone/voice/precision anyway.

Implication for markpilot: we CANNOT credibly build a SynthID detector or
remover. If graded work must be watermark-free, that is an external step (rewrite
via a different model), not a markpilot check. Park this until Anthropic ships a
detector.

Prior art (both fresh, neither verified):
- github.com/aloshdenny/claude-awm — research repo; found Unicode tricks degrade
  detection but "every invisible-character attack gets reverted by one line of
  input normalization".
- Guillaume Meyer's `watermarks-remover` — packaged as an agent skill; strips
  metadata + best-effort model rewrite, self-described as "not a verified
  deletion".
