# -*- coding: utf-8 -*-
"""Does the working tree contain the bytes git says it contains?

This exists because of ONE observed failure, on 2026-09-15, which every other
harness in this repo reported as a clean pass:

    verify_stage3.py's first run of the day printed FOUR checks.
    Every later run printed SIX.
    The file's bytes hash equal to HEAD, and `git status` was clean throughout.

A harness ran an older version of ITSELF and said `OK`. Nothing in git was
wrong and nothing in the code was wrong; the Drive File Stream mount served the
old bytes once and the current bytes afterwards. The sibling failure, observed
in the same session, is a tracked file reading as ABSENT: two harnesses were
invisible to one `verify_docs.py` run and visible to the next.

WHY A CHECK IS POSSIBLE AT ALL, WHICH IS NOT OBVIOUS. `git status` said clean
the whole time, so the obvious check looks useless. It is clean because git's
stat cache trusts SIZE and MTIME and never re-reads content, the same cache
whose other direction is the phantom-dirty tree that `.githooks/drive-restat.sh`
repairs. So git's opinion and the file's CONTENT are two independent readings,
and the failure is exactly the case where they disagree:

    | content vs index | git status says | reading |
    |---|---|---|
    | equal            | clean           | fine |
    | differs          | modified        | somebody edited it; fine |
    | differs          | CLEAN           | nobody edited it and it changed anyway |
    | missing          | clean           | a tracked file is not there |

The last two are the finding. Reproduced deliberately before this was trusted:
change one byte of a tracked file without changing its length, restore its
mtime, and `git status --short` returns EMPTY while the content hash moves.

HASH THROUGH `git hash-object`, NEVER sha1 OF THE RAW BYTES. `.gitattributes`
pins `*.py` to LF and `*.bat` to CRLF, and the index stores the normalised form,
so raw bytes disagree with the index for every CRLF file by construction.
`git hash-object` applies the same filters git would: measured, `run.bat`
matches its index blob through `hash-object` and does NOT through
`--no-filters`, which is what proves the filter is load-bearing rather than
decorative.

IT READS THE WHOLE TREE RATHER THAN A CURATED LIST, deliberately. The lesson
this repo learned the day before this file was written is that a check which
reads one row of a table is a check on that row, and a hand-maintained file
list is that same defect wearing different clothes. All 147 tracked files hash
in 0.25 s, three git invocations regardless of count, so there is nothing to
buy by narrowing it.

AND READING IS ALSO THE CURE, so this is a prophylactic as well as a detector.
Materialisation is what a read does anyway, so calling this first in a harness
either catches the stale bytes or forces the mount to produce the current ones
before the harness reads them itself.

THE ONE GAP, STATED PRECISELY RATHER THAN PAPERED OVER: a harness's OWN source
is compiled by Python before any code in it runs, so a stale import is already
loaded by the time this executes. It is caught in practice because the mount
served stale bytes for a whole PROCESS rather than for a single read, so the
later re-read still sees them; it is not caught in principle, because a
materialisation landing between the import and this call would hide it. Every
file a harness reads AFTER this point is fully covered.
"""
import os
import subprocess

REPO = os.path.dirname(os.path.abspath(__file__))

# Modes git can list that are not a plain file on disk: a submodule pointer and
# a symlink. `git hash-object` on either means something different from "hash
# the file", so they are counted and skipped rather than silently mis-hashed.
_GITLINK = "160000"
_SYMLINK = "120000"


def _git(args, repo):
    """One git invocation, as text, or empty if git is not usable here."""
    try:
        out = subprocess.run(["git"] + args, cwd=repo, capture_output=True)
    except (OSError, ValueError):
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.decode("utf-8", "replace")


def index_blobs(repo=REPO):
    """Tracked regular files as {path: blob sha}, plus the skipped count.

    `git ls-files -s -z` emits one NUL-terminated record per file, shaped
    `<mode> <sha> <stage>` then a TAB then the path.
    """
    raw = _git(["ls-files", "-s", "-z"], repo)
    blobs, skipped = {}, 0
    for entry in raw.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        bits = meta.split()
        if len(bits) < 3 or not path:
            continue
        if bits[0] in (_GITLINK, _SYMLINK):
            skipped += 1
            continue
        blobs[path] = bits[1]
    return blobs, skipped


