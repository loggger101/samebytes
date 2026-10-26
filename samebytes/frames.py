# -*- coding: utf-8 -*-
"""Are these two runs the same?  A hash that is the authority, and a column diff
that is the diagnostic.

Written as part of economicspace's release harness (`verify.py`), whose header
lists the harness bugs that each line below defends against.  Four of them were
DIFFERENT causes of one identical symptom: columns reported as DIFFER beside a
byte-identical hash.  The rules that came out of them:

  - The hash is taken over CSV text with the line terminator PINNED to CRLF,
    never `os.linesep`, because the committed hashes are hashes of CRLF.
  - Columns the caller names as provenance (a version stamp, a wall-clock date)
    are dropped before hashing; column ORDER is never touched.
  - Columns are compared by POSITION, not by index label.
  - None, NaN and the empty string are one value: a CSV cannot tell them apart.
  - Text columns are recognised by dtype KIND, so pandas 3's Arrow-backed `str`
    is text too.
  - Read a CSV back with `float_precision="round_trip"`: the default parser is
    not correctly rounded.  In COMPARISONS only; a pipeline that reads its
    inputs with the default parser is deterministic, and switching it would
    move every number.

numpy and pandas are imported only when a function needs them, so this package
installs with no dependencies and can never move a pinned version.
"""
import hashlib
import struct
from typing import Iterable, List, Sequence, Tuple


def comparable(df, drop: Sequence[str] = ()):
    """The frame with every provenance column (`drop`) removed.

    Column ORDER is left alone.  Sorting the columns would be tidier, and every
    hash printed from it would silently stop matching the ones already
    committed, which are what a printed hash is compared against.
    """
    return df[[c for c in df.columns if c not in drop]]


def canonical_csv(df, drop: Sequence[str] = ()) -> str:
    """The canonical text a frame hashes to.

    A baseline stored on disk IS these bytes, so a hash comparison is a byte
    comparison of the file and needs no parsing at all -- which is why the hash
    is the authority and the column diff is the diagnostic.

    to_csv writes floats at repr precision, so nothing is lost on the way OUT.
    Reading them back is the lossy direction: see `read_exact`.

    lineterminator is PINNED, and leaving it off was the twelfth harness bug in
    economicspace.  pandas defaults it to `os.linesep`, so this function would
    return CRLF text on Windows and LF text on Linux -- and the hash is taken
    over exactly this string.  Every committed cell hash was computed on
    Windows, over CRLF, so the same build on Linux reproduces every float and
    still reports DIFFER on every cell: a broken comparator that looks exactly
    like a broken release.  CRLF is pinned rather than LF because CRLF is what
    the committed hashes are OF.
    """
    return comparable(df, drop).to_csv(index=False, lineterminator="\r\n")


def frame_hash(df, drop: Sequence[str] = (), width: int = 16) -> str:
    """The first `width` hex digits of the sha256 of `canonical_csv(df, drop)`.

    Sixteen by default because that is the width economicspace's release notes
    quote, and its harness reproduces the hashes committed for v1.17.4 and
    v1.17.6 exactly through this function.
    """
    return hashlib.sha256(canonical_csv(df, drop).encode("utf-8")).hexdigest()[:width]


def column_diff(a, b, drop: Sequence[str] = ()) -> Tuple[int, int, List[str]]:
    """(identical, compared, differing) over the shared columns not in `drop`.

    Compared POSITIONALLY, via .to_numpy().  A frame returned SORTED by some
    objective carries a scrambled index while the same frame re-read from CSV
    carries a fresh RangeIndex.  Comparing the two Series
    directly makes pandas align on the index LABEL, so nearly every float
    column reports as differing while the file hashes identical.  The hash said
    MATCH and the column diff said DIFFER, and the hash was right.

    Nulls are normalised to one spelling before comparing.  A parquet round trip
    renders a None in an object column back as nan, so a naive per-column
    astype(str) reports identical text columns as differing.

    Float columns are compared exactly, NaN equal to NaN; every other dtype
    (object, pandas 3's `str`, bool, int) goes through `blanks`.
    """
    shared, _, _ = shared_columns(a, b, drop)
    differing = []
    for c in shared:
        x, y = a[c], b[c]
        if len(x) != len(y):
            differing.append(c)
            continue
        if x.dtype.kind == "f" and y.dtype.kind == "f":
            xv, yv = x.to_numpy(), y.to_numpy()
            same = bool(((xv == yv) | (_isnan(xv) & _isnan(yv))).all())
        else:
            same = blanks(x) == blanks(y)
        if not same:
            differing.append(c)
    return len(shared) - len(differing), len(shared), differing


