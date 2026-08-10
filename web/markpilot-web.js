/* markpilot-web.js — the mechanical checks, for Claude's Analysis tool.
 *
 * Paste this whole file into the Analysis tool, then call:
 *
 *     markpilot(text, { limit: 2000, excludeRefs: true, excludeAppendix: true })
 *
 * `text` is the document as plain text. No imports, no network, no file access.
 *
 * WHY THIS EXISTS
 * ---------------
 * In Claude Code these checks are Python scripts. In claude.ai there is no shell,
 * so the same work would otherwise be done by reading and judging - and a language
 * model counting 2,000 words or cross-matching 30 citations by eye is not a
 * measurement, however confident the output sounds. This runs the real logic in
 * real code, so the numbers are numbers.
 *
 * WHAT IS NOT HERE, AND CANNOT BE
 * -------------------------------
 * The Analysis tool has no network, so link resolution, DOI verification and DOI
 * backfill are impossible here. Those are the checks that catch a fabricated or
 * mis-dated source, which is the highest-severity thing the full pipeline finds.
 * Do them with web search instead, one reference at a time, and say in the report
 * that they were done that way. Do not let their absence read as a pass.
 *
 * Every result carries `checked: true|false`. Anything false is COULD NOT CHECK,
 * which is never a pass.
 */

function mpWords(s) {
  return (s || "").split(/\s+/).filter(t => /[\p{L}\p{N}]/u.test(t));
}

function mpNorm(s) {
  return (s || "").normalize("NFKC").replace(/[   ]/g, " ");
}

/* A decade must not beat the real year: "Rethinking the 1970s ... 2019" keyed
 * 1970s in the original, producing a false year mismatch on a correct entry. */
function mpEntryYear(entry) {
  const paren = entry.match(/\(\s*((?:1[6-9]|20)\d{2}[a-z]?)\s*\)/);
  if (paren) return paren[1].toLowerCase();
  const re = /(?:1[6-9]|20)\d{2}[a-z]?/g;
  let m;
  while ((m = re.exec(entry)) !== null) {
    const after = entry.slice(m.index + m[0].length, m.index + m[0].length + 1);
    if (m[0].endsWith("s") || after === "s") continue;
    return m[0].toLowerCase();
  }
  return /\bn\.\s?d\.?/i.test(entry) ? "nd" : "";
}

const MP_REFS_RE =
  /^\s*(?:(?:chapter|section|part)\s+)?(?:[0-9]+(?:\.[0-9]+)*\s*[.):]?\s+)?(references?|reference\s+list|bibliography|works\s+cited|source\s+list)\s*:?\s*$/i;
const MP_APPX_RE =
  /^\s*(?:(?:chapter|section|part)\s+)?(?:[0-9]+(?:\.[0-9]+)*\s*[.):]?\s+)?(appendix|appendices|annexure|annex)\b/i;

/* Sentence connectives that can be mistaken for a lead surname in a NARRATIVE
 * citation ("However, Nguyen et al. (2021)"). Never applied to the parenthetical
 * form, where the comma disambiguates and An/So/Ho/Le are ordinary surnames. */
const MP_CONNECTIVES = new Set(("however therefore moreover furthermore thus hence " +
  "additionally consequently nevertheless nonetheless although though whereas " +
  "similarly conversely finally first firstly second secondly third thirdly overall " +
  "indeed notably importantly specifically instead meanwhile accordingly subsequently " +
  "in according recent recently research researchers studies study work evidence data " +
  "results findings for as while since both many several other others such here there " +
  "it they we one two by from at on an a and but or so yet if when where which the " +
  "this that these those figure table see chapter section appendix note source adapted " +
  "using based given each its their").split(" "));
const MP_NEVER = new Set("figure fig table chart exhibit appendix section eg ie cf vol no pp p n".split(" "));
const MP_PARTICLES = new Set("van von de del della der den du da dos das di la le el al bin ibn ter ten op st san".split(" "));

function mpSurname(tok) {
  return (tok || "").replace(/[^\p{L}'’-]/gu, "").replace(/['’]s?$/, "").toLowerCase();
}

