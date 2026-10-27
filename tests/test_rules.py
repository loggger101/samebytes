# -*- coding: utf-8 -*-
"""House rules over the package source: ASCII, docstrings, no dependency at import, the CLI.

The rules run through `samebytes.docs` and `samebytes.source`, the same checks
the consumers' tests call; `test_docs.py` and `test_source.py` plant a defect
for each, so passing here is not the checker vouching for itself.
"""
import pathlib
import subprocess
import sys

import pytest

from samebytes import docs, source

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "samebytes"
SOURCES = sorted(PKG.glob("*.py"))
HOOK_FILES = sorted((PKG / "hooks").iterdir())
DOCS = ["README.md", "CHANGELOG.md", "CLAUDE.md"]
LAZY = {"numpy", "pandas"}


def test_sources_found():
    """The rules below read real files, not an empty glob."""
    assert {p.name for p in SOURCES} >= {"__init__.py", "__main__.py", "tree.py",
                                         "parity.py", "frames.py", "hooks.py",
                                         "provenance.py", "docs.py", "source.py"}
    assert {p.name for p in HOOK_FILES} == {"drive-restat.sh", "post-checkout",
                                            "post-merge", "post-rewrite"}


@pytest.mark.parametrize("path", SOURCES + HOOK_FILES, ids=lambda p: p.name)
def test_ascii_only(path):
    """Every byte is ASCII: Windows' cp1252 console crashes on printing anything else."""
    assert source.non_ascii(str(ROOT), [str(path)]) == ([], 1)


@pytest.mark.parametrize("path", HOOK_FILES, ids=lambda p: p.name)
def test_hooks_are_lf(path):
    """A CRLF `#!/bin/sh` fails as a bad interpreter; .gitattributes must keep these LF."""
    assert b"\r\n" not in path.read_bytes()


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_definition_has_a_docstring(path):
    """Modules, classes and functions all say what they are for."""
    bad, n = source.docstrings(str(ROOT), [str(path)])
    assert bad == [] and n >= 1


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_dependency_at_import(path):
    """Module level imports the standard library only; numpy and pandas only inside functions.

    That is what lets the package declare no dependencies and never move a pin.
    """
    assert source.imports(str(ROOT), [str(path)], lazy=LAZY)[0] == []


def test_the_import_rule_read_imports():
    """The package as a whole has imports to check, including the lazy ones."""
    assert source.imports(str(ROOT), [str(p) for p in SOURCES])[1] > 20
    assert source.imports(str(ROOT), [str(p) for p in SOURCES])[0] != []


def test_docs_hold_together():
    """README, CHANGELOG and CLAUDE.md: links resolve, structure is sound, no dashes."""
    for check in (docs.links, docs.structure, docs.dashes):
        assert check(str(ROOT), DOCS)[0] == []
    assert docs.structure(str(ROOT), DOCS)[1] == len(DOCS)


def test_printed_strings_are_ascii():
    """Belt and braces under test_ascii_only: what the CLI prints is ASCII."""
    bad, n = source.printed_non_ascii(str(ROOT), [str(p) for p in SOURCES])
    assert bad == [] and n > 0


def test_version_is_written_once():
    """pyproject reads `samebytes.__version__`; no second copy to forget."""
    assert source.version_written_once(str(ROOT), "samebytes") == ([], 1)


def test_readme_installs_this_version():
    """README's install line pins the release it describes (it named v0.3.0 through v0.4.0)."""
    from samebytes import __version__
    files = ["README.md", "CLAUDE.md"]
    assert docs.pins(str(ROOT), files, "loggger101", packages=["samebytes"])[0] == []
    assert list(docs.pin_copies(str(ROOT), files, "loggger101")["samebytes"]) == ["v" + __version__]


def test_imports_without_numpy_or_pandas():
    """A fresh interpreter imports every module with numpy and pandas blocked."""
    code = ("import sys; sys.modules['numpy'] = None; sys.modules['pandas'] = None\n"
            "import samebytes, samebytes.tree, samebytes.parity, samebytes.frames, "
            "samebytes.hooks, samebytes.provenance, samebytes.docs, samebytes.source, "
            "samebytes.__main__\nprint('ok')")
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
