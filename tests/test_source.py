# -*- coding: utf-8 -*-
"""samebytes.source: each check passes a clean file and fails each planted defect."""
import sys
import textwrap

from samebytes import source


def write(root, name, text, binary=False):
    """Write `text` (dedented) to root/name; bytes are written as given. Return name."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(text)
    else:
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return name


def test_docstrings(tmp_path):
    """Nested and async definitions count; a missing module docstring is named."""
    write(tmp_path, "good.py", '''
        """Module."""
        class A:
            """A."""
            def m(self):
                """M."""
                def inner():
                    """Inner."""
        async def f():
            """F."""
    ''')
    write(tmp_path, "bad.py", '''
        def f():
            def inner():
                """Inner."""
        async def g():
            pass
    ''')
    write(tmp_path, "broken.py", "def f(:\n")
    assert source.docstrings(str(tmp_path), ["good.py"]) == ([], 5)
    bad, n = source.docstrings(str(tmp_path), ["bad.py", "broken.py", "ghost.py"])
    assert n == 4
    assert bad[0] == "ghost.py is listed and is not on disk"
    assert bad[1:4] == ["bad.py has no module docstring",
                        "bad.py:1  f has no docstring", "bad.py:4  g has no docstring"]
    assert len(bad) == 5 and bad[4].startswith("broken.py: could not parse")


def test_non_ascii(tmp_path):
    """Lines holding a byte above 127 are named; a clean file passes."""
    write(tmp_path, "a.py", b"x = 1\n# caf\xc3\xa9\ny = 2\n# \xe2\x80\x94\n", binary=True)
    write(tmp_path, "b.ps1", b"Write-Host 'ok'\r\n", binary=True)
    assert source.non_ascii(str(tmp_path), ["b.ps1"]) == ([], 1)
    assert source.non_ascii(str(tmp_path), ["a.py"]) == (["a.py: non-ASCII on lines [2, 4]"], 1)


def test_printed_non_ascii(tmp_path):
    """Only literals inside print/say calls; cp1252-encodable characters still fail."""
    write(tmp_path, "a.py", '''
        """Docstring \u2192 keeps its arrow."""
        NOTES = "data \u00b1 kept"
        print("ok", "caf\u00e9")
        say("fine %s" % NOTES)
        warn("\u2014")
    ''')
    bad, n = source.printed_non_ascii(str(tmp_path), ["a.py"])
    assert n == 2 and bad == ["a.py:3  print(...) prints '\u00e9'"]
    bad, n = source.printed_non_ascii(str(tmp_path), ["a.py"], callers=("warn",))
    assert n == 1 and bad == ["a.py:5  warn(...) prints '\u2014'"]


def test_calls(tmp_path):
    """Every bare call to a named function is a finding; attribute calls are not."""
    write(tmp_path, "a.py", "print('x')\nlog.print('y')\nsay('z')\n")
    assert source.calls(str(tmp_path), ["a.py"]) == (["a.py:1  calls print()"], 1)


def test_is_stdlib():
    """Standard library, a third-party package, and this package itself."""
    assert source.is_stdlib("os") and source.is_stdlib("__future__")
    assert source.is_stdlib("json") and source.is_stdlib("sys")
    assert not source.is_stdlib("pytest") and not source.is_stdlib("samebytes")


def test_is_stdlib_without_stdlib_module_names(monkeypatch):
    """The Python 3.9 path answers the same for the same names, rather than skipping."""
    monkeypatch.delattr(sys, "stdlib_module_names", raising=False)
    assert source.is_stdlib("os") and source.is_stdlib("json") and source.is_stdlib("sys")
    assert source.is_stdlib("__future__") and source.is_stdlib("subprocess")
    assert not source.is_stdlib("pytest") and not source.is_stdlib("samebytes")


def test_imports(tmp_path):
    """Allowed at module level; lazy only inside a def; relative imports ignored."""
    write(tmp_path, "a.py", '''
        import os
        from . import sibling
        import psutil
        try:
            import numpy
        except ImportError:
            numpy = None
        def f():
            import pandas
            import requests
        class C:
            import pandas as pd
    ''')
    bad, n = source.imports(str(tmp_path), ["a.py"], allowed=["psutil"], lazy=["numpy", "pandas"])
    assert n == 6
    assert bad == ["a.py:5  imports numpy at module level", "a.py:10  imports requests"]
    assert source.imports(str(tmp_path), ["a.py"], allowed=["psutil", "numpy", "requests"],
                          lazy=["pandas"]) == ([], 6)


def test_quiet_import(tmp_path):
    """Silent passes; printing, writing a file, failing and env removal are each seen."""
    write(tmp_path, "quiet_pkg/__init__.py", '"""Q."""\nX = 1\n')
    write(tmp_path, "loud_pkg/__init__.py",
          '"""L."""\nimport os\nprint("hello")\nopen("made.txt", "w").close()\n')
    root = str(tmp_path)
    assert source.quiet_import(root, "import quiet_pkg") == ([], 1)
    bad, _ = source.quiet_import(root, "import loud_pkg")
    assert bad == ["'import loud_pkg' wrote to stdout: 'hello\\n'",
                   "'import loud_pkg' created ['made.txt'] in its working directory"]
    bad, _ = source.quiet_import(root, "import no_such_pkg")
    assert len(bad) == 1 and "exited 1" in bad[0] and "no_such_pkg" in bad[0]
    probe = "import os, sys; sys.exit(3 if os.environ.get('SB_PROBE') else 0)"
    import os
    os.environ["SB_PROBE"] = "1"
    try:
        assert source.quiet_import(root, probe, env={"SB_PROBE": None}) == ([], 1)
        assert "exited 3" in source.quiet_import(root, probe)[0][0]
    finally:
        del os.environ["SB_PROBE"]


def test_version_written_once(tmp_path):
    """The attr form passes; a typed version, a missing attr or __version__ fail."""
    write(tmp_path, "pyproject.toml", '''
        [project]
        name = "pkg"
        dynamic = ["version"]
        [tool.setuptools.dynamic]
        version = { attr = "pkg.__version__" }
    ''')
    write(tmp_path, "pkg/__init__.py", '"""P."""\n__version__ = "1.2.3"\n')
    assert source.version_written_once(str(tmp_path), "pkg") == ([], 1)
    write(tmp_path, "pyproject.toml", '[project]\nname = "pkg"\nversion = "1.2.3"\n')
    write(tmp_path, "pkg/__init__.py", '"""P."""\n')
    bad, _ = source.version_written_once(str(tmp_path), "pkg")
    assert bad == ['pyproject.toml: no dynamic = ["version"]',
                   'pyproject.toml: no version = { attr = "pkg.__version__" }',
                   "pyproject.toml: types a version string",
                   'pkg/__init__.py: no __version__ = "X.Y.Z"']


def test_requirements_match(tmp_path):
    """Names compared case- and separator-blind; versions, markers, URLs and comments ignored."""
    write(tmp_path, "pyproject.toml", '''
        [project]
        dependencies = [
            "numpy>=1.24",
            "Pandas>=2.0; python_version >= '3.9'",
            "samebytes @ git+https://github.com/loggger101/samebytes@v0.3.0",
        ]
    ''')
    write(tmp_path, "requirements.txt", '''
        # pins for a run
        numpy==2.1.0
        pandas==2.2.3
        samebytes @ git+https://github.com/loggger101/samebytes@v0.3.0
    ''')
    assert source.requirements_match(str(tmp_path)) == ([], 3)
    write(tmp_path, "requirements.txt", "numpy\nscipy\n")
    bad, n = source.requirements_match(str(tmp_path))
    assert n == 4 and bad == ["requirements.txt ['numpy', 'scipy'] != pyproject dependencies "
                              "['numpy', 'pandas', 'samebytes']"]


CONFIG = '''
    from dataclasses import dataclass

    @dataclass
    class Cfg:
        """A config."""
        # \u2500\u2500\u2500 MINING THROUGHPUT  (v1.4.0) \u2500\u2500\u2500\u2500\u2500\u2500
        # Rate of the rig.
        #   a hanging indent survives
        rate: float = 1.0   # kg per hour
        bare: int = 0

        hashy: str = "a#b"   # a default may hold a hash
        # ------  ----------
        # a table drawn above
        table: int = 1
        # \u2550\u2550 \u0394v BUDGET \u2550\u2550
        # Budget.
        dv: float = 2.0
        # ========
        ruled: int = 2
        # __ \u00b7 __
        dotted: int = 3


    class Other:
        """Not this one."""
        rate: int = 0   # wrong class
'''


def test_field_docs_reads_the_dashboard_rule(tmp_path):
    """Block above plus trailing, lines kept, banners are sections.

    A drawn table row, a bare rule and a banner with no title are not sections:
    the first and last stay in the help, the rule ends it.
    """
    path = str(tmp_path / write(tmp_path, "cfg.py", CONFIG))
    docs = source.field_docs(path, "Cfg")
    mining = "MINING THROUGHPUT  (v1.4.0)"
    assert docs == {
        "rate": {"help": "Rate of the rig.\n  a hanging indent survives\nkg per hour", "section": mining},
        "bare": {"help": "", "section": mining},
        "hashy": {"help": "a default may hold a hash", "section": mining},
        "table": {"help": "------  ----------\na table drawn above", "section": mining},
        "dv": {"help": "Budget.", "section": "\u0394v BUDGET"},
        "ruled": {"help": "", "section": "\u0394v BUDGET"},
        "dotted": {"help": "__ \u00b7 __", "section": "\u0394v BUDGET"},
    }
    assert source.field_docs(path, "Other") == {"rate": {"help": "wrong class", "section": "Other"}}


def test_field_docs_answers_empty_when_it_cannot_read(tmp_path):
    """No file, no parse, no class: {} each time (the dashboard shows no help, never crashes)."""
    broken = str(tmp_path / write(tmp_path, "broken.py", "class Cfg(:\n"))
    good = str(tmp_path / write(tmp_path, "cfg.py", CONFIG))
    assert source.field_docs(str(tmp_path / "gone.py"), "Cfg") == {}
    assert source.field_docs(broken, "Cfg") == {}
    assert source.field_docs(good, "Nope") == {}


def test_missing_help(tmp_path):
    """Bare fields named; `fields` catches an undeclared one; `skip` exempts; unreadable inputs are findings."""
    write(tmp_path, "cfg.py", CONFIG)
    bad, n = source.missing_help(str(tmp_path), "cfg.py", "Cfg")
    assert n == 7 and bad == ["cfg.py: Cfg.bare has no help comment",
                              "cfg.py: Cfg.ruled has no help comment"]
    bad, n = source.missing_help(str(tmp_path), "cfg.py", "Cfg", fields=["rate", "bare", "inherited"],
                                 skip=["bare"])
    assert n == 2 and bad == ["cfg.py: Cfg declares no field inherited"]
    write(tmp_path, "broken.py", "class Cfg(:\n")
    assert source.missing_help(str(tmp_path), "gone.py", "Cfg") == (
        ["gone.py is listed and is not on disk"], 0)
    assert source.missing_help(str(tmp_path), "broken.py", "Cfg")[0][0].startswith(
        "broken.py does not parse: ")
    assert source.missing_help(str(tmp_path), "cfg.py", "Nope") == (
        ["cfg.py defines no class Nope"], 0)
