#!/usr/bin/env python3
"""linkcheck.py - resolve every URL and DOI in a document and report what is real.

Stdlib only. Network required.

    python linkcheck.py FILE
    python linkcheck.py FILE --json out.json
    python linkcheck.py FILE --timeout 20 --workers 6

Exit codes:
    0  every link resolved LIVE and every DOI matched its entry
    1  at least one DEAD / MISMATCH  -> must be fixed before submission
    2  nothing dead, but some need a human -> BLOCKED / TIMEOUT / SOFT-404 / SSL

The distinction that matters
---------------------------
A 403 is NOT a dead link. Springer, Elsevier, ScienceDirect, JSTOR, Taylor &
Francis, Wiley and most publisher platforms return 403 or 429 to anything that is
not a real browser. Reporting those as broken sends the user off to "fix" working
references; reporting them as verified is worse, because it certifies something
nobody checked. They get their own category and they block the gate until a human
looks. Never collapse BLOCKED into either LIVE or DEAD.

DOIs are checked against Crossref rather than by fetching doi.org, because
Crossref is bot-friendly, authoritative, and returns the metadata - which lets us
answer the question that actually matters: not "does this DOI resolve" but "does
it resolve to the source the reference claims". A DOI that resolves to a
different paper is a worse finding than one that 404s, because it survives every
casual check.
"""

import argparse
import concurrent.futures
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doctext import load, norm  # noqa: E402
from citecheck import split_sections, ref_entries  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

URL_RE = re.compile(r"""(?xi)\bhttps?://[^\s<>"'\]\)]+""")
# 10.xxxx/suffix - the suffix runs to whitespace or a closing bracket
DOI_RE = re.compile(r"""(?xi)\b10\.\d{4,9}/[^\s<>"'\]\),;]+""")
TRAILING = ".,;:'\"’”)]}>»"

SOFT404 = re.compile(
    r"(?i)(page not found|404 error|404 not found|cannot be found|"
    r"no longer available|page you (?:requested|are looking for)|"
    r"content is unavailable|doesn'?t exist|does not exist|"
    r"article withdrawn|has been removed|error 404)"
)

LIVE, DEAD, BLOCKED, TIMEOUT, SSLERR, SOFT, MISMATCH, NOTFOUND, REDIR, NODNS = (
    "LIVE", "DEAD", "BLOCKED", "TIMEOUT", "SSL", "SOFT-404", "MISMATCH", "NOT-FOUND",
    "REDIRECTED", "NO-DNS")

# Statuses that mean "a human must look at this". Nothing here counts as verified.
#
# NO-DNS is here rather than in FATAL on purpose: a name that will not resolve is
# evidence about the NETWORK, not about the URL. Run this offline, behind a captive
# portal, or behind a proxy and every reference in the document reports as dead and
# "MUST be fixed" - which is a confident, wrong, and very expensive answer.
NEEDS_HUMAN = {BLOCKED, TIMEOUT, SSLERR, SOFT, REDIR, NODNS}
FATAL = {DEAD, MISMATCH, NOTFOUND}


def clean(u):
    while u and u[-1] in TRAILING:
        # keep a balanced closing paren, e.g. .../wiki/Foo_(bar)
        if u[-1] == ")" and u.count("(") > u.count(")"):
            break
        u = u[:-1]
    return u


def encode_url(u):
    """Percent-encode non-ASCII path/query bytes. Without this, urllib raises
    UnicodeEncodeError before any request is made, and the URL is reported as a
    timeout it never had."""
    try:
        u.encode("ascii")
        return u
    except UnicodeEncodeError:
        parts = urllib.parse.urlsplit(u)
        return urllib.parse.urlunsplit((
            parts.scheme,
            parts.netloc.encode("idna").decode("ascii") if parts.netloc else "",
            urllib.parse.quote(parts.path, safe="/%"),
            urllib.parse.quote(parts.query, safe="=&%"),
            urllib.parse.quote(parts.fragment, safe="%"),
        ))


