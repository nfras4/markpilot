#!/usr/bin/env python3
"""doifind.py - find the DOI for reference entries that do not carry one, and check
the year the entry uses against the record.

Stdlib only. Network required (Crossref).

    python doifind.py FILE
    python doifind.py FILE --json found.json --min-score 0.6

Why this exists
---------------
linkcheck.py can only verify a reference that already carries an identifier. On a real
submission 23 of 29 entries had none, so they were unverifiable by anything - and
"unverifiable" is where fabricated and mis-dated references survive. This closes that
loop: look the entry up by its own text, and report what the record says.

The year check is the point
---------------------------
Crossref distinguishes `published-online` from `published-print`. An article published
online in one year and issued in the next is the single most common citation error in
student work, and both years look equally defensible until you check. Where they differ
this prints BOTH and says which one the entry used, rather than asserting a correction.

Matching is deliberately conservative. A wrong DOI is worse than no DOI, so a candidate
must clear a title-overlap threshold AND have its first author's surname present in the
entry. Anything short of that is reported as a weak match for a human to settle, never
silently applied.
"""

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doctext import load, norm, die  # noqa: E402
from citecheck import (split_sections, ref_entries, ref_key,  # noqa: E402
                       author_matches)

UA = "markpilot-doifind/1.0 (https://github.com/nfras4/markpilot; mailto:markpilot@local)"
DOI_IN = re.compile(r"(?i)\b10\.\d{4,9}/[^\s<>\"'\]\),;]+")
URL_IN = re.compile(r"(?i)\bhttps?://\S+")
STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "over", "under",
        "study", "studies", "analysis", "research", "journal", "review", "effects",
        "effect", "evidence", "using", "toward", "towards", "role", "case"}


def toks(s):
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower()) if w not in STOP}


def crossref_query(entry, rows, timeout, attempts=4):
    """Retries on 429/503 with linear backoff. Crossref rate-limited a 29-entry
    run at 3 workers, and a rate limit reported as QUERY-FAILED looks like a
    missing source rather than a busy server."""
    for i in range(attempts):
        out = _crossref_once(entry, rows, timeout)
        if not (isinstance(out, dict) and str(out.get("__error__", "")).startswith(
                ("HTTP 429", "HTTP 503"))):
            return out
        if i < attempts - 1:
            time.sleep(2.0 * (i + 1))
    return out


def _crossref_once(entry, rows, timeout):
    # Trim trailing URLs and the tail after the page range - they add noise and the
    # bibliographic index does better with author + year + title + container.
    q = re.sub(r"(?i)https?://\S+", " ", entry)
    q = re.sub(r"\s+", " ", q).strip()[:400]
    url = ("https://api.crossref.org/works?rows=%d&select=DOI,title,author,"
           "container-title,issued,published-print,published-online,page,volume,type"
           "&query.bibliographic=%s" % (rows, urllib.parse.quote(q)))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))["message"]["items"]
    except urllib.error.HTTPError as e:
        return {"__error__": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"__error__": f"{type(e).__name__}"}


def years_of(item):
    """(print_year, online_year, issued_year) as strings, '' when absent."""
    def y(key):
        parts = (item.get(key) or {}).get("date-parts") or []
        return str(parts[0][0]) if parts and parts[0] and parts[0][0] else ""
    return y("published-print"), y("published-online"), y("issued")


def score(item, entry):
    title = (item.get("title") or [""])[0]
    tt, et = toks(title), toks(entry)
    if not tt:
        return 0.0, title
    return len(tt & et) / len(tt), title


