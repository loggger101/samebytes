# -*- coding: utf-8 -*-
"""House rules over Python sources: the checks every repository in the family re-wrote.

Each of these has failed once somewhere, which is why it is a check and not
advice, and each existed in four or five hand-written copies that had already
drifted (one accepted any cp1252 character in printed text where the rest
required ASCII; two skipped the import rule on Python 3.9 rather than answer
it). This is the one copy.

    docstrings(root, files)          every module, class and function, nested
                                     ones included, has a docstring
    non_ascii(root, files)           every byte is ASCII
    printed_non_ascii(root, files)   every string literal passed to print/say is
                                     ASCII (comments, docstrings and data keep
                                     their characters)
    calls(root, files, names)        where `print(...)` (or any named call) is made
    imports(root, files, allowed, lazy)
                                     module level imports the standard library and
                                     `allowed` only; `lazy` only inside functions
    quiet_import(root, statement)    a fresh interpreter running `statement` exits
                                     0, prints nothing and creates no file
    version_written_once(root, package)
                                     pyproject reads the version off
                                     `package.__version__` and types none itself
    requirements_match(root)         requirements.txt and pyproject's dependencies
                                     name the same packages
    missing_help(root, path, class_name, fields=None, skip=())
                                     every field of a config class carries the
                                     comment `field_docs` reads as its help

Like `samebytes.docs`, every check takes the repository root and paths relative
to it (absolute paths work too) and returns `(findings, checked)`: one-line
findings, empty when clean, and how many things were read. A listed file that
is not on disk is a finding. Nothing here imports beyond the standard library.

One reader sits beside the checks: `field_docs(path, class_name)`, field name ->
{"help", "section"} scraped from the comments in a config class's source. It is
economicspace's dashboard rule, moved from its `ui_meta.scrape_field_docs`:
the comment block directly above a field, stopping at a blank line or a section
banner, plus any trailing comment on the field's own line; the banner above it
is the field's section. A dashboard that shows these as help and a package that
tests its own config by them must read one rule, so this is the one copy (a
hand-written copy in spacecost's tests had already drifted from it). It answers
{} for a file it cannot read or parse and for a class it cannot find; the
check `missing_help` tells those apart.
"""
import ast
import importlib.util
import io
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
import tokenize
from typing import Dict, List, Optional

from .docs import _resolve, missing, read

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _parsed(root, files, bad):
    """Yield (relative name, parsed tree) per file; unparseable files become findings."""
    for name in files:
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(read(path), filename=rel)
        except SyntaxError as exc:
            bad.append("%s: could not parse (%s)" % (rel, exc))
            continue
        yield rel, tree


def docstrings(root, files):
    """Every module, class and function in `files` carries a docstring.

    NESTED definitions count. The sharpest note in a file is often on a
    six-line closure, and exempting definitions by size or depth exempts
    exactly the ones worth reading. `checked` counts modules plus definitions.
    """
    bad, n = missing(root, files), 0
    for rel, tree in _parsed(root, files, bad):
        n += 1
        if not ast.get_docstring(tree):
            bad.append("%s has no module docstring" % rel)
        for node in ast.walk(tree):
            if isinstance(node, _DEFS):
                n += 1
                if not ast.get_docstring(node):
                    bad.append("%s:%d  %s has no docstring" % (rel, node.lineno, node.name))
    return bad, n


def non_ascii(root, files):
    """Every byte of `files` is ASCII.

    For sources that print, or are run by an interpreter that reads them in
    the locale's encoding (a PowerShell script on Windows PowerShell 5.1).
    `checked` counts the files read.
    """
    bad, n = missing(root, files), 0
    for name in files:
        path, rel = _resolve(root, name)
        if not os.path.exists(path):
            continue
        n += 1
        with open(path, "rb") as fh:
            lines = [i for i, line in enumerate(fh.read().splitlines(), 1)
                     if any(b > 127 for b in line)]
        if lines:
            bad.append("%s: non-ASCII on lines %s" % (rel, lines[:20]))
    return bad, n


