# CLAUDE.md: working in this repo

samebytes is the modules in `samebytes/` (`tree.py`, `parity.py`,
`frames.py`, `provenance.py`, `hooks.py`, and the house-rule checks
`docs.py` and `source.py`), the sh hooks in `samebytes/hooks/`, and their
tests.
Most of the code is a trap with its reason beside it; README's "Why it looks
the way it does" is the list. Rules:

- **No dependencies, ASCII only, a docstring on every definition.**
  `tests/test_rules.py` enforces all three: module level imports the standard
  library only, and numpy and pandas are imported inside the functions that
  need them, so installing this never moves a consumer's pin.
- **The repository is always an argument** in `tree` and `hooks`; never
  default it to the module's directory (installed, that is site-packages).
- **Never change a parity probe or its grid in place.** A reference is only
  comparable with the probe set that recorded it;
  `test_probe_grids_are_pinned` records the calls the probes make. A new
  probe is a new key, and consumers re-record.
- **Never change `canonical_csv`'s text** (CRLF, column order, the dropped
  columns only) or `frame_hash`'s default width: consumers' committed hashes
  are hashes of it.
- **`read_exact` is for comparisons.** Never suggest it for a pipeline's own
  loader: the default parser is deterministic, and switching moves every
  number.
- **The hooks stay sh and LF**, and stay copies in each consumer
  (`.git/config` is shared across machines by a synced folder, so
  `core.hooksPath` must be relative). `hooks check` is what keeps the copies
  honest; a hook edit here means every consumer re-installs.
- **`docs` and `source` return `(findings, checked)`, and a listed file that
  is not on disk is a finding, never a skip.** Consumers print the count
  (economicspace's `verify_docs.py` checks 4, 5, 6, 10, 11 and 12 print these
  findings verbatim), so a finding's wording is output: change it in a
  release note, not in passing. A rule one consumer needs looser is a keyword
  argument (`one_h1=False`), never a weaker default.
- **A new trap gets a planted test.** Re-introduce the bug in a copy of the
  package and show its test fails before trusting the test's pass.
- **The version is written once**, `samebytes.__version__`; `pyproject.toml`
  reads it. A release bumps it, adds a CHANGELOG entry, and tags `vX.Y.Z`.
  Consumers pin the tag (economicspace: `requirements-verify.txt`, which its
  `modules/_runtime.py` guard reads and auto-installs from).
- The tree lives in OneDrive. `*-DESKTOP-*` files are sync-conflict copies:
  diff, then delete; never commit one. Never `git stash`.