def letters(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def first_author_ok(item, entry):
    """Delegates to citecheck.author_matches - see the failure modes documented
    there. Kept as a name because selftest and the docs refer to it."""
    return author_matches(item, entry)


CORPORATE = re.compile(
    # The joiner alternative matters: "Australian Securities and Investments
    # Commission" and "National Health and Medical Research Council" both contain a
    # lowercase "and", so a capitalised-words-only repetition stops dead at it and
    # neither of the two worst false matches gets classified.
    r"^\s*(?:(?:[A-Z][\w&'’.\-]*|and|of|for|the|on|in)\s+){1,8}"
    r"(?:Commission|Council|Authority|Agency|Bank|"
    r"Bureau|Department|Ministry|Organi[sz]ation|Organisation|Exchange|Board|"
    r"Institute|Association|Office|Committee|Fund|Group|Service|Trust|Society|"
    r"Foundation|Centre|Center|Corporation|Administration|Treasury|Reserve)\b")


def looks_corporate(entry):
    """An organisational author with no personal-name pattern before the year.

    Regulator reports, standards and statements are grey literature: Crossref
    indexes almost none of them, so a 'match' is far more likely to be a different
    document that merely shares the organisation's name."""
    head = re.split(r"\(\s*(?:1[6-9]|20)\d{2}", entry)[0]
    if re.search(r"[A-Z][a-z]+,\s*[A-Z]\.", head):     # "Smith, J." -> personal
        return False
    return bool(CORPORATE.match(head.strip()))


def assess(entry, timeout, min_score):
    if looks_corporate(entry):
        return {"entry": entry, "status": "GREY-LIT",
                "detail": "organisational author - Crossref indexes almost no regulator "
                          "reports or standards. Verify the URL and the report number "
                          "against the issuing body instead."}
    items = crossref_query(entry, 5, timeout)
    if isinstance(items, dict):
        return {"entry": entry, "status": "QUERY-FAILED", "detail": items["__error__"]}
    if not items:
        return {"entry": entry, "status": "NO-MATCH",
                "detail": "Crossref returned nothing for this entry"}

    best, best_s, best_t = None, 0.0, ""
    for it in items:
        s, t = score(it, entry)
        if s > best_s:
            best, best_s, best_t = it, s, t
    if best is None:
        return {"entry": entry, "status": "NO-MATCH", "detail": "no scoreable candidate"}

    pr, on, iss = years_of(best)
    entry_year = ref_key(entry)[1]
    ey = re.sub(r"[^0-9]", "", entry_year)
    rec = {
        "entry": entry, "doi": best.get("DOI", ""), "title": best_t,
        "score": round(best_s, 2),
        "container": (best.get("container-title") or [""])[0],
        "year_print": pr, "year_online": on, "year_issued": iss,
        "entry_year": ey, "volume": best.get("volume", ""), "page": best.get("page", ""),
    }
    if best_s < min_score or not first_author_ok(best, entry):
        rec["status"] = "WEAK"
        rec["detail"] = (f"title overlap {best_s:.0%}"
                         + ("" if first_author_ok(best, entry) else ", first author not in entry"))
        return rec

    candidates = {y for y in (pr, on, iss) if y}
    if ey and candidates and ey not in candidates:
        rec["status"] = "YEAR-DIFFERS"
        rec["detail"] = f"entry says {ey}; record says " + "/".join(sorted(candidates))
    elif pr and on and pr != on:
        rec["status"] = "YEAR-SPLIT"
        rec["detail"] = (f"online {on}, issue {pr} - entry uses {ey or '?'}. "
                         f"Cite the ISSUE year unless the style says otherwise.")
    else:
        rec["status"] = "FOUND"
        rec["detail"] = f"title overlap {best_s:.0%}"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--timeout", type=float, default=25.0)
    ap.add_argument("--workers", type=int, default=2,
                    help="keep this low; Crossref is a free public service")
    ap.add_argument("--min-score", type=float, default=0.6)
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--all", action="store_true",
                    help="also re-check entries that already carry a DOI")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        die(f"error: no such file: {args.file}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    _body, refs = split_sections(load(args.file))
    entries = [norm(e) for e in ref_entries(refs)]
    if not entries:
        print("COULD NOT CHECK - no reference entries were parsed. Not a pass.")
        return 2

    todo = [e for e in entries if args.all or not DOI_IN.search(e)]
    skipped = len(entries) - len(todo)
    print(f"DOI BACKFILL  -  {len(todo)} of {len(entries)} entries have no DOI")
    if skipped:
        print(f"  ({skipped} already carry one; --all to re-check them too)")
    print()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(assess, e, args.timeout, args.min_score): e for e in todo}
        for f in concurrent.futures.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:  # noqa: BLE001
                results.append({"entry": futs[f], "status": "QUERY-FAILED",
                                "detail": type(e).__name__})

    order = {"YEAR-DIFFERS": 0, "YEAR-SPLIT": 1, "NO-MATCH": 2, "WEAK": 3,
             "QUERY-FAILED": 4, "GREY-LIT": 5, "FOUND": 6}
    results.sort(key=lambda r: (order.get(r["status"], 9), r["entry"][:40]))

    for r in results:
        head = r["entry"][:74]
        print(f"  [{r['status']:^12}] {head}")
        if r.get("doi"):
            print(f"                 doi: {r['doi']}")
            if r.get("title"):
                print(f"                 -> {r['title'][:66]}")
        if r.get("detail"):
            print(f"                 {r['detail']}")
        print()

    by = {}
    for r in results:
        by[r["status"]] = by.get(r["status"], 0) + 1
    print("  SUMMARY")
    for k in ("FOUND", "YEAR-SPLIT", "YEAR-DIFFERS", "WEAK", "GREY-LIT", "NO-MATCH",
              "QUERY-FAILED"):
        if k in by:
            print(f"    {k:<13} {by[k]:>3}")

    actionable = by.get("YEAR-DIFFERS", 0) + by.get("YEAR-SPLIT", 0)
    unresolved = by.get("WEAK", 0) + by.get("NO-MATCH", 0) + by.get("QUERY-FAILED", 0)
    grey = by.get("GREY-LIT", 0)
    print(f"\n  {by.get('FOUND', 0)} DOIs can be added as-is.")
    if actionable:
        print(f"  {actionable} have a YEAR question - read these before changing anything.")
    if unresolved:
        print(f"  {unresolved} could not be matched confidently. A wrong DOI is worse than")
        print("  no DOI, so these are left for a human. Do not paste a WEAK match in.")
    print("\n  Nothing here is applied automatically. Check each one against the source.")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n  wrote {args.json_out}")

    # Nothing checked is not a pass. A list that is entirely grey literature
    # yields zero verified entries, and exit 0 would report that as clean.
    if actionable:
        return 1
    if unresolved or (grey and not by.get("FOUND", 0)):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