function mpLead(phrase, dropConnectives) {
  const toks = (phrase || "").split(/[\s,&]+/).filter(Boolean);
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (["and", "et", "al", "al."].includes(t.toLowerCase())) continue;
    const s = mpSurname(t);
    if (!s || s.length < 2 || MP_NEVER.has(s)) continue;
    if (dropConnectives && MP_CONNECTIVES.has(s)) continue;
    if (MP_PARTICLES.has(s) && i + 1 < toks.length) {
      const nxt = mpSurname(toks[i + 1]);
      if (nxt && nxt.length >= 2 && !MP_NEVER.has(nxt)) return toks[i + 1];
    }
    return t;
  }
  return "";
}

/* Split into body / reference list / appendices. A "Reference" cell inside a
 * table hijacked this in the Python version; plain text has no table structure,
 * so a heading must be a SHORT STANDALONE line - that is the only signal left. */
function mpSplit(lines) {
  const body = [], refs = [], appx = [];
  let cur = body;
  for (const raw of lines) {
    const t = raw.trim();
    const short = t.length > 0 && t.length <= 90;
    if (short && MP_REFS_RE.test(t)) { cur = refs; continue; }
    if (short && MP_APPX_RE.test(t)) { cur = appx; continue; }
    cur.push(raw);
  }
  return { body, refs, appx };
}

/* One entry per logical reference: continuation lines are joined. A wrapped
 * hanging-indent list otherwise fragments into false "uncited" entries. */
function mpEntries(lines) {
  const START = /^\s*(?:van|von|de|del|della|der|den|du|da|di|la|le|el|al|ter|ten)?\s*(?:\[\d+\]|\d+[.)]\s+\p{Lu}|\p{Lu}[\p{L}'’-]+\s*,\s*(?:\p{Lu}\.|\p{Lu}[\p{L}'’-]+)|\p{Lu}[\p{L}&'’ .-]{2,60}?\.\s*\(\s*(?:1[6-9]|20)\d{2})/u;
  const out = [];
  let buf = [];
  const flush = () => {
    if (buf.length) {
      const j = buf.join(" ").replace(/\s+/g, " ").trim();
      if (mpWords(j).length >= 4) out.push(j);
      buf = [];
    }
  };
  for (const raw of lines) {
    const t = raw.trim();
    if (!t) { flush(); continue; }
    if (START.test(t) || !buf.length) { flush(); buf.push(t); } else { buf.push(t); }
  }
  flush();
  return out;
}

function mpCitations(bodyText) {
  const found = new Map();
  const add = (auth, yr, raw) => {
    const a = mpSurname(auth);
    if (!a || a.length < 2 || MP_NEVER.has(a)) return;
    const y = (yr || "").toLowerCase().replace(/[^0-9a-z]/g, "") || "nd";
    const k = a + "|" + y;
    if (!found.has(k)) found.set(k, { author: a, year: y, examples: [], n: 0 });
    const e = found.get(k);
    e.n++;
    if (e.examples.length < 2) e.examples.push(raw.trim().slice(0, 70));
  };
  /* The n.d. branch MUST require its periods: written loosely it matches the "nd"
   * inside "and", so every "Smith and Jones, 2020" keyed n.d. against itself. */
  const YEAR = "(?:1[6-9]|20)\\d{2}[a-z]?|\\bn\\.\\s?d\\.?";

  for (const m of bodyText.matchAll(/\(([^()]{2,300}?)\)/g)) {
    if (!new RegExp(YEAR).test(m[1])) continue;
    for (let chunk of m[1].split(";")) {
      const sec = chunk.split(/\bas\s+cited\s+in\b|\bcited\s+in\b|\bquoted\s+in\b/i);
      chunk = sec[sec.length - 1];
      const ym = chunk.match(new RegExp(YEAR));
      if (!ym) continue;
      let head = chunk.slice(0, ym.index).replace(/\b(?:see|also|e\.g\.|i\.e\.|cf\.)\b/gi, " ");
      const tok = mpLead(head, false);
      if (tok && (/\p{Lu}/u.test(tok[0]) || MP_PARTICLES.has(mpSurname(tok)))) add(tok, ym[0], chunk);
    }
  }
  /* "et al." must be its own optional trailing piece: folded into the co-author
   * alternation it loses every "Author et al. (Year)" citation entirely. */
  const NARR = new RegExp(
    "\\b((?:\\p{Lu}[\\p{L}'’-]{1,})(?:\\s*,\\s*(?:(?:and|&)\\s+)?\\p{Lu}[\\p{L}'’-]+" +
    "|\\s+(?:and|&)\\s+\\p{Lu}[\\p{L}'’-]+)*)(?:\\s+et\\s+al\\.?)?(?:['’]s)?\\s*\\(\\s*(" + YEAR + ")", "gu");
  for (const m of bodyText.matchAll(NARR)) {
    const tok = mpLead(m[1], true);
    if (tok) add(tok, m[2], m[0]);
  }
  return found;
}

