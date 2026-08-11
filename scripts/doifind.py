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

def ensure_parent(path):
    """Create the directory an output file is about to be written into.

    The skill's own first prescribed command writes `.markpilot/inputs.json` into a
    directory nothing had created, which raised an uncaught FileNotFoundError while
    the process still exited 0 - a caller gating on the exit code saw success and got
    no file. Every script that accepts an output path creates its parent."""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    return path


UA = "markpilot/1.0 (+https://github.com/nfras4/markpilot)"
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
    """Title overlap, with a floor on how few tokens may carry the decision.

    The denominator is record-title tokens, so a one- or two-word title ("Trust",
    "Consumer Research") scores 1.0 against almost any entry - and because the
    entry side includes the journal name and publisher, a record whose TITLE
    matches the cited work's CONTAINER also scores 1.0. Short titles are capped so
    they cannot clear the threshold on their own."""
    title = (item.get("title") or [""])[0]
    tt, et = toks(title), toks(entry)
    if not tt:
        return 0.0, title
    raw = len(tt & et) / len(tt)
    if len(tt) < 3:
        raw = min(raw, 0.5)
    return raw, title


def corroborate(item, entry):
    """Which independent signals agree with the entry, beyond the title.

    Crossref already returns volume, page, container and type in the same call.
    Requiring TWO agreeing signals rather than one is what stops a fabricated
    entry taking a real DOI on title overlap alone."""
    got, e = [], entry.lower()
    if author_matches(item, entry):
        got.append("author")
    pr, on, iss = years_of(item)
    ey = re.sub(r"[^0-9]", "", ref_key(entry)[1])
    if ey and ey in {pr, on, iss}:
        got.append("year")
    vol = str(item.get("volume") or "")
    if vol and re.search(r"(?<!\d)" + re.escape(vol) + r"(?!\d)", e):
        got.append("volume")
    page = str(item.get("page") or "")
    first_page = page.split("-")[0].strip() if page else ""
    if first_page and re.search(r"(?<!\d)" + re.escape(first_page) + r"(?!\d)", e):
        got.append("page")
    cont = (item.get("container-title") or [""])[0]
    ct = toks(cont)
    if ct and len(ct & toks(entry)) / len(ct) >= 0.6:
        got.append("container")
    return got


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


JOINERS = {"and", "of", "for", "the", "on", "in", "de", "la"}


def looks_corporate(entry):
    """An organisational author with no personal-name pattern before the year.

    Regulator reports, standards and statements are grey literature: Crossref
    indexes almost none of them, so a 'match' is far more likely to be a different
    document that merely shares the organisation's name.

    The keyword list alone was too narrow - it missed acronym authors (OECD, WHO,
    CSIRO), bodies whose name does not end in a listed noun (United Nations,
    Standards Australia), consultancies (Deloitte), and ANY numbered entry, because
    a leading "[12]" defeated the anchor."""
    head = re.split(r"\(\s*(?:1[6-9]|20)\d{2}", entry)[0]
    head = re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", head).strip()   # [12] / 12.
    # Personal-name forms across styles. Requiring an INITIAL ("Smith, J.") missed
    # every style that spells the given name out - Chicago's "Smith, John." and
    # MLA's "Smith, John Robert." - so "Smith" then fullmatched the acronym branch
    # below and every Chicago/MLA journal article was declared grey literature and
    # never looked up.
    if re.search(r"[^\W\d_][\w'’\-]+,\s*(?:[A-Z]\.|[A-Z][a-z]+)", head, re.UNICODE):
        return False
    if re.search(r"^[A-Z]\.\s*[A-Z]?\.?\s*[^\W\d_][\w'’\-]+", head, re.UNICODE):
        return False                                   # IEEE "J. Smith"
    if CORPORATE.match(head):
        return True
    name = re.split(r"[.,]", head)[0].strip()
    if re.fullmatch(r"[A-Z][A-Za-z]*|[A-Z]{2,8}", name) and len(name) >= 3:
        return True                                    # OECD. / WHO. / Deloitte.
    # Two or more substantive capitalised words and no personal-name pattern.
    caps = [w for w in re.findall(r"[A-Z][\w&'’\-]{2,}", name)
            if w.lower() not in JOINERS]
    return len(caps) >= 2


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

    # Rank by (corroborating signals, title overlap) - not by title alone. Checking
    # only the top-scoring candidate discarded a correct record at rank 2 in favour
    # of a wrong one at rank 1.
    ranked = []
    for it in items:
        sc, t = score(it, entry)
        ranked.append((len(corroborate(it, entry)), sc, it, t))
    ranked.sort(key=lambda r: (r[0], r[1]), reverse=True)
    nsig, best_s, best, best_t = ranked[0]
    if best is None:
        return {"entry": entry, "status": "NO-MATCH", "detail": "no scoreable candidate"}
    signals = corroborate(best, entry)

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
    rec["signals"] = signals
    # The AUTHOR is not just another signal - it is the one that says whose work
    # this is. Year, volume and page are the fields a fabricated entry copies from
    # the real paper it is imitating, so they can all agree while the work belongs
    # to someone else entirely. Where the record names authors, a match is required
    # and one further signal must agree. Where it names none, three non-author
    # signals are needed instead.
    has_authors = bool(best.get("author"))
    if has_authors:
        ok = ("author" in signals) and len(signals) >= 2
        need = "an author match plus one more signal"
    else:
        ok = len(signals) >= 3
        need = "three signals (the record names no authors)"
    if best_s < min_score or not ok:
        rec["status"] = "WEAK"
        rec["detail"] = (f"title overlap {best_s:.0%}; agreeing: "
                         + (", ".join(signals) if signals else "none")
                         + f" - needs {need}")
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
        rec["detail"] = (f"title overlap {best_s:.0%}; corroborated by "
                         + ", ".join(signals))
    # If the entry already carries a DOI, the only question worth asking is
    # whether it agrees with the one Crossref returns.
    have = DOI_IN.search(entry)
    if have and rec.get("doi"):
        if have.group(0).rstrip("/.").lower() != rec["doi"].lower():
            rec["status"] = "DOI-CONFLICT"
            rec["detail"] = (f"the entry cites {have.group(0)} but this record is "
                             f"{rec['doi']} - one of them is wrong")
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

    without = [e for e in entries if not DOI_IN.search(e)]
    todo = entries if args.all else without
    print(f"DOI BACKFILL  -  {len(without)} of {len(entries)} entries have no DOI")
    if args.all and len(todo) > len(without):
        print(f"  (--all: also re-checking the {len(todo) - len(without)} that do)")
    elif len(without) < len(entries):
        print(f"  ({len(entries) - len(without)} already carry one; --all to re-check them)")
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

    order = {"DOI-CONFLICT": -1, "YEAR-DIFFERS": 0, "YEAR-SPLIT": 1, "NO-MATCH": 2, "WEAK": 3,
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
    for k in ("FOUND", "YEAR-SPLIT", "YEAR-DIFFERS", "DOI-CONFLICT", "WEAK",
              "GREY-LIT", "NO-MATCH", "QUERY-FAILED"):
        if k in by:
            print(f"    {k:<13} {by[k]:>3}")

    actionable = (by.get("YEAR-DIFFERS", 0) + by.get("YEAR-SPLIT", 0)
                  + by.get("DOI-CONFLICT", 0))
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
        with open(ensure_parent(args.json_out), "w", encoding="utf-8") as f:
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
