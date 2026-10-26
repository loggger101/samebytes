# Changelog

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