def shared_columns(a, b, drop: Sequence[str] = ()) -> Tuple[List[str], List[str], List[str]]:
    """(shared, only in a, only in b), provenance (`drop`) left out of all three.

    `shared` and `only_a` are in A's column order, `only_b` in B's.
    """
    shared = [c for c in a.columns if c in b.columns and c not in drop]
    only_a = [c for c in a.columns if c not in b.columns and c not in drop]
    only_b = [c for c in b.columns if c not in a.columns and c not in drop]
    return shared, only_a, only_b


def shared_hash(a, b, drop: Sequence[str] = (), width: int = 16) -> Tuple[str, str, List[str]]:
    """(hash of A, hash of B, the columns hashed) over the columns both carry.

    A release that ADDS a column cannot be checked by hashing the whole frame
    against the build before it: the frame is a column wider by construction,
    so the hash is certain to differ and says nothing.  economicspace once
    reported all four cells as DIFFER on a configuration later proved identical
    on 142 of 142 shared columns.  Hash the shared set and NAME it, which is why
    the column list is returned, not just the two hashes.

    Both frames are hashed in A's column order.  The rule elsewhere is that
    column order is never touched, and that rule is about matching hashes
    already committed; no committed hash is ever a shared hash, so the only
    requirement here is that both sides use the same order.  When the shared
    columns are in the same relative order in both frames (a column inserted
    or appended), this is each frame's own order.

    The hash is over what each frame HOLDS.  A frame read back from a CSV holds
    what the reader made of it, so hand this the frames in memory when you have
    them.  Before trusting a re-read file, check that
    `frame_hash(read_exact(f), drop)` reproduces the hash the file was written
    under.  A file that re-reads exactly gives a shared hash equal to one taken
    in memory.
    """
    shared, _, _ = shared_columns(a, b, drop)
    return (frame_hash(a[shared], width=width), frame_hash(b[shared], width=width),
            shared)


def blanks(s) -> list:
    """A column as a list with every spelling of "nothing here" collapsed to None.

    None, NaN and the EMPTY STRING all become None, and that last one was the
    eleventh harness bug.  An all-empty object column written by to_csv is a
    run of bare commas, and read_csv types that column as float64-of-NaN -- so
    a live `""` comes back as `nan` and a naive comparison calls them
    different.  They are not: a CSV cannot represent the difference, so the
    file's own hash cannot see it either, and a comparator stricter than the
    artefact it compares reports failures that do not exist.

    pandas' own missing marker, `pd.NA` (the nullable `string` dtype's), is
    tested by identity BEFORE the `v != v` test, because comparing it raises
    "boolean value of NA is ambiguous".  economicspace's verify.py never met
    one; this is the only input on which the two differ, and there it raised.
    """
    import pandas as pd
    na = pd.NA
    return [None if (v is None or v is na or v != v or v == "") else v
            for v in s.to_numpy().tolist()]


def _isnan(v):
    """numpy's isnan, imported lazily so the module imports without numpy.

    Only ever called on a value already known to be a float array, which is why
    there is no type guard.
    """
    import numpy as np
    return np.isnan(v)


def read_exact(path_or_buf, **kwargs):
    """`pandas.read_csv` that does not lose the last bit of any float.

    float_precision="round_trip" is mandatory here, and leaving it off was the
    tenth harness bug.  pandas' default C parser is a fast float reader that is
    NOT correctly rounded, so it returns a float64 one ULP away from the one
    that was written -- `119898.18458829961` comes back as `119898.1845882996`.
    Neither "high" nor the default round-trips; only "round_trip" does.  That
    produced 64 of 139 columns reported as DIFFER while every file hashed
    byte-identical.

    `low_memory=False` unless the caller says otherwise; any other read_csv
    argument passes through.  Passing `float_precision` is refused rather than
    silently obeyed, because the only reason to call this is that one argument.

    FOR COMPARISONS ONLY.  A pipeline that reads its own inputs with the
    default parser is deterministic, and that is why its bit-identity holds;
    switching its loader to this would move every number it produces.
    """
    if "float_precision" in kwargs:
        raise TypeError("read_exact always reads with float_precision='round_trip'")
    import pandas as pd
    kwargs.setdefault("low_memory", False)
    return pd.read_csv(path_or_buf, float_precision="round_trip", **kwargs)


def float_hash(values: Iterable[float], width: int = 16) -> str:
    """sha256 of the raw IEEE 754 bit patterns, first `width` hex digits.

    `struct.pack` rather than `repr` because this has to be sensitive to the
    last bit and nothing else: repr would compare correctly today and hide a
    difference the moment anything reformatted it.
    """
    h = hashlib.sha256()
    for v in values:
        h.update(struct.pack("<d", float(v)))
    return h.hexdigest()[:width]
