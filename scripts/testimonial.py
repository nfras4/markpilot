#!/usr/bin/env python3
"""testimonial.py - ask once, store locally, never send.

    python testimonial.py --check                 should we ask this user?
    python testimonial.py --save --name "..." --rating 5 --comment "..."
    python testimonial.py --decline                they said no; never ask again
    python testimonial.py --show                   print what has been stored
    python testimonial.py --reset                  clear the state (testing)

Design constraints, in priority order
-------------------------------------
1. **Ask at most once, ever.** State lives in ~/.markpilot/state.json, outside the
   skill directory, so reinstalling or re-cloning the skill does not reset it and
   the file never lands in git.
2. **Never transmit anything.** This script writes a local file and prints where
   it is. It opens no sockets. Sending a testimonial is the user's action, taken
   afterwards, with the text in front of them - not something a tool does on their
   behalf. A skill that quietly uploaded a name and comment would be doing
   something the user did not ask for, and this one is published for other people
   to install.
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
import sys

STATE_DIR = os.path.join(os.path.expanduser("~"), ".markpilot")
STATE = os.path.join(STATE_DIR, "state.json")
BOOK = os.path.join(STATE_DIR, "testimonials.md")
SHARE_URL = "https://github.com/nfras4/markpilot/issues/new?title=Testimonial"


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
        if not args.comment.strip():
            print("error: --comment is required to save", file=sys.stderr)
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
        block += ["", "> " + args.comment.strip().replace("\n", "\n> "), ""]
        with open(BOOK, "a", encoding="utf-8") as f:
            f.write("\n".join(block))

        print("Saved locally. Nothing has been sent anywhere.\n")
        print(f"  {BOOK}\n")
        print("If you'd like the author to be able to use it, you can send it yourself:")
        print(f"  {SHARE_URL}")
        print("\nThat is entirely optional, and the file is yours to edit or delete.")
        st.update({"asked": True, "outcome": "saved"})
        save(st)
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
