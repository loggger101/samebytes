# -*- coding: utf-8 -*-
"""hooks: install, the drift check and each silent failure it reports, and the hook itself."""
import os
import shutil
import subprocess
import sys

import pytest

from conftest import commit_all, git
from samebytes import hooks


def _installed_and_committed(repo):
    """Install, pin LF, commit with the executable bit: the state `check` calls clean."""
    hooks.install(str(repo))
    (repo / ".gitattributes").write_bytes(b".githooks/*  text eol=lf\n")
    git(repo, "add", ".gitattributes")
    git(repo, "add", "--chmod=+x", *[".githooks/" + h for h in hooks.HOOKS])
    git(repo, "commit", "-q", "-m", "hooks")


def test_install_writes_lf_copies_and_sets_hookspath(repo):
    """Four files, LF, the packaged bytes; core.hooksPath relative; a second install is a no-op."""
    changed = hooks.install(str(repo))
    assert sorted(changed) == sorted(os.path.join(".githooks", h) for h in hooks.HOOKS)
    for h in hooks.HOOKS:
        data = (repo / ".githooks" / h).read_bytes()
        assert b"\r\n" not in data and data.startswith(b"#!/bin/sh")
    assert git(repo, "config", "--get", "core.hooksPath").strip() == ".githooks"
    assert hooks.install(str(repo)) == []


def test_install_without_config(repo):
    """--no-config leaves core.hooksPath alone."""
    hooks.install(str(repo), set_config=False)
    assert git(repo, "config", "--get", "core.hooksPath", check=False).strip() == ""


def test_check_is_clean_on_a_proper_install(repo):
    """Installed, pinned and committed executable: no findings, with or without the config."""
    _installed_and_committed(repo)
    assert hooks.check(str(repo)) == []
    assert hooks.check(str(repo), require_config=True) == []


def test_check_finds_drift(repo):
    """One changed byte in a copy is drift."""
    _installed_and_committed(repo)
    p = repo / ".githooks" / "drive-restat.sh"
    p.write_bytes(p.read_bytes().replace(b"Repair", b"Rapair", 1))
    assert any("differs" in f for f in hooks.check(str(repo)))


def test_check_finds_crlf(repo):
    """A CRLF copy is reported even though its text is otherwise identical."""
    _installed_and_committed(repo)
    p = repo / ".githooks" / "post-merge"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    found = hooks.check(str(repo))
    assert any("CRLF" in f for f in found) and not any("differs" in f for f in found)


def test_check_finds_a_missing_eol_pin(repo):
    """Without `.githooks/* text eol=lf` a Windows clone would check the hooks out CRLF."""
    hooks.install(str(repo))
    git(repo, "add", "--chmod=+x", *[".githooks/" + h for h in hooks.HOOKS])
    git(repo, "commit", "-q", "-m", "hooks")
    assert any("not pinned" in f for f in hooks.check(str(repo)))


def test_check_finds_a_missing_executable_bit(repo):
    """Tracked 100644, the hook does not run on a host that honours the bit."""
    hooks.install(str(repo))
    (repo / ".gitattributes").write_bytes(b".githooks/*  text eol=lf\n")
    commit_all(repo)
    git(repo, "update-index", "--chmod=-x", ".githooks/post-merge")
    assert any("executable" in f for f in hooks.check(str(repo)))


def test_check_finds_missing_files_and_config(repo):
    """Nothing installed: every file missing, and the config when it is required."""
    found = hooks.check(str(repo), require_config=True)
    assert sum("missing" in f for f in found) == len(hooks.HOOKS)
    assert any("core.hooksPath" in f for f in found)


def _sh():
    """An sh to run the hook with, or None."""
    sh = shutil.which("sh")
    if sh is None and sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
            cand = os.path.join(base, "Git", "bin", "sh.exe")
            if os.path.exists(cand):
                return cand
    return sh


@pytest.mark.skipif(_sh() is None, reason="no sh on this host")
def test_restat_leaves_a_real_edit_alone(repo):
    """The repair touches only entries whose content already matches the index."""
    (repo / "a.txt").write_bytes(b"alpha\n")
    commit_all(repo)
    hooks.install(str(repo))
    (repo / "a.txt").write_bytes(b"alpha, really edited\n")
    r = subprocess.run([_sh(), os.path.join(".githooks", "drive-restat.sh")],
                       cwd=str(repo), capture_output=True)
    assert r.returncode == 0, r.stderr
    assert " M a.txt" in git(repo, "status", "--porcelain")
    assert git(repo, "diff", "--cached", "--name-only").strip() == ""
