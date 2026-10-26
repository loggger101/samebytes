# samebytes

[![tests](https://github.com/loggger101/samebytes/actions/workflows/tests.yml/badge.svg)](https://github.com/loggger101/samebytes/actions/workflows/tests.yml)

Are these the same bytes? Three places that question gets answered wrongly
without anything raising, and a check for each:

- **`tree`**: does the working tree hold the bytes git says it holds? In a
  synced folder (OneDrive, Google Drive) it can serve stale or absent bytes
  while `git status` stays clean, because git's stat cache trusts size and
  mtime and never re-reads content. `tree` hashes the whole tree through
  `git hash-object` and reports every file whose content disagrees with the
  index while git calls it unchanged.
- **`parity`**: can this host reproduce numbers committed elsewhere, bit for
  bit? It records a reference of libm, numpy, CSV, pandas-dtype and
  process-spawn probes on one host, and on another says which differ and what
  that means: a defect, a host property, or a library version.
- **`frames`**: are two runs of a pandas pipeline the same? A hash over a
  canonical CSV is the authority and a column diff is the diagnostic, with the
  rules that stop a correct comparison from reporting failures that do not
  exist (below).

plus **`provenance`**, which writes down what produced a run (the commit,
which tracked files differed from it, the interpreter and package versions)
when it happens, because nothing can work it out afterwards; and **`hooks`**,
a dependency-free sh git hook that repairs git's stat cache after a synced
folder reports a placeholder file size, which otherwise leaves the tree
permanently "modified" and makes `git merge --ff-only` refuse.

Python 3.9 or later. **No dependencies**: numpy and pandas are imported only by
the functions that need them, so installing samebytes can never move a version
your project pins. CI runs Windows, Linux and macOS.

Extracted from [economicspace](https://github.com/loggger101/economicspace),
a pipeline whose every release is argued from bit-identical output; this
repository carries the history of the files it came from.

## Install

```bash
pip install "samebytes @ git+https://github.com/loggger101/samebytes@v0.2.0"
```

## Use

**Before a harness reads anything**, check the tree it is about to read:

```python
from samebytes import tree

if not tree.assert_tree(REPO):          # prints one line; False on a finding
    raise SystemExit(1)
```

```bash
python -m samebytes tree [REPO]         # 0 verified, 1 a finding, 2 skipped (no git)
```

A skip (a plain copy with no `.git`) prints `SKIPPED` and is never reported as
a pass.

**Comparing two runs**:

```python
from samebytes import frames

PROV = ("pipeline_version", "catalog_date")        # columns that may differ
h = frames.frame_hash(df, drop=PROV)               # 16 hex digits, CRLF text
old = frames.read_exact("baseline/cell.csv")       # float_precision="round_trip"
same, compared, differing = frames.column_diff(df, old, drop=PROV)
```

Print both. When they disagree the hash is right and the comparator is
broken.

When one run carries a column the other does not (a release that adds an
output), the whole-frame hash differs by construction. Hash the columns both
carry, and name them:

```python
ha, hb, cols = frames.shared_hash(df, old, drop=PROV)  # both in df's column order
shared, only_new, only_old = frames.shared_columns(df, old, drop=PROV)
```

**Recording what produced a run**, at the time:

```python
from samebytes import provenance

meta = {"git": provenance.git_state(REPO, paths=["src"]),  # sha, branch, dirty
        "environment": provenance.environment()}          # python, host, numpy, pandas, pyarrow
```

`dirty` lists the tracked files under `paths` whose content differs from HEAD
(`git diff`, never `git status`). It is `None` when git cannot answer and `[]`
when it answers "clean"; a package that is not installed is `None`.

**Host parity**:

```bash
python -m samebytes parity --record      # on the reference host; commit the file
python -m samebytes parity               # on another host: 0 match, 1 differ, 2 no reference
python -m samebytes parity --reference path/to/platform_reference.json
python -m samebytes parity --lock requirements-lock.txt   # also each installed package vs its pin
```

`--lock` (repeatable) compares every `name==version` line of a file of exact
pins with the installed distribution. Any other line (a range, a URL, an
environment marker) is printed as `NOT CHECKED` and fails the lock check rather
than being skipped quietly.

A wrapper passes its own reference path and the phrases its advice prints:
`parity.main(reference=..., hints={"rebaseline": ..., ...})`; see `HINTS`.

**The hook**:

```bash
python -m samebytes hooks install [REPO]  # copies into REPO/.githooks, sets core.hooksPath
python -m samebytes hooks check [REPO]    # 0 when every copy is the packaged one
```

`install --no-config` copies the files without setting `core.hooksPath`.
`check --require-config` also fails when `core.hooksPath` is not `.githooks`;
leave it off in CI, where a fresh clone has not opted in.

Then pin the hooks to LF and commit them executable:

```
# .gitattributes
.githooks/*  text eol=lf
```

```bash
git add .gitattributes && git add --chmod=+x .githooks/*
```

## Why it looks the way it does

Each of these was a real failure, and each has a test that plants it:

- **The tree is hashed through `git hash-object`, never as raw bytes**, so a
  file `.gitattributes` pins to CRLF matches its LF index blob.
- **The whole tree is read**, not a list of files: a check that reads one row
  of a table is a check on that row.
- **The repository is always an argument.** Installed, the module's own
  directory is site-packages.
- **The canonical CSV is CRLF on every platform.** pandas defaults the line
  terminator to `os.linesep`, so a Linux run of a byte-identical build
  reported every cell as different from hashes taken on Windows.
- **Provenance columns are dropped by name; column order is never touched.**
  A wall-clock date column made a run that straddled midnight disagree with
  itself; sorting columns would make every hash already on record
  incomparable.
- **Columns are compared by position.** A frame returned sorted carries a
  scrambled index; the same frame read back from CSV does not. Comparing
  Series aligns them by label and reports nearly every float column as
  different.
- **None, NaN, `pd.NA` and the empty string are one value.** An all-empty text
  column is a run of bare commas in a CSV and reads back as float NaN.
- **Text is recognised by dtype kind**, so pandas 3's Arrow-backed `str` is
  text, not a float column to subtract.
- **`read_exact` reads with `float_precision="round_trip"`**: the default
  parser is fast and not correctly rounded, and returned 119898.1845882996 for
  119898.18458829961. For comparisons only: a pipeline that reads its own
  inputs with the default parser is deterministic, and switching it would move
  every number.
- **A release that adds a column is checked on the shared columns, named.**
  Hashing the whole frame against the build before it reported all four cells
  as different on a configuration identical on 142 of 142 shared columns.
- **Provenance is written at capture time, and "could not tell" is never
  "clean".** A lock file named one machine's environment for seven weeks while
  every baseline was taken on the other, and nothing recorded which.
- **A pandas version is never reported as a defect.** `str_dtype` reads
  `object` on pandas 2 and `str` on 3; it gets its own bucket.
- **The probe grids are pinned**: a reference is only comparable with the
  probe set that recorded it.
- **The hook is sh, and copied into each repository.** A Python hook that
  cannot find an interpreter fails silently; a `core.hooksPath` into
  site-packages names nothing on a second machine sharing the synced
  `.git/config`. `hooks check` reports drift, CRLF, a missing `eol=lf` pin and
  a missing executable bit, each of which makes a copy silently useless.
- **The hook re-stats only entries whose content already matches the index**,
  so it cannot stage, hide or discard a real edit.

## Develop

```bash
pip install -e ".[test]"
python -m pytest
```

The tests build throwaway git repositories, so git must be on PATH; the one
that runs the hook also needs an sh (Git for Windows' counts) and skips
without one. `tests/test_rules.py` holds the package to its own rules: the
standard library only at import, ASCII only, a docstring on every definition.
CI runs the suite on Windows, Linux and macOS at Python 3.9, 3.12 and 3.14,
then again against the built wheel.

A release bumps `samebytes.__version__` (the one place the version is written;
`pyproject.toml` reads it), adds a [CHANGELOG](CHANGELOG.md) entry, and tags
`vX.Y.Z`. Consumers pin the tag. A changed parity probe or grid is a new probe
key, never an edit, and a changed hook means every consumer runs
`hooks install` again.

## Licence

MIT. See [LICENSE](LICENSE).
