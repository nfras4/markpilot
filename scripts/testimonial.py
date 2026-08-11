#!/usr/bin/env python3
"""testimonial.py - ask once, store locally, never send.

    python testimonial.py --check                 should we ask this user?
    python testimonial.py --save --rating 5 --consent named --name "..." ...
    python testimonial.py --decline                they said no; never ask again
    python testimonial.py --show                   print what has been stored
    python testimonial.py --doors                  reprint every way to send it
    python testimonial.py --wall                   publishable entries, as JSON
    python testimonial.py --wall --from-github     ... collected from the repo
    python testimonial.py --preview --name ...     show the exact issue text, post nothing
    python testimonial.py --file --name ...        POST it (only after an explicit yes)
    python testimonial.py --reset                  clear the state (testing)

Design constraints, in priority order
-------------------------------------
1. **Ask at most once, ever.** State lives in ~/.markpilot/state.json, outside the
   skill directory, so reinstalling or re-cloning the skill does not reset it and
   the file never lands in git.
2. **Never transmit anything.** This script writes local files and prints where
   they are. It opens no sockets.

   What it does do is hand back a link with the testimonial already filled in.
   Pre-filled is NOT posted: the link opens a draft in the person's own browser
   and nothing leaves their machine until they press Submit. That keeps the
   decision entirely theirs while removing the retyping that otherwise means
   almost nobody bothers.

   The primary door is a plain web form, because it needs no account of any
   kind. A GitHub issue is offered under --doors for people who would rather
   file it there, and --file will post one directly - but ONLY as a separate,
   explicitly confirmed step: the caller must show the person the exact text
   first (--preview) and get a yes.

   A skill that quietly uploaded a name and comment would be doing something the
   user did not ask for, and this one is published for other people to install.
3. **Consent is two questions, not one.** "You may quote this" and "you may use
   my name" are different permissions, and the second is the one people regret.
   They are stored separately, the answer defaults to the most private option,
   and a record that was not consented to cannot reach --wall at all: the name
   is dropped from the publishable record by construction, not by remembering to.
4. **Only after a run that worked.** Asking for a recommendation after a failed or
   blocked run is worse than not asking.
5. **Declining is permanent and costs one keystroke.** No second prompt, no
   "maybe later" that comes back.

Exit codes for --check:
    0  ask (never asked before)
    1  do not ask (already asked, declined, or previously submitted)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

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


STATE_DIR = (os.environ.get("MARKPILOT_HOME")
             or os.path.join(os.path.expanduser("~"), ".markpilot"))
STATE = os.path.join(STATE_DIR, "state.json")
BOOK = os.path.join(STATE_DIR, "testimonials.md")
LEDGER = os.path.join(STATE_DIR, "testimonials.jsonl")

REPO = "nfras4/markpilot"
# The one door that needs no account of any kind. Forking this skill? Point this
# at your own form, or set it to "" to drop the web door entirely.
WEB_FORM = "https://nickwfraser.dev/testimonial"
# Off by default and deliberately so: an address written into a public repository
# is an address that gets scraped. Set it if you want a mailto door.
CONTACT_EMAIL = ""

# Browsers reliably handle ~2000 characters of URL. GitHub itself accepts far
# more, but a link that silently fails to open in someone's browser is worse than
# a truncated one that does.
URL_BUDGET = 1900

# The exact words the person is answering. Stored verbatim alongside their answer,
# so the record says what they agreed to rather than what we remember asking. Change
# the wording and old records still carry the wording that was actually shown.
CONSENT_PROMPT = ("Can these words be quoted publicly - on the markpilot README, "
                  "or on nickwfraser.dev?")
CONSENT_TEXT = {
    "none": "No - keep it on my machine. Do not quote me anywhere.",
    "anon": "Yes, quote the words - but do not use my name.",
    "named": "Yes, quote the words, and use my name as given.",
}
CONSENT_CHOICES = tuple(CONSENT_TEXT)
PUBLISHABLE = ("anon", "named")


def stars(rating):
    """'★★★★☆' for 4, '' for anything that is not 1-5."""
    try:
        n = int(rating)
    except (ValueError, TypeError):
        return ""
    return "★" * n + "☆" * (5 - n) if 1 <= n <= 5 else ""


def who_line(name, role, consent):
    """How the person is identified, given what they actually agreed to.

    On anything short of 'named' this returns Anonymous no matter what was typed
    into --name. The name is not withheld at the point of display, it is dropped
    at the point of record - see public_record()."""
    if consent != "named":
        return "Anonymous"
    who = (name or "").strip() or "Anonymous"
    if (role or "").strip():
        who += f" — {role.strip()}"
    return who


def record(name, role, rating, comment, stamp, consent):
    """The full local record. Keeps the name even when consent withholds it, because
    this file is the person's own copy on their own machine."""
    return {
        "v": 1,
        "date": (stamp or "").strip(),
        "rating": (str(rating) or "").strip(),
        "name": (name or "").strip(),
        "role": (role or "").strip(),
        "comment": (comment or "").strip(),
        "consent": consent,
        "consent_prompt": CONSENT_PROMPT,
        "consent_answer": CONSENT_TEXT[consent],
    }