def fetch(url, timeout, method="GET"):
    """Return (status:int|None, final_url, body_snippet, err:str|None)."""
    try:
        url = encode_url(url)
    except Exception as e:  # noqa: BLE001
        return None, url, "", f"badurl:{e}"
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip, identity",
        "Connection": "close",
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read(60000) if method == "GET" else b""
            if r.headers.get("Content-Encoding") == "gzip":
                # We deliberately read only the first 60KB, so the gzip member is
                # truncated. gzip.GzipFile raises EOFError on that (and EOFError is
                # NOT an OSError, so it escapes the obvious except clause and the
                # whole URL gets misreported as a timeout). zlib's decompressobj
                # returns whatever it managed to inflate, which is all we need -
                # we only look at <title> and the first few KB.
                try:
                    raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
                except (zlib.error, OSError, EOFError):
                    pass
            return r.status, r.geturl(), raw.decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(20000).decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, url, body, None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, ssl.SSLError):
            return None, url, "", f"ssl:{reason}"
        if isinstance(reason, socket.timeout):
            return None, url, "", "timeout"
        if isinstance(reason, socket.gaierror):
            return None, url, "", f"dns:{reason}"
        return None, url, "", f"urlerror:{reason}"
    except socket.timeout:
        return None, url, "", "timeout"
    except Exception as e:  # noqa: BLE001 - a checker must never die on one bad URL
        return None, url, "", f"{type(e).__name__}:{e}"


def check_url(url, timeout):
    status, final, body, err = fetch(url, timeout)
    if err:
        if err.startswith("timeout"):
            return TIMEOUT, "no response", final
        if err.startswith("ssl:"):
            return SSLERR, err[4:][:70], final
        if err.startswith("dns:"):
            return NODNS, "host did not resolve (could be the network, not the link)", final
        if err.startswith("badurl:"):
            return TIMEOUT, f"malformed URL: {err[7:][:60]}", final
        return TIMEOUT, err[:70], final

    if status in (401, 402, 403, 429, 503):
        # Bot protection or a paywall. The page may well be fine.
        return BLOCKED, f"HTTP {status} (bot-blocked or paywalled)", final
    if status in (404, 410):
        return DEAD, f"HTTP {status}", final
    if status and 500 <= status < 600:
        return TIMEOUT, f"HTTP {status} (server error, retry later)", final
    if status and 200 <= status < 400:
        head = body[:4000]
        title = re.search(r"(?is)<title[^>]*>(.*?)</title>", head)
        t = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
        # Only the <title> is tested for soft-404 wording. Scanning raw body markup
        # fires on ordinary prose and on inline JS/JSON-LD, and the finding is then
        # impossible to triage because the quoted title looks perfectly normal.
        if SOFT404.search(t):
            return SOFT, f"HTTP 200 but the title reads as an error ({t[:50]})", final
        # A deep link that redirects to the site root is the commonest form of link
        # rot: the publisher answers 200 from a landing page, so status alone says
        # LIVE while the cited page is gone.
        try:
            o, f = urllib.parse.urlsplit(url), urllib.parse.urlsplit(final)
            odepth = len([s for s in o.path.split("/") if s])
            fdepth = len([s for s in f.path.split("/") if s])
            if odepth >= 2 and fdepth == 0 and not f.query:
                return REDIR, f"deep link redirected to the site root ({final[:60]})", final
        except ValueError:
            pass
        extra = f" -> {final[:50]}" if final and final != url else ""
        return LIVE, f"HTTP {status}" + (f" - {t[:55]}" if t else "") + extra, final
    return TIMEOUT, f"HTTP {status}", final


def crossref(doi, timeout):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA + " (mailto:markpilot@local)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")).get("message")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "404"
        return None
    except Exception:
        return None


def toks(s):
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower())}


