# -*- coding: utf-8 -*-
"""House rules over the package source: ASCII, docstrings, no dependency at import, the CLI."""
import ast
import pathlib
import subprocess
import sys

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / "samebytes"
SOURCES = sorted(PKG.glob("*.py"))
HOOK_FILES = sorted((PKG / "hooks").iterdir())
STDLIB = set(getattr(sys, "stdlib_module_names", ())) or {
    "argparse", "hashlib", "json", "math", "os", "platform", "struct", "subprocess",
    "sys", "typing", "__future__", "multiprocessing", "io", "re", "importlib"}
LAZY = {"numpy", "pandas"}


def test_sources_found():
    """The rules below read real files, not an empty glob."""
    assert {p.name for p in SOURCES} >= {"__init__.py", "__main__.py", "tree.py",
                                         "parity.py", "frames.py", "hooks.py",
                                         "provenance.py"}
    assert {p.name for p in HOOK_FILES} == {"drive-restat.sh", "post-checkout",
                                            "post-merge", "post-rewrite"}


@pytest.mark.parametrize("path", SOURCES + HOOK_FILES, ids=lambda p: p.name)
def test_ascii_only(path):
    """Every byte is ASCII: Windows' cp1252 console crashes on printing anything else."""
    bad = [i for i, line in enumerate(path.read_bytes().splitlines(), 1)
           if any(b > 127 for b in line)]
    assert bad == [], f"{path.name}: non-ASCII on lines {bad}"


@pytest.mark.parametrize("path", HOOK_FILES, ids=lambda p: p.name)
def test_hooks_are_lf(path):
    """A CRLF `#!/bin/sh` fails as a bad interpreter; .gitattributes must keep these LF."""
    assert b"\r\n" not in path.read_bytes()


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_definition_has_a_docstring(path):
    """Modules, classes and functions all say what they are for."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = [n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and not ast.get_docstring(n)]
    assert ast.get_docstring(tree), f"{path.name} has no module docstring"
    assert missing == []


def _imports(node):
    """Top-level module names imported by `node`'s statements (relative imports excluded)."""
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name.split(".")[0], n
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            yield n.module.split(".")[0], n


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_dependency_at_import(path):
    """Module level imports the standard library only; numpy and pandas only inside functions.

    That is what lets the package declare no dependencies and never move a pin.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top = [name for stmt in tree.body for name, _ in _imports(stmt)
           if not isinstance(stmt, (ast.FunctionDef, ast.ClassDef))]
    assert [m for m in top if m not in STDLIB] == []
    everything = {name for name, _ in _imports(tree)}
    assert everything - STDLIB - LAZY == set()


def test_imports_without_numpy_or_pandas():
    """A fresh interpreter imports every module with numpy and pandas blocked."""
    code = ("import sys; sys.modules['numpy'] = None; sys.modules['pandas'] = None\n"
            "import samebytes, samebytes.tree, samebytes.parity, samebytes.frames, "
            "samebytes.hooks, samebytes.provenance, samebytes.__main__\nprint('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(PKG.parent))
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_cli_version_and_help():
    """`python -m samebytes --version` names the package version; no argument prints usage."""
    from samebytes import __version__
    r = subprocess.run([sys.executable, "-m", "samebytes", "--version"],
                       capture_output=True, text=True, cwd=str(PKG.parent))
    assert r.returncode == 0 and r.stdout.strip() == "samebytes " + __version__
    r = subprocess.run([sys.executable, "-m", "samebytes"], capture_output=True, text=True,
                       cwd=str(PKG.parent))
    assert r.returncode == 2 and "tree" in r.stdout
