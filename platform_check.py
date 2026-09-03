# -*- coding: utf-8 -*-
"""Is THIS host able to reproduce the committed numbers?  Answer in ~10 seconds.

The pipeline is portable: every path goes through `os.path.join`, the worker
pool asks for `spawn` explicitly rather than inheriting the platform default,
and nothing imports a Windows API outside `launch_ui.py`, which degrades on its
own.  So `run_pipeline.py` runs on Linux as it stands.

What does NOT travel is BIT-IDENTITY, and that is the whole currency of this
project: every release in `versions.md` is argued from a cell hash, and the
20-cell campaign is 26 hours of work whose value is that it can be compared to
one.  Two things can break that comparison without anything being wrong with
the model, and both are silent:

  1. `pandas.to_csv` defaults `lineterminator` to `os.linesep`.  A catalog
     written on Linux is LF where every committed hash was taken over CRLF, so
     a byte-perfect run reports DIFFER on every cell.  This is FIXED at source
     (the terminator is pinned in the four writers and in `verify.py`); the
     check here is the regression test for that fix.

  2. `math.exp`, `math.log` and `math.cos` are the platform libm, and
     `numpy` chooses SIMD kernels per architecture.  None of them is required
     by IEEE 754 to be correctly rounded, so glibc on aarch64 and the Windows
     UCRT on x86-64 may disagree in the last bit.  The rocket equation is
     `math.exp(dv / ve)` and the mass every ranking runs on comes out of
     `np.power(10.0, -H / 5.0)`, so a one-ULP difference there is not academic.
     This one CANNOT be fixed, only measured, which is what this file is for.

Usage:

    python platform_check.py --record     # on the reference host, once
    python platform_check.py              # on the new host: compare and report

`--record` writes `platform_reference.json`, which is committed.  The default
mode recomputes every probe and diffs it against that file.  It is deliberately
the same baseline/check shape as `verify.py`, and for the same reason: a
reference value that is typed into prose is a number waiting to rot, so this
one is derived on both sides and never written down by hand.

Exit codes: 0 all probes match, 1 a probe differs, 2 the reference is missing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import struct
import sys


# The launcher to name in a printed instruction.  `py` is the Windows launcher
# and does not exist anywhere else, so a hint that says it is wrong advice on
# the host that most needs the hint.  Not shared between files on purpose: the
# four modules must stay standalone for the Colab paste, and this is one
# expression, not a manifest.
_PY = "py" if os.name == "nt" else os.path.basename(sys.executable)

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(HERE, "platform_reference.json")


# -----------------------------------------------------------------------------
# EXACT FLOAT HASHING
# -----------------------------------------------------------------------------
def _hash_floats(values) -> str:
    """sha256 of the raw IEEE 754 bit patterns, first 16 hex digits.

    `struct.pack` rather than `repr` because this has to be sensitive to the
    last bit and nothing else: repr would compare correctly today and hide a
    difference the moment anything reformatted it.  Sixteen digits to match the
    width `verify.py` and every release note already quote.
    """
    h = hashlib.sha256()
    for v in values:
        h.update(struct.pack("<d", float(v)))
    return h.hexdigest()[:16]


def _grid(lo: float, hi: float, n: int):
    """`n` evenly spaced float64 values across [lo, hi], endpoints included.

    Written out rather than taken from numpy so the ARGUMENTS are identical on
    every host by construction.  If the grid itself came from `np.linspace`,
    a numpy difference would move the inputs as well as the outputs and the
    probe could not say which had happened.
    """
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


# -----------------------------------------------------------------------------
# THE PROBES
# -----------------------------------------------------------------------------
def probe_libm() -> dict:
    """The stdlib transcendentals the mass cascade actually calls.

    Argument ranges are the model's own, not decorative:

      exp   `math.exp(dv / ve)` in the rocket equation.  dv runs to ~20 km/s
            and effective exhaust velocity from ~3 km/s (chemical) to ~50 km/s
            (electric), so the ratio spans roughly 0.05 to 8.
      log   `isp * g0 * math.log(r_ret_eff)` inverting the same relation, so
            the argument is a mass ratio, 1.0 upward.
      cos   `math.cos(math.radians(i))` on orbital inclination in degrees.
      sqrt  IEEE 754 REQUIRES correct rounding for sqrt, so this one is a
            CONTROL: it must match on every conforming host, and a mismatch
            here means something far more basic is wrong than a libm variance.
      pow   the `**` operator, which routes to libm pow for non-integer powers.
    """
    return {
        "exp":  _hash_floats(math.exp(x) for x in _grid(0.05, 8.0, 512)),
        "log":  _hash_floats(math.log(x) for x in _grid(1.0000001, 5000.0, 512)),
        "cos":  _hash_floats(math.cos(math.radians(x)) for x in _grid(0.0, 180.0, 512)),
        "sqrt": _hash_floats(math.sqrt(x) for x in _grid(1e-6, 1e9, 512)),
        "pow":  _hash_floats(x ** 0.3333333333333333 for x in _grid(0.1, 1e6, 512)),
    }


def probe_numpy() -> dict:
    """The vectorised calls, where numpy picks a kernel per architecture.

    `np.power(10.0, -H / 5.0)` is the one that matters most: it is the H to
    diameter conversion in `catalog.py`, so it sets `estimated_mass_kg`, and
    mass is what the ranking runs on.  A one ULP move there is the same class
    of thing as the pyarrow CSV engine that was measured at 4.8x and REJECTED
    for moving that column by 1e-13 relative.

    The inputs are built from a Python list so the grid is bit-identical across
    hosts before numpy ever sees it; see `_grid`.
    """
    import numpy as np
    h = np.asarray(_grid(-2.0, 35.0, 512), dtype=np.float64)
    dv = np.asarray(_grid(100.0, 20000.0, 512), dtype=np.float64)
    return {
        "np_power_h":  _hash_floats(np.power(10.0, -h / 5.0).tolist()),
        "np_exp":      _hash_floats(np.exp(dv / (3000.0 * 9.80665)).tolist()),
        "np_log":      _hash_floats(np.log(1.0 + dv / 1000.0).tolist()),
        "np_sqrt":     _hash_floats(np.sqrt(dv).tolist()),
        "np_sum":      _hash_floats([float(np.sum(np.sin(dv)))]),
    }


def probe_csv() -> dict:
    """The CSV contract: line terminator, float repr, and the round trip.

    `lineterminator` is checked against CRLF explicitly rather than against
    `os.linesep`, because the point is that it must NOT follow the platform.

    The round trip is `float_precision="round_trip"`, which `verify.py` depends
    on absolutely: the default C parser is fast and NOT correctly rounded, and
    reading a baseline without it reports 64 of 139 columns as differing while
    every file hashes identical.
    """
    import pandas as pd
    df = pd.DataFrame({
        "f": [1.0 / 3.0, 119898.18458829961, 2.2250738585072014e-308],
        "s": ["a", "", None],
    })
    written = df.to_csv(index=False, lineterminator="\r\n")

    import io as _io
    back = pd.read_csv(_io.StringIO(written), float_precision="round_trip")
    round_trips = all(
        float(a) == float(b)
        for a, b in zip(df["f"].tolist(), back["f"].tolist())
    )
    return {
        "crlf": "\r\n" in written and "\n\n" not in written,
        "float_round_trip": round_trips,
        "repr_hash": _hash_floats(df["f"].tolist()),
    }


def probe_pandas_dtypes() -> dict:
    """The dtype contract, which is the half `probe_csv` cannot see.

    `probe_csv` checks the FLOAT path: line terminator, repr, round trip.
    Every trap this project has actually been bitten by lives on the OBJECT
    path instead, and all three share one premise, that the dtype is inferred
    from the data rather than declared:

      empty_is_nan      an all-empty object column writes as bare commas and
                        reads back as float64-of-NaN, so a live `""` meets a
                        `nan`.  Trap 3 of the three that produced one identical
                        symptom while the files hashed MATCH.
      bool_with_gap     a bool column with one missing value.  `.astype(bool)`
                        reads NaN and the string "False" as True, which is why
                        `_truthy(series, default=...)` exists.
      str_dtype         what pandas infers for a plain text column.  pandas
                        2.x gives `object`; 3.0 gives an Arrow-backed `str`,
                        and that change is why this probe was added.

    None of these is a float, so none of them moves a cell hash on its own.
    They move BEHAVIOUR, and a host where they differ will produce a correct
    looking run that is wrong somewhere nothing hashes.
    """
    import io as _io

    import pandas as pd

    df = pd.DataFrame({
        "empty": ["", "", ""],
        "flag":  [True, False, None],
        "text":  ["a", "bb", "ccc"],
    })
    written = df.to_csv(index=False, lineterminator="\r\n")
    back = pd.read_csv(_io.StringIO(written))

    return {
        # True means the empty column came back as all-null, whatever its dtype.
        "empty_is_nan": bool(back["empty"].isna().all()),
        # The dtype a missing value forces a bool column into.
        "bool_with_gap": str(back["flag"].dtype),
        # object (pandas 2.x) or str (pandas 3.0 Arrow-backed strings).
        "str_dtype": str(back["text"].dtype),
    }


def probe_spawn() -> dict:
    """A `spawn` pool must start and a worker must see what the parent sees.

    This is the cheap version of `verify.py` check 3.  It does not touch the
    pipeline; it only proves the platform can do the thing the pipeline asks
    for, because `mp.get_context("spawn")` on Linux is a supported but not
    DEFAULT context, and a container with no writable /dev/shm fails it.
    """
    import multiprocessing as mp
    try:
        with mp.get_context("spawn").Pool(processes=2) as pool:
            got = pool.map(_worker_probe, [1.0, 2.0, 3.0])
        return {"ok": True, "hash": _hash_floats(got)}
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def _worker_probe(x: float) -> float:
    """One unit of spawn-pool work, at module scope so it can be pickled.

    A lambda or a closure would fail to pickle under `spawn`, which is exactly
    the failure this probe is meant to rule out, so it must be a plain
    top-level function.
    """
    return math.exp(x) + math.log(x + 1.0)


# -----------------------------------------------------------------------------
# HOST FACTS
# -----------------------------------------------------------------------------
def host_facts() -> dict:
    """What this host is, for the report only; never compared.

    Deliberately outside the probe set: an aarch64 Linux box is SUPPOSED to
    differ here, and failing on it would make the check useless for the job it
    exists to do.  What gets compared is the arithmetic, not the badge.
    """
    try:
        import numpy as np
        numpy_v = np.__version__
    except Exception:                              # noqa: BLE001
        numpy_v = "missing"
    try:
        import pandas as pd
        pandas_v = pd.__version__
    except Exception:                              # noqa: BLE001
        pandas_v = "missing"
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "system": platform.system(),
        "libc": "/".join(x for x in platform.libc_ver() if x) or "n/a",
        "numpy": numpy_v,
        "pandas": pandas_v,
        "cpu_count": os.cpu_count(),
        "float_repr_style": sys.float_info.dig,
    }


def collect() -> dict:
    """Every probe plus the host facts, as one JSON-serialisable dict."""
    return {
        "libm": probe_libm(),
        "numpy": probe_numpy(),
        "csv": probe_csv(),
        "pandas": probe_pandas_dtypes(),
        "spawn": probe_spawn(),
        "host": host_facts(),
    }


# -----------------------------------------------------------------------------
# REPORTING
# -----------------------------------------------------------------------------
def _flatten(d: dict, prefix: str = "") -> dict:
    """`{"libm": {"exp": x}}` becomes `{"libm.exp": x}`, for a flat diff."""
    out = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def report(now: dict, ref: dict) -> int:
    """Print the comparison and return the process exit code.

    Groups the result three ways, because the three have different remedies:
    a CSV or spawn failure is a BUG to fix, a libm or numpy difference is a
    property of the host that no edit will change, and a host-facts difference
    is expected and informational.
    """
    flat_now, flat_ref = _flatten(now), _flatten(ref)
    hard, soft = [], []

    for key in sorted(flat_now):
        if key.startswith("host."):
            continue
        a, b = flat_now[key], flat_ref.get(key, "<absent>")
        if a == b:
            continue
        (soft if key.startswith(("libm.", "numpy.")) else hard).append((key, b, a))

    print("\n  HOST")
    for k in ("python", "implementation", "machine", "system", "libc",
              "numpy", "pandas", "cpu_count"):
        mine = now["host"].get(k)
        theirs = ref["host"].get(k)
        flag = "" if mine == theirs else "   (reference: %s)" % theirs
        print("    %-16s %s%s" % (k, mine, flag))

    print("\n  PROBES")
    for key in sorted(flat_now):
        if key.startswith("host."):
            continue
        a = flat_now[key]
        same = a == flat_ref.get(key)
        print("    %-24s %-18s %s" % (key, a, "match" if same else "DIFFER"))

    if hard:
        print("\n  *** BROKEN: these are defects, not host properties ***")
        for key, want, got in hard:
            print("    %-24s reference %-14s got %s" % (key, want, got))

    if soft:
        print("\n  *** LIBM / NUMPY DIVERGENCE ***")
        for key, want, got in soft:
            print("    %-24s reference %-18s got %s" % (key, want, got))
        print("\n    This host's math library rounds at least one function")
        print("    differently from the reference host.  Nothing is wrong with")
        print("    the model and nothing can be edited to fix it.  What it")
        print("    means is that a cell hash produced here will not equal a")
        print("    cell hash produced there, so the two hosts' runs must be")
        print("    compared on VALUES with a tolerance, not on hashes.")
        print("    Re-baseline on this host (%s verify.py baseline) and every" % _PY)
        print("    comparison WITHIN this host stays exact.")

    if not hard and not soft:
        print("\n  ALL PROBES MATCH.  Cell hashes computed on this host are")
        print("  directly comparable with the ones committed in versions.md.")
        return 0
    return 1


def main() -> int:
    """Record a reference, or check this host against one."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true",
                    help="write platform_reference.json for this host")
    args = ap.parse_args()

    print("=" * 72)
    print("  PLATFORM PARITY PROBE")
    print("=" * 72)

    now = collect()

    if args.record:
        with open(REFERENCE, "w", encoding="utf-8", newline="") as f:
            json.dump(now, f, indent=2, sort_keys=True)
            f.write("\n")
        print("\n  Recorded -> %s" % REFERENCE)
        for k, v in sorted(_flatten(now).items()):
            print("    %-26s %s" % (k, v))
        return 0

    if not os.path.exists(REFERENCE):
        print("\n  No reference file at %s" % REFERENCE)
        print("  Run:  python platform_check.py --record")
        return 2

    with open(REFERENCE, encoding="utf-8") as f:
        ref = json.load(f)

    rc = report(now, ref)
    print("")
    return rc


if __name__ == "__main__":
    sys.exit(main())
