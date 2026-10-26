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

Like `samebytes.docs`, every check takes the repository root and paths relative
to it (absolute paths work too) and returns `(findings, checked)`: one-line
findings, empty when clean, and how many things were read. A listed file that
is not on disk is a finding. Nothing here imports beyond the standard library.
"""
import ast
import importlib.util
import os
import re
import subprocess
import sys
import sysconfig
import tempfile

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