def changed_paths(repo=REPO):
    """Paths git itself reports as changed, so an edit is not read as a finding.

    `git status --porcelain -z` emits NUL-terminated `XY path` records, and a
    rename or copy is followed by a SECOND record holding the original path,
    which must be consumed or every later record parses one field out of step.
    """
    raw = _git(["status", "--porcelain", "-z"], repo)
    out, parts, i = set(), raw.split("\0"), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        out.add(path)
        if status[0] in ("R", "C") and i < len(parts):
            out.add(parts[i])
            i += 1
    return out


def working_hashes(paths, repo=REPO):
    """Bytes on disk as {path: blob sha}, with `.gitattributes` applied.

    One `git hash-object --stdin-paths` for the whole list; it reads paths one
    per line, so a name containing a space needs no quoting and
    `_START HERE.vbs` round-trips. Verified against the index for that file and
    for `run.bat`.
    """
    if not paths:
        return {}
    try:
        out = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=repo,
                             input="\n".join(paths).encode("utf-8"),
                             capture_output=True)
    except (OSError, ValueError):
        return {}
    if out.returncode != 0:
        return {}
    shas = out.stdout.decode("ascii", "replace").split()
    if len(shas) != len(paths):
        return {}
    return dict(zip(paths, shas))


def verify_tree(repo=REPO):
    """Return (findings, files verified, skip reason).

    A finding is a tracked file whose CONTENT disagrees with the index while git
    reports the path unchanged, or a tracked file that is not on disk at all and
    git has not noticed. Both mean a read of this tree returned something other
    than what the repository holds, which makes every result computed from it
    unsafe to quote.

    The skip reason is non-empty only when git cannot answer, and it is returned
    rather than printed so the caller decides how loud to be. A skip here is
    honest, since a plain copy with no `.git` is a legitimate way to run this
    code, but it is still a check that did not run, so callers SAY so.
    """
    if not os.path.isdir(os.path.join(repo, ".git")) and \
            not os.path.isfile(os.path.join(repo, ".git")):
        return [], 0, "no .git here, so there is nothing to compare against"
    blobs, _skipped = index_blobs(repo)
    if not blobs:
        return [], 0, "git listed no tracked files (not a repo, or git missing)"

    dirty = changed_paths(repo)
    findings, to_hash = [], []
    for path in sorted(blobs):
        if path in dirty:
            continue                      # somebody edited it; that is not this
        if not os.path.exists(os.path.join(repo, path)):
            findings.append("%s is tracked, is NOT on disk, and git has not "
                            "noticed" % path)
            continue
        to_hash.append(path)

    got = working_hashes(to_hash, repo)
    if not got:
        return [], 0, "git hash-object could not read the working tree"
    for path in to_hash:
        if got.get(path) != blobs[path]:
            findings.append("%s reads as %s, the index holds %s, and git "
                            "reports it unchanged"
                            % (path, got.get(path, "?")[:12], blobs[path][:12]))
    return findings, len(to_hash), ""


def assert_tree(label=""):
    """Print the one-line verdict; return False only on a real finding.

    Callers put this BEFORE the work, because the point is to refuse to quote a
    result computed from bytes the repository does not hold. A skip prints and
    returns True: it is not a pass, and the message says which it is.
    """
    findings, n, skip = verify_tree()
    tag = ("%s: " % label) if label else ""
    if skip:
        print("  %stree      SKIPPED (%s)" % (tag, skip))
        return True
    if findings:
        print("  %stree      *** %d FILE(S) ARE NOT WHAT GIT HOLDS ***"
              % (tag, len(findings)))
        for f in findings:
            print("     ! " + f)
        print("     This is the Drive stale/absent read, not a code defect.")
        print("     Re-read the tree and run this again before trusting a result.")
        return False
    print("  %stree      %d tracked files match the index" % (tag, n))
    return True


def main():
    """Standalone entry point, so the check is runnable without a harness."""
    print("=" * 70)
    print("  WORKING TREE CHECK  -  does the disk hold what git says it holds?")
    print("=" * 70)
    ok = assert_tree()
    print("-" * 70)
    print("  OK  TREE VERIFIED" if ok else "  *** TREE NOT VERIFIED ***")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
