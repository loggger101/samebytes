# Changelog

## v0.4.0 (2026-10-26)

Two more docs checks, the last of economicspace's `verify_docs.py` that need
no project knowledge. Nothing v0.3.0 printed, hashed, probed or installed
changes.

- **`docs.pairs(root, answers, rules, register_header=None)`**: no line of the
  rules file shares three distinctive numbers with a line of an answer file,
  unless a register table (the rows under a header line equal to
  `register_header`) lists them. The answers are not paired with each other.
  One finding per set of shared numbers, naming both lines; `checked` counts
  every pair. Moved from economicspace's check 12.
- **`docs.transfer(root, before, after)`**: every distinctive number in
  `before` still appears somewhere in the `after` files. The audit for a
  reorganisation, where a line diff cannot tell a dropped measurement from a
  reflow. Findings are the lost number and its source line, sorted;
  `checked` counts the numbers. Moved from economicspace's check 10.
- **`docs.figures(line)`**, the numbers `pairs` reads, and the four patterns
  `PAIR_NUMBER`, `PAIR_YEAR`, `TRANSFER_NUMBER` and `TRANSFER_YEAR`, moved
  verbatim. The two checks count "distinctive" differently, as they did
  where they came from. A known miss is carried, not fixed: a comma straight
  after a thousands figure stays on `pairs`' token.

Proved: 6 new tests, 126 in all. 12 defects were planted in a copy of the new
code (versions, link targets and years not stripped, register rows read as a
side, the register ignored, a two-number threshold, no dedupe, a missing file
skipped by either check, only the first `after` file read, findings unsorted)
and each failed its test. On economicspace, `transfer` printed byte-identical
output to the old check on five audits (up to 2,751 numbers), and `pairs` found
the same pairs and numbers on the live docs and on a copy with planted ones.

## v0.3.0 (2026-10-26)

Two new modules, the house rules economicspace, spacecost, spacevalue,
AsteroidCatalog, quietqueue, quietlaunch and samebytes had each written for
themselves. Nothing v0.2.0 printed, hashed, probed or installed changes.

- **`docs`**: `links` (every relative link names a file that exists and every
  `#anchor` a heading; resolved from the linking file, checked in whichever
  markdown file it lands in, `%20` decoded), `structure` (balanced fences, no
  ragged table, no heading-level jump, no repeated h1/h2, exactly one h1
  unless `one_h1=False`), `dashes` (no em- or en-dash and no line opening with
  a bare comma; `prose_only` sources in comments and docstrings only) and
  `slugs`, GitHub's anchor rule with its `-1` suffixes. Moved from
  economicspace's `verify_docs.py` checks 4, 5 and 6, which now call them;
  three fixes on the way: a heading inside a code fence no longer makes an
  anchor, a table that ends the file is checked, and an anchor into an
  unlisted markdown file is checked.
- **`source`**: `docstrings` (nested and async definitions count; check 11),
  `non_ascii`, `printed_non_ascii` (ASCII, not "encodable in cp1252", which
  spacecost's copy accepted), `calls`, `imports` (module level the standard
  library and `allowed` only, `lazy` only inside functions), `is_stdlib`
  (answers on Python 3.9 instead of skipping), `quiet_import` (a fresh
  interpreter exits 0, prints nothing and creates no file),
  `version_written_once` and `requirements_match`.
- Every check returns `(findings, checked)`, and a listed file not on disk is
  a finding.
- `tests/test_rules.py` now runs samebytes' own rules through these, and adds
  its docs, its printed strings and its version.

Proved: 30 new tests, 120 in all. On economicspace the moved checks read what
the old ones read (534 anchors, 10 docs, 41 files, 753 definitions) with the
same verdict. 22 defects were planted in a copy of the two modules (the
underscore stripped from anchors, fenced headings read, links resolved from
the root, `%20` not decoded, anchors in other files unchecked, a missing file
skipped, the last table unchecked, zero h1s passing, `one_h1` ignored,
`prose_only` reading the whole file, the orphan comma unchecked, nested and
async definitions exempt, cp1252 accepted, the 3.9 fallback answering yes, a
lazy import allowed at module level, a guarded import exempt, created files
unseen, an `env` removal ignored, a typed version accepted, requirement names
compared case-sensitively, a parse error swallowed), and each failed its test.

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