def printed_non_ascii(root, files, callers=("print", "say")):
    """Every string literal inside a call to one of `callers` is ASCII.

    Windows gives a REDIRECTED stdout cp1252, so one non-ASCII character in a
    printed string kills `tool build > run.log` with UnicodeEncodeError, and
    never in a console, where it is tested. The rule is ASCII, not "encodable
    in cp1252": the next host's console is not cp1252 either. Comments,
    docstrings and data strings keep their characters. `checked` counts the
    calls examined.
    """
    bad, n = missing(root, files), 0
    for rel, tree in _parsed(root, files, bad):
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in callers):
                continue
            n += 1
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    odd = sorted({c for c in sub.value if ord(c) > 127})
                    if odd:
                        bad.append("%s:%d  %s(...) prints %r"
                                   % (rel, sub.lineno, node.func.id, "".join(odd)))
    return bad, n


def calls(root, files, names=("print",)):
    """Every call to a bare name in `names`, as a finding; for "no print outside the CLI".

    `checked` counts the files read.
    """
    bad, n = missing(root, files), 0
    for rel, tree in _parsed(root, files, bad):
        n += 1
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in names):
                bad.append("%s:%d  calls %s()" % (rel, node.lineno, node.func.id))
    return bad, n


def is_stdlib(name):
    """Whether the top-level module `name` belongs to the standard library.

    `sys.stdlib_module_names` from Python 3.10. Before it, a module is
    standard library when it is built in or its spec's origin lies under the
    interpreter's stdlib directory and outside site-packages, which answers
    rather than skipping: a rule that skips on the oldest supported Python is
    unchecked exactly where an old-stdlib import would break.
    """
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return name in names
    if name in sys.builtin_module_names or name == "__future__":
        return True
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    origin = getattr(spec, "origin", None) if spec else None
    if not origin or origin in ("built-in", "frozen"):
        return bool(spec)
    stdlib = os.path.normcase(os.path.realpath(sysconfig.get_paths()["stdlib"]))
    where = os.path.normcase(os.path.realpath(origin))
    return where.startswith(stdlib + os.sep) and "site-packages" not in where


def _imported(node):
    """(top-level module name, line) for each absolute import under `node`."""
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name.split(".")[0], n.lineno
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            yield n.module.split(".")[0], n.lineno


def imports(root, files, allowed=(), lazy=()):
    """Module level imports the standard library and `allowed`; `lazy` only in functions.

    A package that imports numpy inside the one function that needs it can
    declare no dependency and never move a consumer's pin; `lazy` holds it to
    that. Relative imports are the package's own. Code at module level means
    every top-level statement except a def or class body (so a guarded
    `try: import x` counts). `checked` counts the import statements read.
    """
    bad, n = missing(root, files), 0
    allowed, lazy = set(allowed), set(lazy)
    for rel, tree in _parsed(root, files, bad):
        top = set()
        for stmt in tree.body:
            if isinstance(stmt, _DEFS):
                continue
            for name, line in _imported(stmt):
                top.add(line)
                if not (is_stdlib(name) or name in allowed):
                    bad.append("%s:%d  imports %s at module level" % (rel, line, name))
        for name, line in _imported(tree):
            n += 1
            if line not in top and not (is_stdlib(name) or name in allowed or name in lazy):
                bad.append("%s:%d  imports %s" % (rel, line, name))
    return bad, n


def quiet_import(root, statement, env=None, timeout=120):
    """Run `statement` in a fresh interpreter: it must exit 0, print nothing, create nothing.

    A library imported for one constant that prints a banner, or makes its
    output directory, is a nuisance nobody notices from inside the package: it
    works either way. It has to be a fresh interpreter, because the test
    runner has already imported the package. `root` goes first on sys.path,
    so the checkout is what imports, and the working directory is a new empty
    one, so a created file is seen. `env` updates the environment; a value of
    None removes that variable. `checked` is 1.
    """
    environ = dict(os.environ)
    for k, v in (env or {}).items():
        if v is None:
            environ.pop(k, None)
        else:
            environ[k] = v
    code = "import sys; sys.path.insert(0, %r)\n%s" % (os.path.abspath(root), statement)
    bad = []
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=environ,
                           capture_output=True, text=True, timeout=timeout)
        made = sorted(os.listdir(cwd))
    if r.returncode != 0:
        bad.append("%r exited %d: %s" % (statement, r.returncode, r.stderr.strip()[-300:]))
    elif r.stderr:
        bad.append("%r wrote to stderr: %r" % (statement, r.stderr[:300]))
    if r.stdout:
        bad.append("%r wrote to stdout: %r" % (statement, r.stdout[:300]))
    if made:
        bad.append("%r created %s in its working directory" % (statement, made))
    return bad, 1