def public_record(rec):
    """The subset that may be published, or None if nothing may be.

    This is the guarantee behind --wall. The name is not filtered out downstream
    by a caller who has to remember to; it is never copied into the publishable
    object in the first place unless consent is exactly 'named'."""
    if rec.get("consent") not in PUBLISHABLE:
        return None
    out = {
        "rating": rec.get("rating", ""),
        "comment": rec.get("comment", ""),
        "date": rec.get("date", ""),
        "consent": rec["consent"],
        "name": "Anonymous",
    }
    if rec["consent"] == "named":
        out["name"] = (rec.get("name") or "").strip() or "Anonymous"
        if (rec.get("role") or "").strip():
            out["role"] = rec["role"].strip()
    return out


def consent_block(rec):
    """A fenced JSON block for the issue body.

    Two jobs. It lets --wall --from-github read a submission back without parsing
    prose, and - the reason it is visible rather than a hidden comment - it shows
    the person the exact machine-readable claim about their consent that they are
    about to publish under their own account."""
    pub = public_record(rec) or {"consent": rec.get("consent", "none")}
    return "```markpilot-consent\n" + json.dumps(pub, ensure_ascii=False) + "\n```"


def _fit(build, comment, budget):
    """The longest prefix of `comment` for which build(...) still fits in `budget`.

    Binary search rather than subtract-the-overflow, because a comment can appear
    more than once in a body (once as the quote, once inside the consent block)
    and subtracting the overflow then deletes roughly twice what it needs to - a
    600-word testimonial came back empty rather than trimmed."""
    url = build(comment)
    if len(url) <= budget:
        return url
    lo, hi, best = 0, len(comment), build("")
    while lo <= hi:
        mid = (lo + hi) // 2
        c = comment[:mid].rstrip()
        c = (c + "…") if c else ""
        u = build(c)
        if len(u) <= budget:
            best, lo = u, mid + 1
        else:
            hi = mid - 1
    return best


def form_url(name, role, rating, comment, stamp, consent="named"):
    """A pre-filled link to the web form. Needs no account, no login, no GitHub.

    Pre-filled is NOT submitted. The form opens with the answers already in it,
    in the person's own browser, and nothing is sent until they press Submit -
    at which point they can still change any of it, including the consent."""
    if not WEB_FORM:
        return ""

    def build(c):
        q = {"rating": str(rating or "").strip(), "consent": consent}
        if c.strip():
            q["comment"] = c.strip()
        if stamp:
            q["date"] = stamp
        # Only ever carry the name when it is the name they agreed to publish.
        if consent == "named":
            if (name or "").strip():
                q["name"] = name.strip()
            if (role or "").strip():
                q["role"] = role.strip()
        return WEB_FORM + "?" + urllib.parse.urlencode(
            {k: v for k, v in q.items() if v})

    return _fit(build, comment or "", URL_BUDGET)


def mail_url(name, role, rating, comment, stamp, consent="named"):
    """A pre-filled mail draft. Empty unless CONTACT_EMAIL is configured."""
    if not CONTACT_EMAIL:
        return ""

    def build(c):
        body = plain_block(name, role, rating, c, stamp, consent)
        return "mailto:" + CONTACT_EMAIL + "?" + urllib.parse.urlencode(
            {"subject": "markpilot testimonial", "body": body})

    return _fit(build, comment or "", URL_BUDGET)


