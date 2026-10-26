# -*- coding: utf-8 -*-
"""Put the stat-cache repair hook into a repository, and say when a copy drifted.

The hook is `hooks/drive-restat.sh` in this package, a dependency-free sh
script (its header says what it repairs), run by three one-line git hooks:
post-checkout, post-merge and post-rewrite.  It stays sh, not Python, because a
hook runs after every checkout and merge: one that cannot find an interpreter
fails silently, and the phantom-dirty tree it exists to prevent comes back and
blocks the next merge.

A repository gets COPIES, not a path into site-packages.  `core.hooksPath`
lives in `.git/config`, which a synced folder carries to the other machine,
where an absolute site-packages path names nothing; `.githooks` relative to
the work tree means the same on both.  Copies can drift, so `check` compares
them byte for byte with the packaged originals.

Two things make a copy silently useless, and `check` reports both:
  - CRLF line endings: `#!/bin/sh` then fails as "bad interpreter".  The
    repository's .gitattributes must pin `.githooks/* text eol=lf`, or a clone
    on Windows (core.autocrlf true) checks the hooks out with CRLF.
  - a missing executable bit in git's index, on a host that honours it.
"""
import os
import subprocess

HOOK_DIR = ".githooks"
HOOKS = ("drive-restat.sh", "post-checkout", "post-merge", "post-rewrite")


def packaged_dir() -> str:
    """The directory holding this package's copies of the hooks."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks")


def _packaged(name: str) -> bytes:
    """A packaged hook's bytes, LF whatever the installer did to them."""
    with open(os.path.join(packaged_dir(), name), "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n")


def _git(repo: str, *args: str) -> str:
    """One git command in `repo`; its stdout, or None if git failed."""
    try:
        r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    except (OSError, ValueError):
        return None
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else None


def install(repo: str, set_config: bool = True) -> list:
    """Copy the hooks into `<repo>/.githooks` (LF, mode 755); return what changed.

    Sets `core.hooksPath .githooks` unless `set_config` is False.  Nothing is
    staged: commit the files with `git add --chmod=+x .githooks/*` so the
    executable bit reaches hosts that honour it.
    """
    dest = os.path.join(repo, HOOK_DIR)
    os.makedirs(dest, exist_ok=True)
    changed = []
    for name in HOOKS:
        want = _packaged(name)
        path = os.path.join(dest, name)
        try:
            with open(path, "rb") as fh:
                have = fh.read()
        except OSError:
            have = None
        if have != want:
            with open(path, "wb") as fh:
                fh.write(want)
            changed.append(os.path.join(HOOK_DIR, name))
        os.chmod(path, 0o755)
    if set_config:
        _git(repo, "config", "core.hooksPath", HOOK_DIR)
    return changed


def check(repo: str, require_config: bool = False) -> list:
    """Findings, empty when every copy in `<repo>/.githooks` is the packaged one.

    Compares bytes, and also asks git whether each copy is pinned to LF and
    tracked executable.  `require_config` adds a finding when
    `core.hooksPath` is not `.githooks`; leave it off on a fresh clone, such as
    CI's, where nobody has opted in.
    """
    findings = []
    for name in HOOKS:
        rel = HOOK_DIR + "/" + name
        path = os.path.join(repo, HOOK_DIR, name)
        try:
            with open(path, "rb") as fh:
                have = fh.read()
        except OSError:
            findings.append("%s is missing" % rel)
            continue
        if b"\r\n" in have:
            findings.append("%s has CRLF line endings; sh will refuse it" % rel)
        if have.replace(b"\r\n", b"\n") != _packaged(name):
            findings.append("%s differs from the packaged copy" % rel)
        eol = _git(repo, "check-attr", "eol", "--", rel)
        if eol is not None and not eol.endswith(": lf"):
            findings.append("%s is not pinned `eol=lf` in .gitattributes (%s)"
                            % (rel, eol.rsplit(": ", 1)[-1]))
        mode = _git(repo, "ls-files", "-s", "--", rel)
        if mode and not mode.startswith("100755"):
            findings.append("%s is tracked without the executable bit (%s)"
                            % (rel, mode.split()[0]))
    if require_config:
        got = _git(repo, "config", "--get", "core.hooksPath")
        if got != HOOK_DIR:
            findings.append("core.hooksPath is %r, not %r" % (got, HOOK_DIR))
    return findings