def version_written_once(root, package):
    """pyproject.toml reads its version off `package.__version__` and types none itself.

    `checked` is 1.
    """
    path, rel = _resolve(root, "pyproject.toml")
    if not os.path.exists(path):
        return missing(root, ["pyproject.toml"]), 0
    text = read(path)
    bad = []
    if not re.search(r'^dynamic\s*=\s*\[[^\]]*"version"', text, re.M):
        bad.append('%s: no dynamic = ["version"]' % rel)
    attr = re.escape("%s.__version__" % package)
    if not re.search(r'^version\s*=\s*\{\s*attr\s*=\s*"%s"\s*\}' % attr, text, re.M):
        bad.append('%s: no version = { attr = "%s.__version__" }' % (rel, package))
    if re.search(r'^version\s*=\s*"', text, re.M):
        bad.append("%s: types a version string" % rel)
    pkg = os.path.join(root, package, "__init__.py")
    if not re.search(r'^__version__\s*=\s*"\d+\.\d+\.\d+"', read(pkg) if os.path.exists(pkg) else "", re.M):
        bad.append("%s/__init__.py: no __version__ = \"X.Y.Z\"" % package)
    return bad, 1


def _names(specs):
    """The distribution names in a list of requirement strings, lower-cased."""
    return {re.split(r"[<>=!~;\[ @]", s.strip(), maxsplit=1)[0].strip().lower().replace("_", "-")
            for s in specs if s.strip() and not s.strip().startswith(("#", "-"))}


def requirements_match(root, requirements="requirements.txt"):
    """`requirements` and pyproject's `dependencies` name the same distributions.

    Versions and markers are not compared: the two files say different things
    about them on purpose (a range for the package, a pin for a run).
    `checked` counts the names compared.
    """
    bad = missing(root, [requirements, "pyproject.toml"])
    if bad:
        return bad, 0
    req = _names(read(os.path.join(root, requirements)).split("\n"))
    block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", read(os.path.join(root, "pyproject.toml")),
                      re.S | re.M)
    if not block:
        return ["pyproject.toml has no dependencies list"], 0
    meta = _names(re.findall(r'"([^"]+)"', block.group(1)))
    if req != meta:
        bad.append("%s %s != pyproject dependencies %s"
                   % (requirements, sorted(req), sorted(meta)))
    return bad, len(req | meta)


# Matches `# --- MINING THROUGHPUT  (v1.4.0) --------------------` and friends.
# The modules use box-drawing rules of a few different characters (U+2500,
# U+2550, U+2501, and the dots U+00B7 and U+2022), written below as escapes
# because this package's source is ASCII.
#
# The class is built through re.escape because a literal "-" sitting between
# two other characters is a RANGE, not a hyphen: the same family of mistake as
# the `str.contains(..., regex=False)` fixes in the pipeline itself.
_RULE_CHARS = "".join(re.escape(c) for c in "\u2500\u2550\u2501=_\u00b7\u2022-")
_BANNER_RE = re.compile(
    rf"^#\s*[{_RULE_CHARS}]{{2,}}\s*(?P<title>.*?)\s*[{_RULE_CHARS}]{{2,}}\s*$"
)
_BARE_RULE_RE = re.compile(rf"^#\s*[{_RULE_CHARS}]{{4,}}\s*$")


def _banner_title(line: str) -> Optional[str]:
    """Section title if `line` is a section banner, else None.

    A banner must have an actual title, or an ASCII table drawn in a comment
    becomes a section: a separator row like `------  ----------------` matches
    the banner shape exactly and produced a group heading with that literal
    text. The instance this was written for was the version-history block above
    each `pipeline_version`, which moved to versions.md in 2026-09; the guard
    stays because a comment is free to draw a table at any time, and a UI that
    invents a section from one is worse than a bare dial.
    """
    match = _BANNER_RE.match(line.strip())
    if not match:
        return None
    title = match.group("title").strip()
    # Reject a "title" made of nothing but more rule characters.
    if not title or not re.search(r"[0-9A-Za-z\u0394]", title):
        return None
    return title


def _clean_comment(line: str) -> str:
    """A comment line with its `#` and one following space removed.

    Exactly ONE space, so the modules' hanging indents survive into the help
    text: several config blocks lay out a small table or a bulleted list under
    a field, and stripping the leading whitespace would flatten them.
    """
    body = line.lstrip()[1:]
    return body[1:] if body.startswith(" ") else body