function mpFigures(lines) {
  const CAP = /^\s*(figure|fig\.?|table|chart|exhibit|graph)\s*([A-Z]?\d+(?:\.\d+)*)\s*([.:—–-])?\s*(.*)$/i;
  const PROSE = /^(?:and\s|below\b|above\b|shows?|showed|presents?|summaris\w*|summariz\w*|illustrat\w*|report\w*|display\w*|indicat\w*|provid\w*|compar\w*|list\w*|outlin\w*|detail\w*|highlight\w*|demonstrat\w*|confirm\w*|suggest\w*|contain\w*|reveal\w*|sets? out)\b/i;
  const norm = (k, n) => {
    k = k.toLowerCase().replace(/\.$/, "");
    if (["fig", "figure", "graph", "chart"].includes(k)) k = "figure";
    return k + " " + n.toUpperCase();
  };
  const captions = new Map(), capLines = new Set();
  lines.forEach((raw, i) => {
    const t = mpNorm(raw).trim();
    if (!t || t.length >= 300) return;
    const m = t.match(CAP);
    if (!m) return;
    /* The separator after the number is the discriminator, not the word that
     * follows it: "Figure 2. Reported scores" is a caption, "Table 3 reports the
     * coefficients" is prose. */
    if (!m[3] && PROSE.test(m[4].trim())) return;
    const key = norm(m[1], m[2]);
    if (!captions.has(key)) captions.set(key, m[4].trim());
    capLines.add(i);
  });
  const refs = new Map();
  lines.forEach((raw, i) => {
    for (const m of mpNorm(raw).matchAll(/\b(Figure|Fig\.?|Table|Chart|Exhibit|Graph)\s*([A-Z]?\d+(?:\.\d+)*)\b/gi)) {
      const key = norm(m[1], m[2]);
      if (capLines.has(i) && captions.has(key)) continue;   // not a self-reference
      refs.set(key, (refs.get(key) || 0) + 1);
    }
  });
  const problems = [];
  for (const [k, cap] of captions) {
    if (!refs.get(k)) problems.push(`${k} is never referred to in the body text`);
    if (!cap) problems.push(`${k} has a number but no caption text`);
  }
  for (const [k, n] of refs) {
    if (!captions.has(k)) problems.push(`body text refers to ${k} (${n}x) but no such caption exists`);
  }
  return { captions: [...captions.keys()], problems, checked: captions.size > 0 || refs.size > 0 };
}

