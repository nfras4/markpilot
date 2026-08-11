#!/usr/bin/env python3
"""docxpatch.py - apply text edits to a .docx without disturbing anything else.

    python docxpatch.py FILE --edits edits.json          apply
    python docxpatch.py FILE --edits edits.json --dry    report, change nothing
    python docxpatch.py FILE --find "old text"           is this reachable?

`edits.json` is a list of objects:

    [{"old": "a medium main effect", "new": "a main effect of f = .20",
      "why": "Cohen's f medium is .25", "authored": false}]

Exit codes follow the rest of this skill:

    0  every edit applied and verified
    1  some edit could not be applied (each named)
    2  could not check - the file could not be read or rewritten

WHY THIS EXISTS
---------------
Markpilot's fix-and-regrade loop edits extracted text, because `.docx` is a zip and
Write/Edit cannot touch it. That leaves the user holding a score for a text file
and a document that has not changed. This closes that gap: the loop stays on text,
and the accumulated edits are written back into the real document at the end.

THE PROBLEM THIS SOLVES
-----------------------
Word splits a paragraph into runs (`<w:r>`) wherever formatting changes, and the
split lands mid-sentence far more often than you would guess. In a real reference
list this appeared as:

    <w:t>Journal of Service Research, 14</w:t>     (italic volume)
    <w:t>(3), 252-271.</w:t>

so the string `14(3), 252-271.` does not exist anywhere in document.xml, and a
naive `xml.replace(old, new)` silently does nothing while reporting success. Of six
edits attempted by hand against one real assignment, one target was invisible for
exactly this reason.

So this works on the *paragraph's* concatenated text, maps each character back to
the run it came from, and rewrites only the runs the match actually covers. The
replacement inherits the formatting of the first run it touches, which is correct
for the corrections this tool makes (a mislabelled effect size, a wrong year) and
is why this deliberately does NOT try to restructure, restyle, or move content.

WHAT IT WILL NOT DO
-------------------
Not a general Word editor. No inserting paragraphs, no changing styles, no tables,
no moving content. Text substitution inside existing paragraphs, and nothing else -
because every capability added here is a new way to corrupt somebody's submission
the day before it is due.
"""

import argparse
import json
import os
import re
import shutil
import sys
import zipfile

DOC = "word/document.xml"
# A run: <w:r ...> ... <w:t ...>text</w:t> ... </w:r>. We only ever rewrite the
# text inside <w:t>, never the run's properties.
RUN_RE = re.compile(r"(<w:r(?:\s[^>]*)?>)(.*?)(</w:r>)", re.S)
TEXT_RE = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.S)
PARA_RE = re.compile(r"(<w:p(?:\s[^>]*)?>)(.*?)(</w:p>)", re.S)


def xml_unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'")
             .replace("&amp;", "&"))


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;"))


def para_runs(para_body):
    """[(start, end, prefix, text, suffix, whole_match_span)] for each <w:t> in order.

    `start`/`end` are offsets into the paragraph's visible text, so a match found in
    that text can be mapped back to the runs it covers."""
    out, cursor = [], 0
    for m in TEXT_RE.finditer(para_body):
        text = xml_unescape(m.group(2))
        out.append({
            "vis_start": cursor,
            "vis_end": cursor + len(text),
            "text": text,
            "span": m.span(),
            "open": m.group(1),
            "close": m.group(3),
        })
        cursor += len(text)
    return out


def visible_text(para_body):
    return "".join(xml_unescape(m.group(2)) for m in TEXT_RE.finditer(para_body))


def minimal_edit(old, new):
    """Trim the shared head and tail, returning the smallest substitution that does
    the same job: (offset_into_old, old_middle, new_middle).

    This is not a tidiness measure, it is the whole reason formatting survives.
    Appending a DOI to `...Journal of Service Research, 14(3), 252-271.` matches text
    spanning an italic run (the journal name and volume) and a roman one (the issue,
    pages, DOI). Replacing the full match dumps all of it into the first run, so the
    page range and the DOI come out italic - an APA error introduced by the tool
    meant to fix APA errors, in a document where Referencing is separately marked.

    Reduced to the minimal edit, the change is a pure insertion at the very end,
    which lands inside the roman run and leaves the italic one untouched."""
    head = 0
    while head < len(old) and head < len(new) and old[head] == new[head]:
        head += 1
    tail = 0
    while (tail < len(old) - head and tail < len(new) - head
           and old[len(old) - 1 - tail] == new[len(new) - 1 - tail]):
        tail += 1
    return head, old[head:len(old) - tail], new[head:len(new) - tail]


