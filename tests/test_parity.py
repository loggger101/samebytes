# -*- coding: utf-8 -*-
"""parity: the probes, the reference round trip, and the four buckets of a difference."""
import copy
import json

import pytest

from samebytes import parity


@pytest.fixture(scope="module")
def now():
    """One collection for the module: the spawn probe starts a pool."""
    return parity.collect()


def test_collect_has_every_probe(now):
    """The probe set a reference file is keyed by."""
    assert set(now) == {"libm", "numpy", "csv", "pandas", "spawn", "host"}
    assert now["csv"]["crlf"] is True and now["csv"]["float_round_trip"] is True
    assert now["spawn"]["ok"] is True, now["spawn"]


def test_probe_grids_are_pinned(monkeypatch):
    """The argument grids the probes CALL are exactly what references were recorded with.

    The calls are recorded from the probes themselves, so a grid edited inside
    a probe is caught, not only one edited in this table.  `_grid` is
    additions and multiplications only, correctly rounded on every IEEE host,
    so the hashes are host-independent.  If one moves, every recorded
    reference stops being comparable: that is a new probe set, not an edit.
    """
    calls, real = [], parity._grid
    monkeypatch.setattr(parity, "_grid", lambda *a: calls.append(a) or real(*a))
    parity.probe_libm()
    parity.probe_numpy()
    monkeypatch.setattr(parity, "_grid", real)
    grids = {
        (0.05, 8.0, 512): "438c72aef619a2ef",
        (1.0000001, 5000.0, 512): "7825f72b9111067f",
        (0.0, 180.0, 512): "e659aa3e7f08ed32",
        (1e-6, 1e9, 512): "93865787b63a7d99",
        (0.1, 1e6, 512): "d0af3677bc4a88ea",
        (-2.0, 35.0, 512): "6a89a5088c755f43",
        (100.0, 20000.0, 512): "7f3e28d1c86c71de",
    }
    assert sorted(set(calls)) == sorted(grids)
    got = {k: parity._hash_floats(parity._grid(*k)) for k in grids}
    assert got == grids


def test_record_then_check_matches(tmp_path, capsys, now):
    """A reference recorded here compares clean here."""
    ref = tmp_path / "ref.json"
    assert parity.main(["--record", "--reference", str(ref)]) == 0
    assert parity.main(["--reference", str(ref)]) == 0
    assert "ALL PROBES MATCH" in capsys.readouterr().out


def test_missing_reference_exits_2_with_the_hint(tmp_path, capsys):
    """No file: exit 2, and the wrapper's own instruction is the one printed."""
    rc = parity.main(["--reference", str(tmp_path / "none.json")],
                     hints={"record_missing": "python platform_check.py --record"})
    assert rc == 2
    assert "Run:  python platform_check.py --record" in capsys.readouterr().out


def _with(now, key, value):
    """A copy of `now` with one dotted key changed, as a reference."""
    ref = copy.deepcopy(now)
    a, b = key.split(".")
    ref[a][b] = value
    return ref


def _report(now, ref, capsys, hints=None):
    """report()'s exit code and printed text."""
    rc = parity.report(now, ref, hints)
    return rc, capsys.readouterr().out


def test_a_pandas_version_is_never_called_a_defect(now, capsys):
    """str_dtype differing (pandas 2 vs 3) lands in the pandas bucket, not under BROKEN."""
    rc, out = _report(now, _with(now, "pandas.str_dtype", "elsewhere"), capsys)
    assert rc == 1 and "PANDAS DTYPE CONTRACT DIFFERS" in out and "BROKEN" not in out


def test_libm_divergence_is_a_host_property(now, capsys):
    """A libm hash differing is reported as divergence with re-baseline advice, not a defect."""
    rc, out = _report(now, _with(now, "libm.exp", "0" * 16), capsys,
                      {"rebaseline": "py verify.py baseline"})
    assert rc == 1 and "LIBM / NUMPY DIVERGENCE" in out and "BROKEN" not in out
    assert "Re-baseline on this host (py verify.py baseline)" in out


def test_csv_or_spawn_difference_is_broken(now, capsys):
    """The two things a project controls: a difference there is a defect."""
    rc, out = _report(now, _with(now, "csv.crlf", False), capsys)
    assert rc == 1 and "BROKEN" in out


def test_host_facts_are_never_compared(now, capsys):
    """Another CPU count or pandas version alone is informational."""
    ref = _with(_with(now, "host.cpu_count", 1), "host.pandas", "0.0")
    rc, out = _report(now, ref, capsys, {"hashes_doc": "versions.md"})
    assert rc == 0 and "(reference: 1)" in out and "committed in versions.md" in out


def test_reference_file_is_lf_json(tmp_path, now):
    """--record writes sorted JSON with LF endings, whatever the platform."""
    ref = tmp_path / "ref.json"
    parity.main(["--record", "--reference", str(ref)])
    raw = ref.read_bytes()
    assert b"\r\n" not in raw and json.loads(raw)["csv"]["crlf"] is True
