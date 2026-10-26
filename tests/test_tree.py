# -*- coding: utf-8 -*-
"""tree: the working tree against git's index, including the case git cannot see."""
import os

from conftest import backdate, commit_all, git
from samebytes import tree


def test_clean_tree_verifies(repo):
    """A freshly committed tree has no findings and counts every tracked file."""
    (repo / "a.txt").write_bytes(b"alpha\n")
    (repo / "b.py").write_bytes(b"print(1)\n")
    commit_all(repo)
    findings, n, skip = tree.verify_tree(str(repo))
    assert (findings, n, skip) == ([], 2, "")


def test_same_length_change_git_cannot_see_is_found(repo):
    """THE case: one byte changed, length and mtime restored, `git status` clean.

    This is the synced-folder stale read reproduced on purpose: git's stat cache
    trusts size and mtime and never re-reads, so only a content hash sees it.
    """
    f = repo / "data.txt"
    f.write_bytes(b"0123456789\n")
    past = backdate(f)
    commit_all(repo)
    git(repo, "status", "--porcelain")          # refresh the stat cache
    f.write_bytes(b"0123456780\n")              # same length
    os.utime(f, ns=(past, past))                # same mtime
    assert git(repo, "status", "--porcelain").strip() == "", "git should not see it"
    findings, n, skip = tree.verify_tree(str(repo))
    assert len(findings) == 1 and "data.txt" in findings[0] and "unchanged" in findings[0]


def test_an_edit_git_sees_is_not_a_finding(repo):
    """A modification git reports is somebody's edit, not a stale read."""
    (repo / "a.txt").write_bytes(b"alpha\n")
    commit_all(repo)
    (repo / "a.txt").write_bytes(b"alpha, edited\n")
    assert tree.verify_tree(str(repo))[0] == []


def test_missing_file_git_has_not_noticed_is_found(repo, monkeypatch):
    """A tracked file absent from disk while git reports nothing changed."""
    (repo / "a.txt").write_bytes(b"alpha\n")
    commit_all(repo)
    os.remove(repo / "a.txt")
    monkeypatch.setattr(tree, "changed_paths", lambda r: set())   # git "has not noticed"
    findings = tree.verify_tree(str(repo))[0]
    assert findings and "NOT on disk" in findings[0]


def test_crlf_file_is_hashed_through_gitattributes(repo):
    """A CRLF-pinned file matches its LF index blob only through `git hash-object`'s filters."""
    (repo / ".gitattributes").write_bytes(b"*.bat text eol=crlf\n")
    (repo / "run.bat").write_bytes(b"@echo off\r\necho hi\r\n")
    commit_all(repo)
    assert tree.verify_tree(str(repo))[0] == []


def test_path_with_a_space_round_trips(repo):
    """`--stdin-paths` reads one path per line, so a space needs no quoting."""
    (repo / "_START HERE.vbs").write_bytes(b"x\n")
    commit_all(repo)
    findings, n, _ = tree.verify_tree(str(repo))
    assert findings == [] and n == 1


def test_no_git_is_a_skip_not_a_pass(tmp_path, capsys):
    """A plain copy skips, says so, and the command line exits 2 rather than 0."""
    findings, n, skip = tree.verify_tree(str(tmp_path))
    assert findings == [] and n == 0 and skip
    assert tree.assert_tree(str(tmp_path)) is True
    assert "SKIPPED" in capsys.readouterr().out
    assert tree.main(str(tmp_path)) == 2


def test_main_exit_codes(repo):
    """0 when verified, 1 on a finding."""
    f = repo / "data.txt"
    f.write_bytes(b"aaaa\n")
    past = backdate(f)
    commit_all(repo)
    git(repo, "status", "--porcelain")
    assert tree.main(str(repo)) == 0
    f.write_bytes(b"aaab\n")
    os.utime(f, ns=(past, past))
    assert tree.main(str(repo)) == 1
