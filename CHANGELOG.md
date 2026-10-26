# Changelog

## v0.2.0 (2026-10-26)

Three additions. Nothing that v0.1.0 printed, hashed, probed or installed
changes: every v0.1.0 test passes unchanged, the probe set and its grids are
the same, and `parity` without `--lock` prints byte-identical output.

- **`frames.shared_hash(a, b, drop)` and `frames.shared_columns`.** A release
  that adds an output column cannot be checked by hashing the whole frame
  against the build before it. economicspace once reported four cells as
  different on a configuration identical on 142 of 142 shared columns.
  `shared_hash` hashes both frames over the columns both carry, in A's order,
  and returns the column list so the set can be named. `column_diff` now takes
  its shared set from `shared_columns`, with the same result.
- **`provenance`**, moved from economicspace's `verify.py`:
  - `git_state(repo, paths)` gives the commit, the branch, and the tracked
    files under `paths` whose content differs from HEAD (`git diff`, never
    `git status`).
  - `environment(packages)` gives the interpreter, system, machine, host and
    each package's version.
  - "Could not tell" is `None` and never reads as clean.
  - A module already imported reports its own `__version__`; otherwise
    `importlib.metadata` answers without importing the package.
- **`parity --lock FILE`** (repeatable) compares each installed distribution
  with its `name==version` pin.
  - Names are normalised as PEP 503 does, and versions are compared as exact
    strings.
  - Every other line (a range, a URL, `-r`, an environment marker) is printed
    `NOT CHECKED` and fails the lock check.
  - The exit code is the probes' when they did not all match, else the lock's.
  - The lock is checked even when the reference is missing (exit 2).
  - `--lock` with `--record` is an argument error.

Proved: 22 new tests, 90 in all. Twelve defects were planted in a copy (whole B
hashed, provenance kept, B's own order, `git status` for dirty, no git read as
clean, metadata ignoring the imported module, unreadable lock lines dropped or
passed, names not normalised, tab comments, the lock skipped without a
reference, the lock's exit code ignored), and each failed its test, as do v0.1.0's 16.

Also in this release, documentation only:

- README: a Develop section (running the tests, what they need, how a release
  is made), a Licence section, and the `--no-config` / `--require-config`
  flags of `hooks`.
- Docstrings in `tree`, `frames` and `parity` say plainly what they said with
  filler, and a few paragraphs broken by the move out of economicspace are
  rewrapped.
- `pyproject.toml`: a plainer description, two keywords, Changelog and Issues
  links.

## v0.1.0 (2026-10-25)

First release: economicspace's `tree_check.py`, `platform_check.py` and
`.githooks/` (as of economicspace 087aef5), with the comparison functions of
its `verify.py`, made into a package. The commits that built the three moved
files are replayed at the start of this repository's history, limited to
those files; `frames.py` starts from a verbatim AST extraction so that its
first diff is the whole of what changed.

What changed in moving it:

- **The repository is an argument.** `tree_check.py` checked the directory it
  sat in; installed, that is site-packages, so `verify_tree(repo)` and
  `assert_tree(repo, label)` take it and nothing defaults it except the
  command line (the current directory).
- **parity takes its reference path and its advice.** The reference file and
  the four project phrases the report prints (`HINTS`: the re-baseline
  command, the record command, where the dtype traps and the hashes are
  written down) are arguments. The probes and their argument grids are
  unchanged, so a reference recorded by economicspace stays comparable.
  Proved: with economicspace's hints, `report` prints byte-identical output to
  `platform_check.py` on all-match, libm, pandas, hard-defect and combined
  references, and `collect()` is identical.
- **frames is verify.py's comparison as public functions**:
  `comparable`, `canonical_csv`, `frame_hash`, `column_diff`, `blanks`,
  `read_exact`, `float_hash`. The provenance columns are a `drop=` argument.
  Proved against verify.py on 108 baseline cells: the same frame, hash,
  canonical CSV and column diff for every one.
- **One behavioural difference: `blanks` accepts `pd.NA`.** verify.py's
  version raised "boolean value of NA is ambiguous" on the nullable `string`
  dtype; it never met one. On every input verify.py accepted, the results are
  the same.
- **`read_exact` refuses a `float_precision` argument** rather than obeying
  it, and passes every other `read_csv` argument through.
- **hooks**: `install` copies the sh hooks into a repository and sets
  `core.hooksPath .githooks`; `check` compares the copies byte for byte and
  asks git for the `eol=lf` pin and the executable bit. The hook's header now
  names samebytes instead of economicspace's CLAUDE.md.
- `python -m samebytes tree | parity | hooks install/check`.

Tests: the stale same-length read git cannot see, the absent file, CRLF
through `.gitattributes`, the skip that must not pass; each frames rule; the
parity buckets and the pinned probe grids; every hooks finding and the hook
itself leaving a real edit alone. Sixteen of the bugs behind them are planted
in a copy of the package and shown to fail their test.
