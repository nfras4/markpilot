#!/usr/bin/env python3
"""discover.py - work out which file is the draft, the rubric and the task sheet.

    python discover.py FOLDER
    python discover.py FOLDER --json inputs.json

Exit codes:
    0  a draft and a rubric were both identified
    1  something required is missing or ambiguous (each named)
    2  COULD NOT CHECK - the folder cannot be read

WHY CONTENT BEATS THE FILENAME
------------------------------
The first real folder this was pointed at contained
`RBUS3900 Semester 2 2025 Assessment 1 Rubric.docx`, whose own first line reads
`RBUS3900 Semester 2, 2026`. Trusting the filename would have raised a false alarm
about grading against a previous offering's criteria; trusting the content got it
right. So filenames are a hint and the text inside is the evidence.

The same applies to identifying the draft. "Assessment 1 Briefing" and
"Assessment 1 Rubric" both look like the assignment if you only read names.
A rubric contains band descriptors and weights; a task sheet contains
instructions and a due date; a draft contains a reference list. Those are
checkable.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DOC_EXT = (".docx", ".md", ".txt", ".rtf", ".html", ".htm")
SKIP_DIRS = {".markpilot", ".git", "__pycache__", "node_modules", ".obsidian"}

# Band vocabularies. A rubric almost always enumerates its bands.
BANDS = re.compile(
    r"\b(exceptional|outstanding|advanced|proficient|functional|unsatisfactory"
    r"|high distinction|distinction|credit|pass|fail|excellent|satisfactory"
    r"|exemplary|developing|emerging|beginning)\b", re.I)
WEIGHT = re.compile(r"\b\d{1,3}\s?%")
RUBRIC_WORD = re.compile(r"\b(rubric|criteri(a|on)|marking guide|assessment criteria)\b", re.I)
TASK_WORD = re.compile(
    r"\b(brief|briefing|task sheet|instructions|assessment \d|due date|submission|"
    r"word limit|weighting)\b", re.I)
REFS_WORD = re.compile(r"^\s*(references|reference list|bibliography|works cited)\s*$",
                       re.I | re.M)
OFFERING = re.compile(r"\bsem(?:ester)?\s*([12])\s*,?\s*(20\d\d)\b", re.I)
OFFERING2 = re.compile(r"\b(20\d\d)\s*,?\s*sem(?:ester)?\s*([12])\b", re.I)


def read_text(path, head=20000, tail=8000):
    """Best-effort text: the opening AND the closing of the document.

    Never raises - an unreadable candidate is simply not evidence.

    The tail is not an optimisation, it is the fix for a real misclassification. A
    reference list lives at the END of a document, and it is the single strongest
    signal that a file is the draft rather than a research note. Reading only the
    first 20,000 characters missed it on a 4,700-word proposal, so the real draft
    scored no higher than the notes sitting beside it and the wrong file was picked.
    """
    def clip(text):
        if len(text) <= head + tail:
            return text
        return text[:head] + "\n" + text[-tail:]

    try:
        import doctext
        paras = doctext.load(path)
        return clip("\n".join(p.text for p in paras))
    except SystemExit:
        return ""
    except Exception:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return clip(f.read(head + tail + 1))
        except OSError:
            return ""


def offering(text):
    m = OFFERING.search(text) or None
    if m:
        return f"Semester {m.group(1)}, {m.group(2)}"
    m = OFFERING2.search(text)
    if m:
        return f"Semester {m.group(2)}, {m.group(1)}"
    return None


def score(path, text):
    """(rubric_score, task_score, draft_score). Deliberately additive and readable;
    a clever classifier that cannot be explained is worse than a blunt one that can."""
    # Underscores and hyphens are word characters, so `\bproposal\b` does not match
    # inside `Research_Proposal_DRAFT.docx` - the real draft scored zero on its own
    # name until these were normalised to spaces.
    name = re.sub(r"[_\-.]+", " ", os.path.basename(path).lower())
    words = len(text.split())

    rubric = 0
    if RUBRIC_WORD.search(name):
        rubric += 3
    if RUBRIC_WORD.search(text[:2000]):
        rubric += 2
    bands = len(set(m.group(0).lower() for m in BANDS.finditer(text)))
    if bands >= 4:
        rubric += 4                      # four distinct band names is close to conclusive
    elif bands >= 3:
        rubric += 2
    weights = len(WEIGHT.findall(text))
    if weights >= 4:
        rubric += 2

    task = 0
    if re.search(r"\b(brief|briefing|task|instructions|assessment)\b", name):
        task += 2
    hits = len(set(m.group(0).lower() for m in TASK_WORD.finditer(text)))
    task += min(hits, 4)
    if rubric >= 6:
        task -= 3                        # a rubric is not the task sheet

    draft = 0
    if re.search(r"\b(draft|proposal|report|essay|assignment|submission)\b", name):
        draft += 2
    if REFS_WORD.search(text):
        draft += 3                       # a reference list is the strongest draft signal
    if words > 800:
        draft += 2
    if rubric >= 6 or bands >= 4:
        draft -= 4
    return rubric, task, draft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not os.path.isdir(args.folder):
        print(f"COULD NOT CHECK - {args.folder} is not a folder", file=sys.stderr)
        return 2

    candidates, extras = [], {"plot_sources": [], "images": [], "pdfs": []}
    for root, dirs, files in os.walk(args.folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            path = os.path.join(root, fn)
            low = fn.lower()
            if low.startswith("~$"):
                continue                                   # Word lock file
            if ".markpilot-backup." in low or ".pre-markpilot" in low:
                continue                                   # our own backups
            if low.endswith((".py", ".r", ".ipynb")):
                extras["plot_sources"].append(path)
            elif low.endswith((".png", ".jpg", ".jpeg", ".svg")):
                extras["images"].append(path)
            elif low.endswith(".pdf"):
                extras["pdfs"].append(path)
            elif low.endswith(DOC_EXT):
                candidates.append(path)

    if not candidates:
        print(f"COULD NOT CHECK - no .docx/.md/.txt/.rtf/.html in {args.folder}",
              file=sys.stderr)
        if extras["pdfs"]:
            print("  PDFs found, which no script here reads. Convert first:",
                  file=sys.stderr)
            for p in extras["pdfs"][:5]:
                print("   -", os.path.basename(p), file=sys.stderr)
        return 2

    scored = []
    for p in candidates:
        text = read_text(p)
        r, t, d = score(p, text)
        scored.append({"path": p, "rubric": r, "task": t, "draft": d,
                       "words": len(text.split()), "offering": offering(text)})

    pick = {}
    for kind in ("rubric", "task", "draft"):
        ranked = sorted(scored, key=lambda s: -s[kind])
        best = ranked[0] if ranked else None
        if best and best[kind] > 0 and best["path"] not in pick.values():
            pick[kind] = best["path"]
        elif best and best[kind] > 0:
            for alt in ranked[1:]:
                if alt[kind] > 0 and alt["path"] not in pick.values():
                    pick[kind] = alt["path"]
                    break

    by_path = {s["path"]: s for s in scored}
    print(f"INPUTS in {args.folder}\n")
    for kind, label in (("draft", "draft     "), ("rubric", "rubric    "),
                        ("task", "task sheet")):
        p = pick.get(kind)
        if p:
            s = by_path[p]
            off = f"  [{s['offering']}]" if s["offering"] else ""
            print(f"  {label}  {os.path.basename(p)}{off}")
        else:
            print(f"  {label}  NOT FOUND")
    if extras["plot_sources"]:
        print(f"  plot source {os.path.basename(extras['plot_sources'][0])}"
              + (f" (+{len(extras['plot_sources']) - 1} more)"
                 if len(extras["plot_sources"]) > 1 else ""))

    problems = []
    if "draft" not in pick:
        problems.append("No draft identified. Markpilot refines an existing document "
                        "and stops without one.")
    if "rubric" not in pick:
        problems.append("No rubric identified. The grade gate cannot run, and no "
                        "percentage can be honestly produced. Check Blackboard or the "
                        "course site before running - a rubric found now is worth more "
                        "than every other step in this pipeline.")
    if "task" not in pick:
        problems.append("No task sheet identified. Word limit, referencing style and "
                        "the AI-use policy will have to be supplied by hand.")

    # The offering check, automated. Content governs, not the filename.
    offs = {k: by_path[p]["offering"] for k, p in pick.items() if by_path[p]["offering"]}
    if len(set(offs.values())) > 1:
        detail = ", ".join(f"{k}: {v}" for k, v in offs.items())
        problems.append(
            f"The inputs disagree about which offering this is ({detail}). Criteria and "
            f"weightings get rewritten between offerings, so grading against the wrong "
            f"one produces a confident number nobody should trust.")

    if problems:
        print(f"\n  PROBLEMS ({len(problems)})")
        for p in problems:
            print(f"    - {p}")
    else:
        print("\n  OK - draft, rubric and task sheet all identified")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"picked": pick, "extras": extras, "scored": scored,
                       "problems": problems}, f, indent=2)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