def apply_to_paragraph(para_body, old, new):
    """Replace the first occurrence of `old` in this paragraph. (body, True) or (body, False).

    Only the minimally-differing span is rewritten, so an edit that merely appends or
    tweaks inside one run cannot disturb the formatting of its neighbours. Where the
    reduced span genuinely straddles a run boundary the new text takes the first
    touched run's formatting, because something has to, and the covered portion is
    removed from the runs after it. Any run left with no text keeps an empty <w:t>
    rather than being deleted, so numbering, bookmarks and comment anchors that
    reference it survive."""
    vis = visible_text(para_body)
    found = vis.find(old)
    if found < 0:
        return para_body, False
    # Shrink to the part that actually changes.
    offset, old_mid, new_mid = minimal_edit(old, new)
    at = found + offset
    end = at + len(old_mid)
    new = new_mid

    pieces = para_runs(para_body)

    if at == end:
        # A pure insertion has zero width, so no run is "covered" and the loop below
        # would match nothing and silently report failure. Choose the run explicitly,
        # preferring the one that ENDS here so the text appends with that run's
        # formatting rather than the next run's. Appending a DOI to a reference then
        # inherits the roman run carrying the page range, not the italic run carrying
        # the volume number.
        target = None
        for p in pieces:
            if p["vis_start"] <= at <= p["vis_end"]:
                target = p
                if p["vis_end"] == at:
                    break
        if target is None:
            return para_body, False
        cut = at - target["vis_start"]
        keep = target["text"][:cut] + new + target["text"][cut:]
        s, e = target["span"]
        return (para_body[:s] + target["open"] + xml_escape(keep)
                + target["close"] + para_body[e:]), True

    edits = []                       # (span, replacement_text) per run
    for p in pieces:
        if p["vis_end"] <= at or p["vis_start"] >= end:
            continue                 # untouched by the match
        lead = p["text"][:max(0, at - p["vis_start"])]
        tail = p["text"][max(0, end - p["vis_start"]):]
        if not edits:
            keep = lead + new + tail          # first touched run carries the new text
        else:
            keep = lead + tail
        edits.append((p["span"], p["open"] + xml_escape(keep) + p["close"]))

    if not edits:
        return para_body, False
    for (s, e), replacement in reversed(edits):   # right to left; offsets stay valid
        para_body = para_body[:s] + replacement + para_body[e:]
    return para_body, True


def patch_xml(xml, old, new):
    """(xml, count) - replaces the first occurrence, paragraph by paragraph."""
    out, last, count = [], 0, 0
    for m in PARA_RE.finditer(xml):
        if count:
            break
        body, hit = apply_to_paragraph(m.group(2), old, new)
        if hit:
            out.append(xml[last:m.start()])
            out.append(m.group(1) + body + m.group(3))
            last = m.end()
            count = 1
    out.append(xml[last:])
    return "".join(out), count


def read_doc(path):
    with zipfile.ZipFile(path) as z:
        return z.read(DOC).decode("utf-8")


def write_doc(src, dst, xml):
    """Rewrite the archive, replacing only document.xml. Every other part - images,
    styles, numbering, relationships - is copied byte for byte."""
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == DOC:
                data = xml.encode("utf-8")
            zout.writestr(item, data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--edits", help="JSON list of {old,new,why,authored}")
    ap.add_argument("--find", help="report whether this text is reachable, change nothing")
    ap.add_argument("--dry", action="store_true", help="report, write nothing")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.file.lower().endswith(".docx"):
        print("error: docxpatch only handles .docx", file=sys.stderr)
        return 2
    try:
        xml = read_doc(args.file)
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        print(f"COULD NOT CHECK - {args.file} could not be read ({type(e).__name__})",
              file=sys.stderr)
        return 2

    if args.find:
        paras = [visible_text(m.group(2)) for m in PARA_RE.finditer(xml)]
        n = sum(p.count(args.find) for p in paras)
        contiguous = xml.count(args.find)
        print(f"reachable in paragraph text : {n}")
        print(f"contiguous in raw xml       : {contiguous}"
              + ("   <- naive replace would work" if contiguous else
                 "   <- split across runs; naive replace would silently fail"))
        return 0 if n else 1

    if not args.edits:
        ap.print_help()
        return 0
    try:
        with open(args.edits, encoding="utf-8") as f:
            edits = json.load(f)
    except (OSError, ValueError) as e:
        print(f"COULD NOT CHECK - {args.edits} unreadable ({type(e).__name__})",
              file=sys.stderr)
        return 2

    applied, failed = [], []
    for e in edits:
        old, new = e.get("old", ""), e.get("new", "")
        if not old:
            failed.append((e.get("why", "?"), "no 'old' given"))
            continue
        xml, n = patch_xml(xml, old, new)
        if n == 1:
            applied.append(e)
        else:
            failed.append((e.get("why") or old[:48], "not found in any paragraph"))

    for e in applied:
        mark = "  [AUTHORED]" if e.get("authored") else ""
        print(f"  + {e.get('why') or e['old'][:60]}{mark}")
    for why, reason in failed:
        print(f"  ! {why} - {reason}", file=sys.stderr)

    if args.dry:
        print(f"\ndry run: {len(applied)} would apply, {len(failed)} would not")
        return 1 if failed else 0

    if applied:
        if not args.no_backup:
            bak = args.file[:-5] + ".markpilot-backup.docx"
            if not os.path.exists(bak):
                shutil.copy(args.file, bak)
                print(f"\n  backup: {bak}")
        tmp = args.file + ".tmp"
        try:
            write_doc(args.file, tmp, xml)
            # Verify before replacing the original: a patched file that will not
            # reopen is worse than one that was never patched.
            check = zipfile.ZipFile(tmp)
            if check.testzip() is not None:
                raise zipfile.BadZipFile("testzip reported a corrupt member")
            reread = check.read(DOC).decode("utf-8")
            check.close()
            for e in applied:
                if e["new"] and e["new"] not in visible_text_all(reread):
                    raise ValueError(f"edit did not survive the rewrite: {e['new'][:40]}")
            os.replace(tmp, args.file)
        except Exception as ex:                       # noqa: BLE001 - report, never half-write
            if os.path.exists(tmp):
                os.remove(tmp)
            print(f"COULD NOT CHECK - not written ({type(ex).__name__}: {ex})",
                  file=sys.stderr)
            return 2
        print(f"\n  wrote {args.file}")

    print(f"\n{len(applied)} applied, {len(failed)} not applied")
    return 1 if failed else 0


def visible_text_all(xml):
    return "".join(xml_unescape(m.group(2)) for m in TEXT_RE.finditer(xml))


if __name__ == "__main__":
    sys.exit(main())
