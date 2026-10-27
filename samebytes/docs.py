# -*- coding: utf-8 -*-
"""Do the docs still hold together? The markdown checks that need no project knowledge.

Every repository in the family samebytes came from wrote these by hand, each
slightly differently: economicspace's `verify_docs.py` checks 4, 5 and 6,
spacecost's `tests/test_docs.py`, spacevalue's anchor test. Two copies of a
check drift (spacevalue's anchor rule dropped GitHub's `-1` suffix for a
repeated heading; spacecost's link check resolved against the repository root,
so a doc in a subdirectory could not link back up), and a fix to one never
reached the others. This is the one copy.

    links(root, docs)        every relative link names a file that exists, and
                             every #anchor a heading that does
    structure(root, docs, one_h1=True)
                             balanced fences, no ragged tables, no heading-level
                             jumps, no repeated h1/h2, and exactly one h1
    dashes(root, files, prose_only=())
                             no em- or en-dash, and no line opening with the bare
                             comma a dash-removal pass leaves behind
    pairs(root, answers, rules, register_header=None)
                             no line of the rules file shares three distinctive
                             numbers with a line of an answer file, unless a
                             register table lists them
    transfer(root, before, after)
                             every distinctive number in `before` still appears
                             somewhere in `after` (the audit for a reorganisation)
    pins(root, files, owner, packages=None, claims=())
                             every git pin of one of `owner`'s repositories
                             (`github.com/<owner>/<repo>@<ref>`, and prose
                             claims by pattern) names one ref per repository;
                             `pin_copies` returns the copies themselves

Every check takes the repository root and paths relative to it (an absolute
path also works), and returns `(findings, checked)`: a list of one-line
strings, empty when clean, and how many things it read. Print the count.
A check that read nothing passes, and the count is the only thing that tells.

A NAMED FILE THAT IS NOT ON DISK IS A FINDING, NEVER A SKIP. The lists a
caller passes name files the repository owns, so a name with nothing behind it
means a rename the list missed, or a synced folder that has not materialised
the file yet. economicspace proved the second on 2026-09-15: one docs run read
33 files and the next 35, with no commit in between, and both said OK.

Nothing here imports anything outside the standard library.
"""
import ast
import io
import os
import re
import tokenize
from urllib.parse import unquote

# `[text](target)`; a title after a space (`[t](x "title")`) is not part of the target.
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")

# A target with a URL scheme (https:, mailto:) is outside the repository.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

EM, EN = "\u2014", "\u2013"

# A line that begins with a bare comma is what an ASCII pass leaves where an
# em-dash had OPENED a continuation line. The sentence stops parsing in English
# and nothing notices: economicspace found twelve in its modules and eight more
# in its docs a week later, because the first sweep looked only at Python.
# Anchored on start-of-line (after an optional `#`), so a comma inside a
# sentence is untouched.
ORPHAN_COMMA = re.compile(r"^\s*(?:#\s*)?,\s+\S")


def read(path):
    """A whole file as text, always UTF-8 (the Windows locale default is cp1252)."""
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _resolve(root, name):
    """(absolute path, the name as it is reported) for a path relative to `root`."""
    path = os.path.normpath(os.path.join(root, name))
    try:
        rel = os.path.relpath(path, root)
    except ValueError:                  # another drive
        rel = path
    return path, rel.replace(os.sep, "/")


def missing(root, names):
    """The names in `names` with no file behind them, as findings."""
    return ["%s is listed and is not on disk" % _resolve(root, n)[1]
            for n in names if not os.path.exists(_resolve(root, n)[0])]