def plain_block(name, role, rating, comment, stamp, consent="named"):
    """The testimonial as text, to be copied and sent however the person likes.

    The door that always works: no account, no browser, no network, no trust in
    any of the above."""
    lines = [who_line(name, role, consent)]
    s = stars(rating)
    if s or stamp:
        lines.append("  ".join(x for x in (s, stamp) if x))
    lines.append("")
    lines.append(f'"{comment.strip()}"' if (comment or "").strip()
                 else "(rating only; no comment left)")
    lines.append("")
    lines.append(f"Consent: {CONSENT_TEXT[consent]}")
    return "\n".join(lines)


def share_url(name, role, rating, comment, stamp, consent="named"):
    """A GitHub 'new issue' link with the testimonial already filled in.

    Pre-filled is NOT posted. The link opens a draft issue in the person's own
    browser, under their own account, and nothing reaches the repository until
    they press Submit."""
    who = who_line(name, role, consent)
    rec = record(name, role, rating, comment, stamp, consent)

    def build(c):
        body = who
        s = stars(rating)
        if s:
            body += f"\n\n{s}"
        if stamp:
            body += f"\n\n_{stamp}_"
        # A rating with no comment is a rating with no comment. Emitting a
        # blockquote containing a placeholder puts words in someone's mouth, in
        # the one file whose entire purpose is quoting people accurately.
        body += f"\n\n> {c.strip()}\n" if c.strip() else "\n\n_Rating only; no comment left._\n"
        r = dict(rec, comment=c.strip())
        body += "\n" + consent_block(r) + "\n"
        return ("https://github.com/" + REPO + "/issues/new?"
                + urllib.parse.urlencode({
                    "title": f"Testimonial — {who}"[:80],
                    "labels": "testimonial",
                    "body": body,
                }))

    return _fit(build, comment or "", URL_BUDGET)


def issue_parts(name, role, rating, comment, stamp, consent="named"):
    """(title, body) exactly as they would be posted. Used by --preview so the
    person sees the real text before deciding, not a summary of it."""
    who = who_line(name, role, consent)
    rec = record(name, role, rating, comment, stamp, consent)
    body = who
    s = stars(rating)
    if s:
        body += f"\n\n{s}"
    if stamp:
        body += f"\n\n_{stamp}_"
    body += (f"\n\n> {comment.strip()}\n" if (comment or "").strip()
             else "\n\n_Rating only; no comment left._\n")
    body += "\n" + consent_block(rec) + "\n"
    body += f"\n<sub>{CONSENT_TEXT[consent]}</sub>\n"
    return f"Testimonial — {who}"[:80], body


def doors(rec, every=False, indent="  "):
    """How to send it. Returns a list of lines; nothing here sends anything.

    One door by default. The web form is the only one that needs no account of
    any kind, so it is the only one worth putting in front of somebody who is
    already doing you a favour - three links and a copy block is a menu, and a
    menu is a decision they did not ask to make. `every` opens the rest for
    anyone who would rather use them, and for when posting has just failed."""
    name, role = rec.get("name", ""), rec.get("role", "")
    rating, comment = rec.get("rating", ""), rec.get("comment", "")
    stamp, consent = rec.get("date", ""), rec.get("consent", "none")
    out = []
    if consent not in PUBLISHABLE:
        out.append("You asked for this to stay on your machine, so there is nothing")
        out.append("to send and no link to open. That is a complete answer.")
        return out

    form = form_url(name, role, rating, comment, stamp, consent)
    if form:
        out += ["The form opens with your answers already in it. Nothing is sent",
                "until you press Submit, and you can change anything there first -",
                "including the consent. No account, no sign-in.", "",
                indent + form, ""]
    if not every:
        if form:
            out.append("(`testimonial.py --doors` for other ways to send it.)")
            return out
        every = True            # no web form configured: show what there is

    mail = mail_url(name, role, rating, comment, stamp, consent)
    if mail:
        out += ["Or open a mail draft instead:", "", indent + mail, ""]
    out += ["Or file it on GitHub, if you would rather it lived there:", "",
            indent + share_url(name, role, rating, comment, stamp, consent), ""]
    out += ["Or copy this and send it however suits you:", ""]
    out += [indent + ln for ln in plain_block(
        name, role, rating, comment, stamp, consent).split("\n")]
    return out


