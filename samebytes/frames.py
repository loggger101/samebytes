def _comparable(df):
    """The frame with every provenance column removed.

    Column ORDER is left alone deliberately.  Sorting them would be tidier and
    would silently make every hash this file prints incomparable with the eight
    already committed in versions.md -- which is the whole point of printing one.
    """
    return df[[c for c in df.columns if c not in PROVENANCE]]


def _csv(df) -> str:
    """The canonical text a cell hashes to.

    The baseline stored on disk IS these bytes, so a hash comparison is a byte
    comparison of the file and needs no parsing at all -- which is why the hash
    is the authority here and the column diff is the diagnostic.

    to_csv writes floats at repr precision, so nothing is lost on the way OUT.
    Reading them back is the lossy direction: see _read_baseline.

    lineterminator is PINNED, and leaving it off is trap #12.  pandas defaults
    it to `os.linesep`, so this function returns CRLF text on Windows and LF
    text on Linux -- and the hash is taken over exactly this string.  Every
    cell hash in versions.md was computed on Windows, over CRLF, so the same
    build on Linux reproduces every float and still reports DIFFER on all four
    cells.  That is the eleven-entry table in this header happening a twelfth
    time: a broken comparator that looks exactly like a broken release.  CRLF
    is pinned rather than LF because CRLF is what the committed hashes are OF.
    """
    return _comparable(df).to_csv(index=False, lineterminator="\r\n")


def cell_hash(df) -> str:
    """First 16 hex digits of the sha256 of the cell's comparable CSV.

    Sixteen because that is the width every release note in versions.md quotes,
    and this harness reproduces the four hashes committed for v1.17.4 and
    v1.17.6 exactly. It goes through `_csv` / `_comparable`, which strips BOTH
    provenance columns and deliberately does NOT sort the remaining ones:
    sorting would be tidier and would silently make every hash printed here
    incomparable with the ones already on record.
    """
    return hashlib.sha256(_csv(df).encode("utf-8")).hexdigest()[:16]


def column_diff(a, b) -> Tuple[int, int, List[str]]:
    """(identical, compared, differing) over the shared non-provenance columns.

    Compared POSITIONALLY, via .to_numpy(), and that is not a detail.
    build_profitability_catalog returns its rows SORTED by the objective, so a
    live frame carries a scrambled index while the same frame re-read from CSV
    carries a fresh RangeIndex.  Comparing the two Series directly makes pandas
    align on the index LABEL, so nearly every float column reports as differing
    while the file hashes identical -- which is the ninth entry in this file's
    header, found by this very function on the run it was written for.  The
    hash said MATCH and the column diff said DIFFER, and the hash was right.

    Nulls are normalised to one spelling before comparing.  A parquet round trip
    renders a None in an object column back as nan, so a naive per-column
    astype(str) reports thrust_scaling, isru_feed_material and name as differing
    when they are identical -- v1.17.1 lost time to exactly that.
    """
    shared = [c for c in a.columns if c in b.columns and c not in PROVENANCE]
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
            same = _blanks(x) == _blanks(y)
        if not same:
            differing.append(c)
    return len(shared) - len(differing), len(shared), differing


def _blanks(s) -> list:
    """A column as a list with every spelling of "nothing here" collapsed to None.

    None, NaN and the EMPTY STRING all become None, and that last one is trap
    #11.  An all-empty object column written by to_csv is a run of bare commas,
    and read_csv types that column as float64-of-NaN -- so a live `""` comes
    back as `nan` and a naive comparison calls them different.  They are not:
    a CSV cannot represent the difference, so the file's own hash cannot see it
    either, and a comparator stricter than the artefact it compares reports
    failures that do not exist.  `payload_mix` and `payload_dominant_phase` are
    empty on every row of a raw cell and were the last two columns to fall.
    """
    return [None if (v is None or v != v or v == "") else v
            for v in s.to_numpy().tolist()]


def _isnan(v):
    """numpy's isnan, imported lazily so the module imports without pandas.

    Only ever called on a value already known to be a float, which is why there
    is no type guard: `math.isnan` would do as well here and numpy is already
    loaded by the time any comparison runs.
    """
    import numpy as np
    return np.isnan(v)


def _read_baseline(pd, path):
    """Read a baseline cell back WITHOUT losing the last bit of every float.

    float_precision="round_trip" is mandatory, and leaving it off is trap #10 in
    the header.  pandas' default C parser is a fast float reader that is NOT
    correctly rounded, so it returns a float64 one ULP away from the one that
    was written -- `119898.18458829961` comes back as `119898.1845882996`.
    Neither "high" nor the default round-trips; only "round_trip" does.

    That produced the same symptom as trap #9 and had to be diagnosed
    separately: 64 of 139 columns reported as DIFFER while all four cells
    hashed byte-identical to the baseline.  Same family as the pyarrow CSV
    engine v1.17.4 measured and rejected -- a different float parser rounding
    differently in the last ULP -- and the same lesson: a comparison is only as
    exact as the slackest step in it.

    NOTE this says nothing about the pipeline itself.  load_all_catalogs reads
    with the default parser too, so the model's inputs go through the same
    slightly-inexact reader on every run -- which is deterministic, and is
    therefore why bit-identity holds at all.  Do not "fix" that: changing
    float_precision there would move every number in the model.
    """
    return pd.read_csv(path, low_memory=False, float_precision="round_trip")
