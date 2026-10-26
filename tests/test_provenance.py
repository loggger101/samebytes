# -*- coding: utf-8 -*-
"""provenance: "could not tell" is never recorded as "clean", and content decides dirty."""
import os
import sys
import types

from samebytes import provenance

from conftest import backdate, commit_all, git


def _seed(repo):
    """Two tracked files in two directories, committed."""
    (repo / "model").mkdir()
    (repo / "model" / "calc.py").write_text("x = 1\n")
    (repo / "README").write_text("hello\n")
    commit_all(repo)


def test_clean_repo_is_an_empty_list_not_none(repo):
    """A clean answer is [] with the commit and branch named."""
    _seed(repo)
    state = provenance.git_state(str(repo))
    assert state["dirty"] == []
    assert state["sha"] == git(repo, "rev-parse", "HEAD").strip()
    assert state["branch"] == git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def test_a_content_change_is_dirty_and_paths_filter_it(repo):
    """An edit under `paths` is named; one outside them is not."""
    _seed(repo)
    (repo / "model" / "calc.py").write_text("x = 2\n")
    (repo / "README").write_text("changed\n")
    assert provenance.dirty_paths(str(repo), ["model"]) == ["model/calc.py"]
    assert sorted(provenance.dirty_paths(str(repo))) == ["README", "model/calc.py"]
    assert provenance.git_state(str(repo), ["model"])["dirty"] == ["model/calc.py"]


def test_a_touch_without_a_content_change_is_clean(repo):
    """Content decides, not the stat: a new mtime on the same bytes is clean."""
    _seed(repo)
    p = repo / "model" / "calc.py"
    backdate(p, 5000)
    os.utime(p, None)
    assert provenance.dirty_paths(str(repo)) == []


def test_untracked_files_are_not_dirty(repo):
    """A new file nothing tracks is not reported."""
    _seed(repo)
    (repo / "model" / "scratch.py").write_text("y = 1\n")
    assert provenance.dirty_paths(str(repo), ["model"]) == []


def test_no_git_is_none_never_clean(tmp_path):
    """Outside a repository every answer is None, so it cannot read as clean."""
    state = provenance.git_state(str(tmp_path))
    assert state == {"sha": None, "branch": None, "dirty": None}


def test_environment_names_the_interpreter_and_marks_absence():
    """Every key is present; a package that is not installed is None."""
    env = provenance.environment(("pip", "no-such-package-samebytes"))
    assert env["python"].count(".") == 2
    assert env["system"] and env["machine"] and "host" in env
    assert env["pip"] and env["no-such-package-samebytes"] is None
    assert set(provenance.environment()) >= {"numpy", "pandas", "pyarrow"}


def test_an_imported_module_answers_with_the_code_that_ran(monkeypatch):
    """A module already imported reports its own __version__, not the metadata's."""
    fake = types.ModuleType("pip")
    fake.__version__ = "0.0.shadow"
    monkeypatch.setitem(sys.modules, "pip", fake)
    assert provenance.package_version("pip") == "0.0.shadow"
