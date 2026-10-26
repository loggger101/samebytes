# -*- coding: utf-8 -*-
"""What produced this run?  Write it down when the run happens, because nothing
can work it out afterwards.

Moved from economicspace's `verify.py`.  Its baselines recorded the commit they
were taken on from the start, and recorded nothing about the interpreter; seven
weeks later its lock file named one machine's environment while every baseline
had been taken on the other, and finding out which had produced them took a
measurement in two environments.  Both records are here:

  git_state(repo, paths)   the commit, the branch, and which of `paths` differ
                           from it
  environment(packages)    the interpreter, the host, and each package's version

Neither raises.  A copied tree with no git, or a package that is not installed,
is a legitimate place to run; the answer there is None, which is recorded as
"could not tell" and is never read as "clean" or as a version.
"""
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence

# The packages economicspace's lock calls float-reaching: each can move the
# last bit of a result.
FLOAT_PACKAGES = ("numpy", "pandas", "pyarrow")


def git(repo: str, *args: str) -> Optional[str]:
    """One git command in `repo`, its stdout stripped; None if git cannot answer."""
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def dirty_paths(repo: str, paths: Sequence[str] = ()) -> Optional[List[str]]:
    """Tracked files under `paths` (all of them if empty) whose content differs
    from HEAD; None if git cannot say.

    `git diff`, NEVER `git status`.  A synced folder (Google Drive File Stream
    was the case met) can report a placeholder size when git stats a file just
    after checkout, and `status` then calls the file modified WITHOUT READING
    IT, while `diff` compares content and shows nothing.  A record built on
    `status` would condemn every run taken in that folder.

    Untracked files are not reported: a new file that nothing imports changes
    no result, and one that is imported shows up as the change to the file that
    imports it.
    """
    out = git(repo, "diff", "--name-only", "HEAD", "--", *paths)
    if out is None:
        return None
    return [line for line in out.splitlines() if line.strip()]


def git_state(repo: str, paths: Sequence[str] = ()) -> Dict[str, Any]:
    """{"sha", "branch", "dirty"} for `repo`, with `dirty` from `dirty_paths`.

    `dirty` is None when git could not answer and [] when it answered "clean".
    They are different facts and are kept apart on purpose: reading a missing
    answer as a clean one is how an unverifiable run comes to look like a good
    one.
    """
    return {"sha": git(repo, "rev-parse", "HEAD"),
            "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": dirty_paths(repo, paths)}


def package_version(name: str) -> Optional[str]:
    """The version of `name` this process would run; None if it is not installed.

    A module already imported answers with its own `__version__`: that is the
    code that ran, even if another copy is installed.  Otherwise the installed
    distribution's metadata answers, which needs no import (importing pandas to
    read its version costs about a second).
    """
    mod = sys.modules.get(name)
    if mod is not None and isinstance(getattr(mod, "__version__", None), str):
        return mod.__version__
    from importlib import metadata
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def environment(packages: Sequence[str] = FLOAT_PACKAGES) -> Dict[str, Any]:
    """The interpreter, the host, and each of `packages`' versions (None if absent).

    `system` and `machine` are recorded because the platform libm and numpy's
    SIMD kernels differ by both, which is what `parity` measures.  `host` is
    the machine's network name, so two machines with the same versions are
    still told apart.
    """
    env: Dict[str, Any] = {"python": platform.python_version(),
                           "system": platform.system(),
                           "machine": platform.machine(),
                           "host": platform.node()}
    for name in packages:
        env[name] = package_version(name)
    return env