def gh_ready():
    """(ok, message). Never posts as the wrong person: if gh is not authenticated
    we do not post at all, rather than posting under whatever account happens to
    be configured elsewhere."""
    exe = shutil.which("gh")
    if not exe:
        return False, "the GitHub CLI (gh) is not installed"
    try:
        r = subprocess.run([exe, "auth", "status"], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"gh could not be run ({type(e).__name__})"
    if r.returncode != 0:
        return False, "gh is installed but not logged in (`gh auth login`)"
    return True, exe


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def read_ledger():
    """Every stored record. A malformed line is skipped rather than fatal - one bad
    line must not make the rest of someone's file unreadable."""
    out = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def wall_from_github():
    """(records, error). Reads issues labelled `testimonial` and pulls the fenced
    consent block out of each. An issue without one is skipped: somebody typed a
    testimonial by hand and never answered the consent question, and a missing
    answer is not a yes."""
    ok, info = gh_ready()
    if not ok:
        return [], info
    try:
        r = subprocess.run(
            [info, "issue", "list", "--repo", REPO, "--label", "testimonial",
             "--state", "all", "--limit", "200", "--json", "number,body,createdAt"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return [], f"gh could not be run ({type(e).__name__})"
    if r.returncode != 0:
        return [], (r.stderr.strip().splitlines() or ["gh failed"])[-1]
    try:
        issues = json.loads(r.stdout or "[]")
    except ValueError:
        return [], "gh returned output that is not JSON"

    out = []
    for iss in issues:
        m = re.search(r"```markpilot-consent\s*\n(.*?)\n```",
                      iss.get("body") or "", re.S)
        if not m:
            continue
        try:
            pub = json.loads(m.group(1))
        except ValueError:
            continue
        if pub.get("consent") not in PUBLISHABLE:
            continue
        pub.setdefault("date", (iss.get("createdAt") or "")[:10])
        pub["source"] = f"github#{iss.get('number')}"
        out.append(pub)
    return out, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--decline", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--doors", action="store_true",
                    help="reprint every way to send the stored testimonial")
    ap.add_argument("--share", action="store_true",
                    help="reprint the pre-filled links for stored entries")
    ap.add_argument("--wall", action="store_true",
                    help="publishable entries as JSON; consented ones only")
    ap.add_argument("--from-github", action="store_true",
                    help="with --wall: collect from issues labelled `testimonial`")
    ap.add_argument("--out", default="", help="with --wall: write here instead of stdout")
    ap.add_argument("--preview", action="store_true",
                    help="print the exact issue text; posts nothing")
    ap.add_argument("--file", action="store_true",
                    help="POST the issue via gh. Only after an explicit yes")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument("--role", default="", help="e.g. 'UQ, 4th-year business'")
    ap.add_argument("--rating", default="", help="1-5")
    ap.add_argument("--comment", default="")
    ap.add_argument("--consent", default="none", choices=CONSENT_CHOICES,
                    help="none (default) | anon | named")
    ap.add_argument("--stamp", default="", help="date, supplied by the caller")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    st = load()

    if args.reset:
        st.pop("asked", None)
        st.pop("outcome", None)
        save(st)
        print("testimonial state cleared")
        return 0

    if args.wall:
        if args.from_github:
            recs, err = wall_from_github()
            if err:
                print(f"could not collect from GitHub — {err}", file=sys.stderr)
                return 2
        else:
            recs = [p for p in (public_record(r) for r in read_ledger()) if p]
        text = json.dumps(recs, indent=2, ensure_ascii=False)
        if args.out:
            with open(ensure_parent(args.out), "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print(f"{len(recs)} publishable entr{'y' if len(recs) == 1 else 'ies'} "
                  f"-> {args.out}")
        else:
            print(text)
        return 0

    if args.show:
        print(f"state:  {STATE}")
        print(f"asked:  {st.get('asked', False)}   outcome: {st.get('outcome', '-')}")
        if os.path.exists(BOOK):
            print(f"\n--- {BOOK} ---")
            print(open(BOOK, encoding="utf-8").read())
        else:
            print("no testimonials stored")
        return 0

    if args.doors or args.share:
        recs = read_ledger()
        if not recs:
            print("Nothing stored yet.")
            return 2
        for ln in doors(recs[-1], every=True):
            print(ln)
        return 0

    if args.check:
        return 1 if st.get("asked") else 0

    if args.decline:
        st.update({"asked": True, "outcome": "declined"})
        save(st)
        print("Noted - you will not be asked again.")
        return 0

    if args.save:
        if not args.comment.strip() and not args.rating.strip():
            print("error: --save needs a --rating or a --comment (or both)",
                  file=sys.stderr)
            return 2
        rec = record(args.name, args.role, args.rating, args.comment,
                     args.stamp, args.consent)
        os.makedirs(STATE_DIR, exist_ok=True)

        block = ["", "---", ""]
        if args.stamp:
            block.append(f"**{args.stamp}**")
        # The book keeps the name whatever the consent, because the book is theirs.
        who = (args.name.strip() or "Anonymous")
        if args.role.strip():
            who += f" — {args.role.strip()}"
        s = stars(args.rating)
        block.append(f"**{who}**" + (f"  {s}" if s else ""))
        if args.comment.strip():
            block += ["", "> " + args.comment.strip().replace("\n", "\n> "), ""]
        else:
            block += ["", "_Rating only; no comment left._", ""]
        block += [f"_Asked: {CONSENT_PROMPT}_",
                  f"_Answered: {CONSENT_TEXT[args.consent]}_", ""]
        with open(BOOK, "a", encoding="utf-8") as f:
            f.write("\n".join(block))
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print("Saved to your own machine. Nothing has been sent anywhere.\n")
        print(f"  {BOOK}\n")
        for ln in doors(rec):
            print(ln)
        print("\nSkipping is completely fine. The files above are yours to edit or")
        print("delete, and you will not be asked again.")
        st.update({"asked": True, "outcome": "saved"})
        save(st)
        return 0

    if args.preview or args.file:
        if args.consent not in PUBLISHABLE:
            print("Not previewed — this was kept private (--consent none), so there",
                  file=sys.stderr)
            print("is nothing to post. Re-run with the consent they actually gave.",
                  file=sys.stderr)
            return 2
        title, body = issue_parts(args.name, args.role, args.rating,
                                  args.comment, args.stamp, args.consent)
        if args.preview:
            print("This is exactly what would be posted, word for word:\n")
            print(f"  repo:  github.com/{REPO}")
            print(f"  title: {title}\n")
            for ln in body.strip().split("\n"):
                print(f"  | {ln}")
            print("\n  It would be a PUBLIC issue on a public repository, opened under")
            print("  your own GitHub account and visible to anyone. You can edit or")
            print("  delete it afterwards. Nothing is posted by this command.")
            return 0

        ok, info = gh_ready()
        if not ok:
            print(f"Not posted — {info}.\n")
            print("No GitHub account is needed for any of these:\n")
            for ln in doors(record(args.name, args.role, args.rating,
                                   args.comment, args.stamp, args.consent),
                            every=True):
                print(ln)
            return 2
        try:
            r = subprocess.run(
                [info, "issue", "create", "--repo", REPO, "--title", title,
                 "--body", body, "--label", "testimonial"],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            r = None
            err = f"{type(e).__name__}"
        if r is not None and r.returncode == 0:
            url = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
            print("Posted. Thank you.\n")
            if url:
                print(f"  {url}\n")
            print("It is a public issue under your own account — edit or delete it")
            print("there at any time.")
            st.update({"asked": True, "outcome": "posted"})
            save(st)
            return 0
        detail = (r.stderr.strip().splitlines()[-1] if r is not None and r.stderr.strip()
                  else err if r is None else "unknown error")
        print(f"Not posted — gh reported: {detail}\n")
        print("Nothing was sent. Any of these work instead:\n")
        for ln in doors(record(args.name, args.role, args.rating,
                               args.comment, args.stamp, args.consent), every=True):
            print(ln)
        return 2

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