def check_doi(doi, context, timeout, msg=None):
    """context = the reference-list entry the DOI came from, for metadata matching.

    `msg` may be a pre-fetched Crossref record. The network lookup is cached per
    DOI, but the COMPARISON must run per occurrence - the same DOI attached to two
    different reference entries is exactly the case where one of them is wrong, and
    deduplicating by DOI alone silently checks only the first."""
    if msg is None:
        msg = crossref(doi, timeout)
    if msg == "404":
        return NOTFOUND, "not registered with Crossref - likely fabricated", {}
    if msg is None:
        # Crossref unreachable; fall back to resolving doi.org itself.
        st, detail, _ = check_url("https://doi.org/" + doi, timeout)
        if st == LIVE:
            return BLOCKED, "Crossref unreachable; doi.org resolved (metadata unchecked)", {}
        return TIMEOUT, "Crossref unreachable and doi.org did not resolve", {}

    title = (msg.get("title") or [""])[0]
    year = ""
    for k in ("published-print", "published-online", "issued", "created"):
        p = msg.get(k, {}).get("date-parts") or []
        if p and p[0] and p[0][0]:
            year = str(p[0][0])
            break
    authors = msg.get("author") or []
    first = (authors[0].get("family") or "") if authors else ""
    meta = {"title": title, "year": year, "first_author": first,
            "container": (msg.get("container-title") or [""])[0]}

    if not context:
        return LIVE, f"registered: {title[:60]}", meta

    ctx = norm(context).lower()
    problems = []
    if first and first.lower() not in ctx:
        problems.append(f"first author '{first}' not in the entry")
    if year and year not in ctx:
        # allow +/-1 year: online-first vs issue year is a real, common, benign case
        if not any(str(int(year) + d) in ctx for d in (-1, 1)):
            problems.append(f"year {year} not in the entry")
    tt, ct = toks(title), toks(context)
    if tt:
        overlap = len(tt & ct) / len(tt)
        if overlap < 0.34:
            problems.append(f"title does not match ({int(overlap * 100)}% word overlap; "
                            f"Crossref says '{title[:55]}')")
    if problems:
        return MISMATCH, "; ".join(problems), meta
    return LIVE, f"matches: {first} ({year}) {title[:50]}", meta


# ------------------------------------------------------------------ extraction


def context_blocks(paras):
    """Text blocks to scan, each carrying the FULL context for anything inside it.

    Reference entries are joined first. In a plain-text or Markdown draft a wrapped
    entry puts its DOI on its own line, and comparing Crossref metadata against that
    line alone finds no author, no year and no title - so a completely correct
    reference is accused of being MISMATCH, the most severe status this tool emits.
    One entry must be one block."""
    body, refs = split_sections(paras)
    blocks = [norm(p.text) for p in body if p.text.strip()]
    blocks += [norm(e) for e in ref_entries(refs)]
    return blocks