function markpilot(text, opts) {
  opts = opts || {};
  const lines = mpNorm(text).split(/\r?\n/);
  const { body, refs, appx } = mpSplit(lines);

  // ---- word count
  const all = mpWords(lines.join(" ")).length;
  let counted = lines;
  const removed = {};
  if (opts.excludeRefs) { removed["references section"] = mpWords(refs.join(" ")).length; }
  if (opts.excludeAppendix) { removed["appendix section"] = mpWords(appx.join(" ")).length; }
  counted = body.concat(opts.excludeRefs ? [] : refs, opts.excludeAppendix ? [] : appx);
  let countedN = mpWords(counted.join(" ")).length;

  const noop = Object.entries(removed).filter(([, v]) => !v).map(([k]) => k);

  // ---- citations
  const entries = mpEntries(refs);
  const cites = mpCitations(body.join("\n"));
  const byAuthor = new Map();
  const keys = new Set();
  for (const e of entries) {
    const a = mpSurname(mpLead(e.replace(/^\s*\[?\d+\]?[.)]?\s*/, "").split(/[.,]/).slice(0, 2).join(" "), false));
    const y = mpEntryYear(e) || "nd";
    keys.add(a + "|" + y);
    if (!byAuthor.has(a)) byAuthor.set(a, new Set());
    byAuthor.get(a).add(y);
  }
  const orphans = [], yearMismatch = [];
  for (const [k, c] of cites) {
    if (!byAuthor.has(c.author)) orphans.push(c);
    else if (!byAuthor.get(c.author).has(c.year) && c.year !== "nd")
      yearMismatch.push({ ...c, listed: [...byAuthor.get(c.author)] });
  }
  const citedKeys = new Set([...cites.keys()]);
  const uncited = entries.filter(e => {
    const a = mpSurname(mpLead(e.replace(/^\s*\[?\d+\]?[.)]?\s*/, "").split(/[.,]/).slice(0, 2).join(" "), false));
    return a && !citedKeys.has(a + "|" + (mpEntryYear(e) || "nd"));
  });

  const citeChecked = cites.size > 0 && entries.length > 0;

  return {
    words: {
      everything: all,
      counted: countedN,
      removed,
      limit: opts.limit || null,
      delta: opts.limit ? countedN - opts.limit : null,
      verdict: opts.limit ? (countedN > opts.limit ? "OVER" : "within") : null,
      flagsThatRemovedNothing: noop,
      checked: all > 0
    },
    references: {
      entries: entries.length,
      distinctCitations: cites.size,
      orphanCitations: orphans,
      yearMismatches: yearMismatch,
      uncitedEntries: uncited,
      checked: citeChecked,
      note: citeChecked ? null :
        "COULD NOT CHECK - no reference list found, or no citations detected. " +
        "This is NOT a pass: a document whose citations the parser cannot see looks " +
        "exactly like one with no citation problems."
    },
    figures: mpFigures(lines),
    notChecked: [
      "link resolution — no network in the Analysis tool",
      "DOI verification against Crossref — no network",
      "DOI backfill for entries with no identifier — no network",
      "whether any source is real — use web search, one reference at a time"
    ]
  };
}

/* ---------------------------------------------------------------------------
 * testimonialLink() - the feedback step, for an environment with no shell.
 *
 * In Claude Code this is testimonial.py: it stores the answer on the user's own
 * machine, remembers that it asked, and prints a pre-filled link. Here there is
 * no filesystem and no persistent state, so two of those three are simply not
 * available and must not be pretended at:
 *
 *   - nothing is stored anywhere, so there is no local copy to fall back on;
 *   - "ask at most once, ever" cannot be enforced across chats. It degrades to
 *     "ask at most once per conversation", which is a weaker promise. Do not
 *     claim the stronger one.
 *
 * What DOES survive is the part that matters: the consent split, and a link that
 * needs no account. Build it here rather than by hand - percent-encoding a
 * comment containing an apostrophe, an ampersand or a line break is exactly the
 * kind of thing that silently produces a broken link.
 *
 * Nothing here sends anything. It returns a string.
 * ------------------------------------------------------------------------- */

var MP_FORM = "https://nickwfraser.dev/testimonial";
var MP_URL_BUDGET = 1900;

function testimonialLink(a) {
  a = a || {};
  var consent = a.consent === "named" ? "named" : a.consent === "anon" ? "anon" : "none";
  // Private means private. There is no link, because there is nothing to send.
  if (consent === "none") return null;

  var rating = parseInt(a.rating, 10);
  var build = function (comment) {
    var q = [];
    var add = function (k, v) {
      if (v !== "" && v !== null && v !== undefined) {
        q.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
      }
    };
    add("rating", rating >= 1 && rating <= 5 ? String(rating) : "");
    add("consent", consent);
    add("comment", comment);
    add("source", "claude-web");
    // The name rides along only on the consent that asked for it. Same rule as
    // public_record() in the skill, and for the same reason.
    if (consent === "named") {
      add("name", (a.name || "").trim());
      add("role", (a.role || "").trim());
    }
    return MP_FORM + "?" + q.join("&");
  };

  var comment = (a.comment || "").replace(/\s+/g, " ").trim();
  var url = build(comment);
  if (url.length <= MP_URL_BUDGET) return url;
  var lo = 0, hi = comment.length, best = build("");
  while (lo <= hi) {
    var mid = (lo + hi) >> 1;
    var c = comment.slice(0, mid).replace(/\s+$/, "");
    var u = build(c ? c + "…" : "");
    if (u.length <= MP_URL_BUDGET) { best = u; lo = mid + 1; } else { hi = mid - 1; }
  }
  return best;
}
