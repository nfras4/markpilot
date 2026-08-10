#!/usr/bin/env python3
"""testimonial.py - ask once, store locally, never send.

    python testimonial.py --check                 should we ask this user?
    python testimonial.py --save --name "..." --rating 5 --comment "..."
    python testimonial.py --decline                they said no; never ask again
    python testimonial.py --show                   print what has been stored
    python testimonial.py --share                  reprint the pre-filled share link
    python testimonial.py --reset                  clear the state (testing)

Design constraints, in priority order
-------------------------------------
1. **Ask at most once, ever.** State lives in ~/.markpilot/state.json, outside the
   skill directory, so reinstalling or re-cloning the skill does not reset it and
   the file never lands in git.
2. **Never transmit anything.** This script writes a local file and prints where
   it is. It opens no sockets.

   What it does do is hand back a GitHub "new issue" link with the testimonial
   already filled in. Pre-filled is NOT posted: the link opens a draft in the
   person's own browser, under their own account, and nothing reaches the
   repository until they press Submit. That keeps the decision entirely theirs
   while removing the retyping that otherwise means almost nobody bothers.

   A skill that quietly uploaded a name and comment would be doing something the
   user did not ask for, and this one is published for other people to install.
3. **Only after a run that worked.** Asking for a recommendation after a failed or
   blocked run is worse than not asking.
4. **Declining is permanent and costs one keystroke.** No second prompt, no
   "maybe later" that comes back.

Exit codes for --check:
    0  ask (never asked before)
    1  do not ask (already asked, declined, or previously submitted)
"""

import argparse
import json
import os
import re
import sys
import urllib.parse

STATE_DIR = os.path.join(os.path.expanduser("~"), ".markpilot")
STATE = os.path.join(STATE_DIR, "state.json")
BOOK = os.path.join(STATE_DIR, "testimonials.md")
REPO = "nfras4/markpilot"
# Browsers reliably handle ~2000 characters of URL. GitHub itself accepts far
# more, but a link that silently fails to open in someone's browser is worse than
# a truncated one that does.
URL_BUDGET = 1900


def share_url(name, role, rating, comment, stamp):
    """A GitHub 'new issue' link with the testimonial already filled in.

    Pre-filled is NOT posted. The link opens a draft issue in the person's own
    browser, under their own account, and nothing reaches the repository until
    they press Submit. That is the whole design: one click instead of retyping,
    with the decision still entirely theirs."""
    who = name.strip() or "Anonymous"
    if role.strip():
        who += f" — {role.strip()}"
    stars = ""
    try:
        n = int(rating)
        if 1 <= n <= 5:
            stars = "★" * n + "☆" * (5 - n)
    except (ValueError, TypeError):
        pass

    body = f"{who}"
    if stars:
        body += f"\n\n{stars}"
    if stamp:
        body += f"\n\n_{stamp}_"
    # A rating with no comment is a rating with no comment. Emitting a blockquote
    # containing a placeholder puts words in someone's mouth, in the one file whose
    # entire purpose is quoting people accurately.
    if comment.strip():
        body += f"\n\n> {comment.strip()}\n"
    else:
        body += "\n\n_Rating only; no comment left._\n"

    def build(b):
        return ("https://github.com/" + REPO + "/issues/new?"
                + urllib.parse.urlencode({
                    "title": f"Testimonial — {who}"[:80],
                    "labels": "testimonial",
                    "body": b,
                }))

    url = build(body)
    if len(url) > URL_BUDGET:
        keep = max(120, len(comment) - (len(url) - URL_BUDGET) - 40)
        body = body.replace(comment.strip(), comment.strip()[:keep] + "…")
        url = build(body)
    return url


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--decline", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--share", action="store_true",
                    help="reprint the pre-filled share link for stored entries")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument("--role", default="", help="e.g. 'UQ, 4th-year business'")
    ap.add_argument("--rating", default="", help="1-5")
    ap.add_argument("--comment", default="")
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

    if args.show:
        print(f"state:  {STATE}")
        print(f"asked:  {st.get('asked', False)}   outcome: {st.get('outcome', '-')}")
        if os.path.exists(BOOK):
            print(f"\n--- {BOOK} ---")
            print(open(BOOK, encoding="utf-8").read())
        else:
            print("no testimonials stored")
        return 0

    if args.check:
        if st.get("asked"):
            return 1
        return 0

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
        os.makedirs(STATE_DIR, exist_ok=True)
        stars = ""
        try:
            n = int(args.rating)
            if 1 <= n <= 5:
                stars = "★" * n + "☆" * (5 - n)
        except ValueError:
            pass
        block = ["", "---", ""]
        if args.stamp:
            block.append(f"**{args.stamp}**")
        who = args.name.strip() or "Anonymous"
        if args.role.strip():
            who += f" — {args.role.strip()}"
        block.append(f"**{who}**" + (f"  {stars}" if stars else ""))
        if args.comment.strip():
            block += ["", "> " + args.comment.strip().replace("\n", "\n> "), ""]
        else:
            block += ["", "_Rating only; no comment left._", ""]
        with open(BOOK, "a", encoding="utf-8") as f:
            f.write("\n".join(block))

        url = share_url(args.name, args.role, args.rating, args.comment, args.stamp)
        with open(BOOK, "a", encoding="utf-8") as f:
            f.write(f"\n<!-- share: {url} -->\n")

        print("Saved to your own machine. Nothing has been sent anywhere.\n")
        print(f"  {BOOK}\n")
        print("Optional — if you're happy for the author to quote it, this link opens a")
        print("GitHub issue with your words already filled in. It is a DRAFT: nothing is")
        print("posted until you press Submit, and you can edit or abandon it there.\n")
        print(f"  {url}\n")
        print("Skipping is completely fine. The file above is yours to edit or delete,")
        print("and you will not be asked again.")
        st.update({"asked": True, "outcome": "saved"})
        save(st)
        return 0

    if args.share:
        if not os.path.exists(BOOK):
            print("Nothing stored yet.")
            return 2
        text = open(BOOK, encoding="utf-8").read()
        links = re.findall(r"<!-- share: (\S+) -->", text)
        if not links:
            print("No share link stored (entry predates this feature).")
            return 2
        print("Pre-filled share link(s) — a draft issue, not a post:\n")
        for u in links:
            print(f"  {u}\n")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