def slugs(text):
    """The anchors GitHub gives the headings in `text`, with `-1`, `-2` for repeats.

    The underscore is a word character and GitHub KEEPS it:
    `## Reading profitability_catalog.csv` is
    `#reading-profitability_catalogcsv`. A rule that stripped it reported a
    correct link as broken, and a broken checker looks exactly like a broken
    document. Headings inside code fences are not headings.
    """
    out, seen, infence = set(), {}, False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            infence = not infence
            continue
        m = None if infence else re.match(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$", line)
        if not m:
            continue
        h = re.sub(r"[`*~]|\[|\]|\(|\)", "", m.group(2))
        s = re.sub(r"[^\w\s\-]", "", h, flags=re.UNICODE).strip().lower()
        s = s.replace(" ", "-")
        k = seen.get(s, 0)
        seen[s] = k + 1
        out.add(s if k == 0 else "%s-%d" % (s, k))
    return out


def links(root, docs):
    """Every relative link in `docs` names a file that exists, and its #anchor a heading.

    A target resolves relative to the LINKING file, not to `root`: a doc in a
    subdirectory links back up with `../`, and resolving from the root reports
    every such link broken. An anchor is checked in whatever markdown file the
    link lands in, listed or not; an anchor into a non-markdown file (`#L10`)
    is not checked. A target with a URL scheme is skipped: this checks what
    the repository controls. `checked` counts the anchors resolved.
    """
    bad = missing(root, docs)
    cache, n = {}, 0
    for name in docs:
        src, rel = _resolve(root, name)
        if not os.path.exists(src):
            continue
        base = os.path.dirname(src)
        for m in LINK.finditer(read(src)):
            target = m.group(2)
            if _SCHEME.match(target) or target.startswith("#!"):
                continue
            fpart, _, apart = target.partition("#")
            dest = os.path.normpath(os.path.join(base, unquote(fpart))) if fpart else src
            if not os.path.exists(dest):
                bad.append("%s -> %s  (no such file)" % (rel, target))
                continue
            if not apart or not dest.lower().endswith(".md"):
                continue
            if dest not in cache:
                cache[dest] = slugs(read(dest))
            n += 1
            if apart not in cache[dest]:
                bad.append("%s -> %s  (no such anchor)" % (rel, target))
    return bad, n


def structure(root, docs, one_h1=True):
    """Balanced fences, no ragged tables, no heading jumps, one h1, no repeated h1/h2.

    A ragged table (rows with different numbers of `|`) renders as literal
    pipes. A heading that jumps a level (h2 to h4) breaks the outline. A
    repeated h1 or h2 makes an ambiguous anchor; a repeated h3 is normal (a
    changelog's "### Verification" under every release) and is not flagged.
    Exactly one h1, the title, unless `one_h1` is False (a long history that
    divides itself into parts with h1s). `checked` counts the files read.
    """
    bad = missing(root, docs)
    files = 0
    for name in docs:
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        files += 1
        lines = read(path).split("\n")

        fences = [i for i, l in enumerate(lines, 1) if l.strip().startswith("```")]
        if len(fences) % 2:
            bad.append("%s: unbalanced code fences (last at line %d)" % (rel, fences[-1]))

        infence, block, start, prev, heads, h1 = False, [], 0, 0, {}, 0
        for i, l in enumerate(lines + [""], 1):
            if l.strip().startswith("```"):
                infence = not infence
                continue
            if infence:
                continue
            s = l.strip()
            if s.startswith("|"):
                if not block:
                    start = i
                block.append(s)
            else:
                if len(block) >= 2 and len({b.count("|") for b in block}) > 1:
                    bad.append("%s: ragged table at line %d" % (rel, start))
                block = []
            m = re.match(r"^(#{1,6})\s+\S", l)
            if m:
                lvl = len(m.group(1))
                if prev and lvl > prev + 1:
                    bad.append("%s: heading jumps h%d -> h%d at line %d" % (rel, prev, lvl, i))
                prev = lvl
                h1 += lvl == 1
                if lvl <= 2:
                    heads[s] = heads.get(s, 0) + 1
        if one_h1 and h1 != 1:
            bad.append("%s: %d h1 headings, want exactly 1" % (rel, h1))
        for h, c in heads.items():
            if c > 1:
                bad.append("%s: duplicate heading %r (%dx)" % (rel, h[:60], c))
    return bad, files


def python_prose_lines(src):
    """The line numbers of `src` that are comments or docstrings.

    Raises SyntaxError (or tokenize.TokenError) when `src` does not parse.
    """
    rows = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            rows.add(tok.start[0])
    for node in ast.walk(ast.parse(src)):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and body:
            f = body[0]
            if (isinstance(f, ast.Expr) and isinstance(f.value, ast.Constant)
                    and isinstance(f.value.value, str)):
                rows.update(range(f.lineno, f.end_lineno + 1))
    return rows


def dashes(root, files, prose_only=()):
    """No em- or en-dash in text a person reads, and no line opening with a bare comma.

    `files` are checked whole. `prose_only` are Python sources checked in their
    comments and docstrings only, for a module whose string literals are DATA
    (a `notes` column written into a CSV keeps whatever it says). This is a
    ratchet, not a style opinion: once the dashes are out, they drift back one
    commit at a time unless something fails. `checked` counts the files read.
    """
    bad = missing(root, list(files) + list(prose_only))
    n = 0
    for name in list(files) + list(prose_only):
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        n += 1
        src = read(path)
        rows = None
        if name in prose_only:
            try:
                rows = python_prose_lines(src)
            except (SyntaxError, tokenize.TokenError) as exc:
                bad.append("%s: could not parse (%s)" % (rel, exc))
                continue
        for i, line in enumerate(src.split("\n"), 1):
            if rows is not None and i not in rows:
                continue
            if EM in line or EN in line:
                bad.append("%s:%d  em/en dash  %s" % (rel, i, line.strip()[:60]))
            elif ORPHAN_COMMA.match(line):
                bad.append("%s:%d  line opens with a bare comma  %s"
                           % (rel, i, line.strip()[:60]))
    return bad, n


# What `pairs` counts as a distinctive number: a decimal, or a digit followed by
# three or more digits and commas, never a year. Specific enough that two lines
# sharing three of them are quoting one measurement rather than coinciding; a
# line carrying `2`, `5` and `64` shares those with half a repository.
# A comma straight after a thousands figure stays on its token (`1,555,667,`
# in a list), so that copy does not match `1,555,667` elsewhere: a known miss,
# kept because it is the rule check 12 was proved with, and a fix is a release.
PAIR_NUMBER = re.compile(r"\d[\d,]*\.\d+|\d[\d,]{3,}")
PAIR_YEAR = re.compile(r"(?:19|20)\d\d")

# A dotted version (`1.21.0`, `v1.17.7`) is an identifier, not a measurement,
# and a link like `[calc v1.12.0](versions.md#calc-v1120--transportation-v1100)`
# made three "shared numbers" out of one anchor. Both are stripped BEFORE
# tokenising, because an anchor's digits cannot be told from a real figure once
# they are tokens.
_SEMVER = re.compile(r"v?\d+\.\d+\.\d+")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")

# What `transfer` counts as a distinctive number: a decimal, a properly
# separated thousands figure, or a bare integer of four or more digits, never a
# 20xx year. Not `PAIR_NUMBER`, and not unified with it: each is the rule its
# check was proved with (economicspace's `verify_docs.py` checks 12 and 10), and
# changing either changes what a consumer's audit reports.
TRANSFER_NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\b\d{4,}\b")
TRANSFER_YEAR = re.compile(r"20\d\d")


def figures(line):
    """The distinctive numbers on one line, as `pairs` reads them: versions and link targets dropped."""
    line = _LINK_TARGET.sub("]()", line)
    line = _SEMVER.sub(" ", line)
    return {m.group(0) for m in PAIR_NUMBER.finditer(line)
            if not PAIR_YEAR.fullmatch(m.group(0))}


def pairs(root, answers, rules, register_header=None):
    """No line of `rules` quotes a measurement a line of one of `answers` quotes.

    Two files that both claim to be CURRENT (a README that carries the numbers
    and a rules file that should carry none) drift when they share a figure:
    the next release moves one copy. A pair is two lines, one in `rules` and
    one in an answer, sharing three or more `figures`. The answers are not
    paired with each other: they are one answer split across files, and a
    result quoting the model's own figure is not a copy.

    A pair is allowed when its shared numbers are on the register: the rows of
    a table, in any of the files read, whose header line is exactly
    `register_header`. Register rows quote what they register by design, so
    they are never one side of a pair. A finding names the two lines and the
    shared numbers the register lacks, once per set of shared numbers.
    `checked` counts every pair found, registered or not.
    """
    names = list(answers) + [rules]
    bad = missing(root, names)
    reg, lines = set(), {}
    for name in names:
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        rows, in_register = [], False
        for i, raw in enumerate(read(path).splitlines(), 1):
            if register_header is not None and raw.strip() == register_header:
                in_register = True
                continue
            if in_register:
                # The table ends at the first line that is not one of its rows.
                if raw.startswith("|"):
                    reg |= figures(raw)
                    continue
                in_register = False
            rows.append((i, figures(raw)))
        lines[name] = (rel, rows)

    n, seen = 0, set()
    rrel, rrows = lines.get(rules, (None, ()))
    for name in answers:
        arel, arows = lines.get(name, (None, ()))
        for ia, fa in arows:
            if len(fa) < 3:
                continue
            for ib, fb in rrows:
                shared = fa & fb
                if len(shared) < 3:
                    continue
                n += 1
                off = shared - reg
                key = tuple(sorted(shared))
                if not off or key in seen:
                    continue
                seen.add(key)
                bad.append("%s:%d and %s:%d both quote %s, not on the register"
                           % (arel, ia, rrel, ib, ", ".join(sorted(off))))
    return bad, n


def transfer(root, before, after):
    """Every distinctive number in `before` still appears somewhere in `after`.

    The check for a reorganisation: snapshot a document, split or rewrite it,
    then ask whether any measurement was dropped rather than moved. A line diff
    cannot answer that; economicspace's split of its history into versions.md
    gave 302 differing lines and could not tell 26 dropped measurements from a
    reflowed paragraph. A number survives if its text occurs anywhere in the
    `after` files taken together. A finding is the lost number and the line it
    came from, sorted by number. `checked` counts the distinct numbers in
    `before`.
    """
    after = list(after)
    bad = missing(root, [before] + after)
    src = _resolve(root, before)[0]
    if not os.path.exists(src):
        return bad, 0
    old = read(src)
    hay = "\n".join(read(_resolve(root, p)[0]) for p in after
                    if os.path.exists(_resolve(root, p)[0]))
    seen = {}
    for m in TRANSFER_NUMBER.finditer(old):
        tok = m.group(0)
        if tok in seen or TRANSFER_YEAR.fullmatch(tok):
            continue
        a = old.rfind("\n", 0, m.start()) + 1
        b = old.find("\n", m.end())
        seen[tok] = old[a:b if b > 0 else None].strip()
    lost = sorted((t, c) for t, c in seen.items() if t not in hay)
    bad += ["%-14s | %s" % (t, c[:110]) for t, c in lost]
    return bad, len(seen)


# How far before a prose claim its package must be named, in characters.
CLAIM_WINDOW = 200


def _pin_url(owner):
    """`github.com/<owner>/<repo>[.git]@<ref>`: groups repo and ref.

    The ref ends at whitespace, a quote, a backtick, a comma or a closing
    bracket, so a pin inside `"..."`, a markdown link or a YAML string reads
    the same; a sentence's full stop is stripped by the caller.
    """
    return re.compile(r"github\.com/%s/([A-Za-z0-9_.-]+?)(?:\.git)?@([^\s\"'`,)\]>]+)"
                      % re.escape(owner))


def _line(text, at):
    """The 1-based line number of offset `at` in `text`."""
    return text.count("\n", 0, at) + 1


def pin_copies(root, files, owner, packages=None, claims=()):
    """{repo: {ref: [where, ...]}}: every pin of one of `owner`'s repositories in `files`.

    A pin is the URL form, `github.com/<owner>/<repo>@<ref>` (pip's
    `git+https://...@vX.Y.Z`, a CI step, a README's install line), found rather
    than looked up, so a copy typed tomorrow joins with no edit. `where` is
    `file:line`.

    `claims` adds the prose form: `(pattern, files)` pairs, `pattern` a regex
    whose first group is the ref (`pinned to tag `(v[^`]+)``). Prose carries no
    URL, so a claim belongs to the package named nearest before it, within
    CLAIM_WINDOW characters; one named nowhere in that window is not a pin of
    anything and is left out. `where` is then `file:line (prose)`. The
    candidate names are `packages` when given, else every repository the URL
    form found. Files that are not on disk are skipped here; `pins` reports
    them.
    """
    url = _pin_url(owner)
    out = {}
    for name in files:
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        text = read(path)
        for m in url.finditer(text):
            ref = m.group(2).rstrip(".:;")
            out.setdefault(m.group(1), {}).setdefault(ref, []).append(
                "%s:%d" % (rel, _line(text, m.start())))
    names = list(packages) if packages is not None else sorted(out)
    for pattern, claim_files in claims:
        pattern = re.compile(pattern) if isinstance(pattern, str) else pattern
        for name in claim_files:
            path, rel = _resolve(root, name)
            if not os.path.exists(path):
                continue
            text = read(path)
            for m in pattern.finditer(text):
                window = text[max(0, m.start() - CLAIM_WINDOW):m.start()]
                near = max(names, key=lambda p: window.rfind(p), default=None)
                if near is None or window.rfind(near) < 0:
                    continue
                out.setdefault(near, {}).setdefault(m.group(1), []).append(
                    "%s:%d (prose)" % (rel, _line(text, m.start())))
    return out


def pins(root, files, owner, packages=None, claims=()):
    """Each of `owner`'s repositories is pinned at one ref everywhere it is pinned.

    Two copies of a pin at different refs install two different revisions,
    and both import cleanly: a repin that reaches some copies and not others
    says nothing. `files` are read for the URL form and `claims` for the prose
    form, as `pin_copies` describes. Leave history (a changelog, a release
    log) out of `files`: an old pin there is an account of what happened.

    With `packages`, only those repositories are held, each must be pinned at
    least once, and every file of every claim must state a ref for each of
    them (a reworded sentence the pattern stops matching is how a prose check
    goes back to reading nothing). A finding names each ref and where it is.
    `checked` counts the copies found.
    """
    names = list(files) + [f for _, fs in claims for f in fs]
    bad = missing(root, list(dict.fromkeys(names)))
    found = pin_copies(root, files, owner, packages, claims)
    held = list(packages) if packages is not None else sorted(found)
    for pkg in held:
        refs = found.get(pkg, {})
        if not refs:
            bad.append("no pin of %s/%s in the %d file(s) read" % (owner, pkg, len(files)))
        elif len(refs) > 1:
            bad.append("%s is pinned at %d refs: %s"
                       % (pkg, len(refs), "; ".join("%s in %s" % (ref, ", ".join(where))
                                                    for ref, where in sorted(refs.items()))))
    if packages is not None:
        for pattern, claim_files in claims:
            text = getattr(pattern, "pattern", pattern)
            for name in claim_files:
                path, rel = _resolve(root, name)
                if not os.path.exists(path):
                    continue
                for pkg in held:
                    stated = [w for where in found.get(pkg, {}).values() for w in where
                              if w.startswith(rel + ":") and w.endswith(" (prose)")]
                    if not stated:
                        bad.append("%s states no %s ref in a form `pins` reads (%s)"
                                   % (rel, pkg, text))
    return bad, sum(len(where) for pkg in held for where in found.get(pkg, {}).values())