def _trailing_comments(src: str) -> Dict[int, str]:
    """line number -> the inline `#` comment on that line, if any.

    Read through `tokenize` rather than by splitting on "#", because a default
    value is allowed to contain one.  This exists because several fields carry
    their whole description as a TRAILING comment and nothing else:

        preview_rows:      int = 20   # rows per table in the end-of-run preview
        request_timeout: int = 60   # seconds per HTTP call; a timeout is a soft failure

    Reading only the block ABOVE a field showed those as having no help at all,
    while the text was sitting on the same line.
    """
    out: Dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                # A comment that starts the line is a block comment, not a
                # trailing one; those are already handled by the walk upward.
                if src.split("\n")[tok.start[0] - 1][:tok.start[1]].strip():
                    out[tok.start[0]] = _clean_comment(tok.string).strip()
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return {}
    return out


def field_docs(path: str, class_name: str) -> Dict[str, Dict[str, str]]:
    """field name -> {"help", "section"} scraped from a module source.

    Walks backwards from each field definition collecting the comment block
    directly above it, stopping at the first blank line or section banner. The
    banner title, if there is one, becomes the field's group heading: the
    modules already organise their configs into labelled sections and there is
    no reason for the UI to invent its own taxonomy.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return {}

    lines = src.split("\n")
    trailing_comments = _trailing_comments(src)
    cls = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    if cls is None:
        return {}

    docs: Dict[str, Dict[str, str]] = {}
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue

        block: List[str] = []
        section = ""

        i = stmt.lineno - 2          # 0-indexed line directly above the field
        while i >= 0 and lines[i].strip() and lines[i].lstrip().startswith("#"):
            section = _banner_title(lines[i]) or ""
            if section or _BARE_RULE_RE.match(lines[i].strip()):
                break
            block.append(_clean_comment(lines[i]))
            i -= 1

        # If the field had no comment of its own, keep scanning up for the
        # section banner it lives under so it still gets grouped.
        while not section and i >= 0:
            line = lines[i].strip()
            if line.startswith("class ") or line.startswith("@dataclass"):
                break
            section = _banner_title(line) or ""
            i -= 1

        help_text = "\n".join(reversed(block)).strip()

        # A trailing comment on the field's own line. For most fields this is
        # the only description there is; where a block exists too it usually
        # carries the part the block leaves out ("0 = all 1.55 M asteroids"),
        # so it is appended rather than discarded, and skipped when the block
        # already says it.
        trailing = trailing_comments.get(stmt.lineno, "")
        if trailing and trailing not in help_text:
            help_text = (help_text + "\n" + trailing).strip() if help_text else trailing

        docs[stmt.target.id] = {
            "help": help_text,
            "section": section or "Other",
        }

    return docs


def missing_help(root, path, class_name, fields=None, skip=()):
    """Every field of `class_name` in `path` carries the help `field_docs` would show.

    `fields`, when given, is the names the class must declare in its own body
    (a dataclass's `dataclasses.fields`, say): one it does not declare is a
    finding, because an inherited field's help is read from the base class's
    source, not this one. Without it, every annotated field in the body is
    checked. Names in `skip` (paths, say, which a dashboard does not show as a
    dial) are not checked. A file that is missing or does not parse, or that
    has no such class, is a finding, where `field_docs` would answer {}.
    `checked` counts the fields checked.
    """
    full, rel = _resolve(root, path)
    if not os.path.exists(full):
        return missing(root, [path]), 0
    try:
        tree = ast.parse(read(full))
    except SyntaxError as exc:
        return ["%s does not parse: %s" % (rel, exc.msg)], 0
    if not any(isinstance(n, ast.ClassDef) and n.name == class_name for n in ast.walk(tree)):
        return ["%s defines no class %s" % (rel, class_name)], 0
    docs = field_docs(full, class_name)
    names = list(docs) if fields is None else list(fields)
    bad, n = [], 0
    for name in names:
        if name in skip:
            continue
        n += 1
        if name not in docs:
            bad.append("%s: %s declares no field %s" % (rel, class_name, name))
        elif not docs[name]["help"].strip():
            bad.append("%s: %s.%s has no help comment" % (rel, class_name, name))
    return bad, n
