# markpilot for claude.ai

The Claude Code skill is six Python scripts and a fan-out of independent grading
subagents. **None of that exists in claude.ai** — no shell, no filesystem, no subagents.

So this is not a port. It is a smaller, weaker tool that keeps the parts which can be
made mechanical and is honest about the parts that become judgement.

## What survives, and what does not

| Check | Claude Code | claude.ai | Why |
|---|---|---|---|
| Word count + exclusions | script | **`markpilot-web.js`** | real code, real number |
| Per-section budget | script | **`markpilot-web.js`** | same |
| Citation cross-match | script | **`markpilot-web.js`** | same |
| Figure numbering + cross-refs | script | **`markpilot-web.js`** | same |
| Link / DOI resolution | script + network | ⚠ **web search, one at a time** | the Analysis tool has no network |
| DOI backfill (Crossref) | script | ⚠ **web search, one at a time** | same |
| Grading | **3 independent subagents**, lowest score governs | ⚠ **one pass, self-assessed** | no subagents |
| Quoted-evidence check | script | ⚠ manual | no second context to check the first |
| Report as `.docx` / `.pdf` | script | Claude can write a doc artefact | — |

The two rows that matter most are the last-but-two.

**Grading is materially weaker here.** In Claude Code, three graders with different
stances run in fresh contexts that never see the fixes, and the *lowest* score governs.
In claude.ai the same context that suggested the fixes also judges them — it is marking
its own homework, which is exactly what the Claude Code version is built to prevent. Treat
any score it gives as a rough read, not a gate. If you want the real gate, use Claude Code.

**Reference verification is the other loss.** Fabricated and mis-dated sources are the
highest-severity thing the full pipeline catches, and catching them needs Crossref lookups
in bulk. Here you check them one at a time with web search, or not at all — and "not at
all" must be reported as *not checked*, never as a pass.

## Setup (once)

1. Make a Claude **Project** called something like *Markpilot*.
2. Paste `INSTRUCTIONS.md` (next to this file) into the Project's custom instructions.
3. Upload `markpilot-web.js` to the Project's knowledge, so it is available every chat.

Then, in a new chat in that Project: upload your draft, your rubric and your task sheet,
and say **"run markpilot"**.

No Project? Paste `INSTRUCTIONS.md` as your first message in an ordinary chat and attach
the files. It works; you just repeat the paste each time.

## Using the checker directly

If you only want the numbers, ask Claude to run the Analysis tool with
`markpilot-web.js` pasted in, then:

```js
markpilot(text, { limit: 2000, excludeRefs: true, excludeAppendix: true })
```

It returns word counts, citation cross-matching, figure numbering, and a `notChecked`
list naming what it could not do. Every section carries `checked: true|false` — **false
means could not check, which is never a pass.**

## The rule that carries over unchanged

**Never report as checked what was not checked.** It matters *more* here, not less: in
Claude Code a script that cannot parse something exits `2` and the pipeline stops. Here
there is no exit code, only prose — so the discipline has to come from the instructions
and from you reading the `notChecked` list.

## What it still will not do

Same as the full version, and for the same reasons: it refines a draft rather than writing
one, it flags anything needing your own position or evidence instead of supplying it, it
will not invent a source or a page number, and it helps you comply with your course's
AI-use policy rather than around it.
