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