def harvest(paras):
    """[(kind, value, context_entry)].

    Deduplicated by (value, context), not by value. The same DOI or URL appearing
    under two different reference entries is checked against both, because that is
    precisely the situation where one entry has the wrong identifier attached."""
    seen, out = set(), []
    for t in context_blocks(paras):
        if not t.strip():
            continue
        for m in URL_RE.finditer(t):
            u = clean(m.group(0))
            # a doi.org URL is handled on the DOI path instead
            if re.search(r"(?i)://(dx\.)?doi\.org/", u):
                continue
            key = ("url", u, t[:150])
            if key not in seen:
                seen.add(key)
                out.append(("url", u, t))
        for m in DOI_RE.finditer(t):
            d = clean(m.group(0)).rstrip("/")
            key = ("doi", d.lower(), t[:150])
            if key not in seen:
                seen.add(key)
                out.append(("doi", d, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--urls-only", action="store_true")
    ap.add_argument("--dois-only", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        sys.exit(f"error: no such file: {args.file}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    paras = load(args.file)
    items = harvest(paras)

    # Reference COVERAGE, not just link status. A list of 30 print-only or
    # DOI-less entries yields 6 live URLs and "6/6 confirmed", which reads as a
    # pass while 24 sources were never checked by anything. The denominator that
    # matters is reference entries, not links found.
    _body, _refs = split_sections(paras)
    entries = ref_entries(_refs)
    with_id = [e for e in entries
               if URL_RE.search(e) or DOI_RE.search(e)]
    coverage = (len(with_id), len(entries))
    if args.urls_only:
        items = [i for i in items if i[0] == "url"]
    if args.dois_only:
        items = [i for i in items if i[0] == "doi"]

    print(f"LINK & DOI RESOLUTION  -  {len(items)} to check")
    if not items:
        print("  COULD NOT CHECK - the document contains no URLs or DOIs at all.")
        print("  This is NOT a pass. Either the sources are all print-only, or the")
        print("  parser never saw the reference section. Read it by hand and confirm")
        print("  which before reporting anything about the references.")
        return 2
    print()

    # One network call per distinct URL/DOI, however many entries reference it.
    uniq_urls = sorted({v for k, v, _ in items if k == "url"})
    uniq_dois = sorted({v for k, v, _ in items if k == "doi"}, key=str.lower)

    url_cache, doi_cache = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        fu = {ex.submit(check_url, u, args.timeout): u for u in uniq_urls}
        fd = {ex.submit(crossref, d, args.timeout): d for d in uniq_dois}
        for f in concurrent.futures.as_completed(list(fu) + list(fd)):
            # One worker blowing up must not discard every completed result. fetch()
            # catches Exception but check_url's own post-processing does not, and an
            # unguarded .result() here kills the run after printing only the header.
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = None
                err = f"checker crashed: {type(e).__name__}"
            if f in fu:
                url_cache[fu[f]] = res or (TIMEOUT, err, fu[f])
            else:
                doi_cache[fd[f]] = res  # None already means "Crossref unreachable"

    results = []
    for kind, val, ctx in items:
        if kind == "doi":
            st, detail, meta = check_doi(val, ctx, args.timeout, msg=doi_cache.get(val))
        else:
            st, detail, _final = url_cache[val]
            meta = {}
        r = {"kind": kind, "value": val, "status": st, "detail": detail,
             "meta": meta, "context": ctx[:200]}
        results.append(r)

    for r in results:
        mark = {LIVE: "  ok  "}.get(r["status"], f"{r['status']:^6}")
        print(f"  [{mark}] {r['kind']:<3} {r['value'][:78]}")
        if r["status"] != LIVE:
            print(f"           -> {r['detail']}")

    by = {}
    for r in results:
        by.setdefault(r["status"], []).append(r)

    print("\n  SUMMARY")
    for st in (LIVE, DEAD, NOTFOUND, MISMATCH, SOFT, REDIR, BLOCKED, TIMEOUT,
               SSLERR, NODNS):
        if st in by:
            print(f"    {st:<11} {len(by[st]):>3}")

    fatal = sum(len(by.get(s, [])) for s in FATAL)
    human = sum(len(by.get(s, [])) for s in NEEDS_HUMAN)
    verified = len(by.get(LIVE, []))

    print(f"\n  {verified}/{len(results)} of the links and DOIs found resolve to a real page.")

    have, total = coverage
    if total:
        gap = total - have
        print(f"\n  REFERENCE COVERAGE  {have}/{total} entries carried a DOI or URL to check.")
        if gap:
            print(f"    {gap} reference entr{'y' if gap == 1 else 'ies'} had NOTHING for this")
            print("    script to verify. They are NOT confirmed by this run, and the count")
            print("    above says nothing about them. Check them by hand.")
            if have * 2 < total:
                print("    Most of the list is unverifiable this way. If these are journal")
                print("    articles they almost certainly have DOIs - APA 7 and Harvard both")
                print("    want one wherever it exists, and adding them makes the list")
                print("    checkable as a side effect.")
    if fatal:
        print(f"  {fatal} MUST be fixed - dead, unregistered, or resolving to the wrong source.")
    if human:
        print(f"  {human} could not be confirmed automatically and MUST be opened by hand.")
        print("  Bot-blocked and paywalled links are NOT verified. Do not report them as passing.")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"coverage": {"entries_with_identifier": coverage[0],
                                    "reference_entries": coverage[1]},
                       "results": results}, f, indent=2)
        print(f"\n  wrote {args.json_out}")

    if fatal:
        return 1
    if human:
        return 2
    # Everything found resolved - but if most of the reference list had no
    # identifier, this run does not establish that the references are sound, and
    # exit 0 would be read as if it did.
    if coverage[1] and coverage[0] * 2 < coverage[1]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
