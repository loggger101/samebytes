# -*- coding: utf-8 -*-
"""A throwaway git repository per test, with an identity and no autocrlf."""
import os
import subprocess

import pytest


def git(repo, *args, check=True):
    """Run git in `repo` and return its stdout as text."""
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True)
    if check and r.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), r.stderr.decode()))
    return r.stdout.decode("utf-8", "replace")


@pytest.fixture
def repo(tmp_path):
    """An initialised repository: identity set, autocrlf off, nothing committed."""
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.name", "test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "commit.gpgsign", "false")
    return path


def commit_all(repo, message="c"):
    """Stage everything and commit it."""
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def backdate(path, seconds=1000):
    """Set a file's mtime well into the past, so git's racy-clean rule cannot re-hash it."""
    st = os.stat(path)
    past = st.st_mtime_ns - seconds * 10 ** 9
    os.utime(path, ns=(past, past))
    return past
