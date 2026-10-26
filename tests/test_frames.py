# -*- coding: utf-8 -*-
"""frames: each of the harness bugs behind it, planted, must be caught or tolerated as stated."""
import hashlib
import io
import random

import numpy as np
import pandas as pd
import pytest

from samebytes import frames

PROV = ("pipeline_version", "catalog_date")


def _frame():
    """A small frame shaped like a cell: floats, text, an empty text column, provenance."""
    return pd.DataFrame({
        "name": ["a", "b", "c"],
        "cost": [1.0 / 3.0, 119898.18458829961, 2.5],
        "mix": ["", "", ""],
        "pipeline_version": ["1.0.0"] * 3,
        "catalog_date": ["2026-10-25"] * 3,
    })


def test_hash_is_over_crlf_whatever_the_platform():
    """The canonical text is CRLF, and an LF rendering would hash differently."""
    df = _frame()
    text = frames.canonical_csv(df, drop=PROV)
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    lf = frames.comparable(df, PROV).to_csv(index=False, lineterminator="\n")
    assert frames.frame_hash(df, PROV) != hashlib.sha256(lf.encode()).hexdigest()[:16]


def test_provenance_is_dropped_and_order_kept():
    """A new date is invisible to the hash; a reordered column is not."""
    a, b = _frame(), _frame()
    b["catalog_date"] = "2026-10-26"                 # midnight fell mid-run
    assert frames.frame_hash(a, PROV) == frames.frame_hash(b, PROV)
    assert frames.frame_hash(a) != frames.frame_hash(b)
    reordered = a[["cost", "name", "mix", "pipeline_version", "catalog_date"]]
    assert frames.frame_hash(reordered, PROV) != frames.frame_hash(a, PROV)
    assert list(frames.comparable(a, PROV).columns) == ["name", "cost", "mix"]


def test_width():
    """The default is the sixteen digits release notes quote; any width can be asked for."""
    df = _frame()
    assert len(frames.frame_hash(df)) == 16 and len(frames.frame_hash(df, width=64)) == 64


def test_one_ulp_is_caught():
    """One unit in the last place moves the hash and names the column."""
    a, b = _frame(), _frame()
    b.loc[1, "cost"] = np.nextafter(b.loc[1, "cost"], np.inf)
    assert frames.frame_hash(a, PROV) != frames.frame_hash(b, PROV)
    assert frames.column_diff(a, b, PROV) == (2, 3, ["cost"])


def test_blank_spellings_are_one_value():
    """"" and NaN and None are the same to a CSV, so the diff calls them equal."""
    a = pd.DataFrame({"t": ["", "x", None]})
    b = pd.DataFrame({"t": [np.nan, "x", ""]})
    assert frames.column_diff(a, b) == (1, 1, [])


def test_empty_text_column_survives_a_csv_round_trip():
    """An all-empty text column reads back as float NaN; the diff must not call that a change."""
    a = _frame()
    b = frames.read_exact(io.StringIO(frames.canonical_csv(a)))
    assert frames.column_diff(a, b, PROV) == (3, 3, [])


def test_compared_by_position_not_index_label():
    """A sorted frame (scrambled index) against its re-read copy (fresh index) is equal."""
    a = _frame().sort_values("cost", ascending=False)
    b = a.reset_index(drop=True)
    assert list(a.index) != list(b.index)
    assert frames.column_diff(a, b, PROV) == (3, 3, [])


def test_text_columns_of_any_string_dtype_are_text():
    """pandas 3's Arrow-backed str (and the nullable string dtype) compare as text, not floats."""
    a = pd.DataFrame({"t": ["a", "b", ""]})
    b = pd.DataFrame({"t": pd.array(["a", "b", None], dtype="string")})
    assert frames.column_diff(a, b) == (1, 1, [])


def test_read_exact_round_trips_every_float():
    """Every float written at repr precision comes back bit for bit."""
    rng = random.Random(20261025)
    vals = [119898.18458829961, 2.2250738585072014e-308, 1.0 / 3.0, 5e-324, 1.7976931348623157e308]
    vals += [rng.uniform(-1e6, 1e6) * 10 ** rng.randint(-30, 30) for _ in range(5000)]
    df = pd.DataFrame({"x": vals})
    back = frames.read_exact(io.StringIO(df.to_csv(index=False)))
    assert [float(v).hex() for v in back["x"]] == [float(v).hex() for v in vals]


def test_read_exact_refuses_another_float_precision():
    """The one argument it exists for cannot be overridden by accident."""
    with pytest.raises(TypeError):
        frames.read_exact(io.StringIO("x\n1\n"), float_precision="high")


def test_read_exact_passes_other_arguments_through():
    """dtype and the rest reach read_csv; low_memory is only a default."""
    df = frames.read_exact(io.StringIO("designation,x\n069260,1.5\n"), dtype={"designation": str})
    assert df.loc[0, "designation"] == "069260"


def test_float_hash_sees_the_last_bit_and_the_sign_of_zero():
    """struct-packed, so repr formatting cannot hide a difference."""
    assert frames.float_hash([1.0]) != frames.float_hash([np.nextafter(1.0, 2.0)])
    assert frames.float_hash([0.0]) != frames.float_hash([-0.0])
    assert len(frames.float_hash([1.0], width=8)) == 8


def test_different_lengths_differ():
    """A column with a row missing is a difference, not an error."""
    a = pd.DataFrame({"x": [1.0, 2.0]})
    b = pd.DataFrame({"x": [1.0]})
    assert frames.column_diff(a, b) == (0, 1, ["x"])


def test_shared_hash_sees_through_an_added_column():
    """A release that adds a column: the whole-frame hash must differ, the shared hash must not."""
    a, b = _frame(), _frame()
    b.insert(2, "new_term", [0.5, 0.25, 0.125])
    assert frames.frame_hash(a, PROV) != frames.frame_hash(b, PROV)
    ha, hb, cols = frames.shared_hash(a, b, PROV)
    assert ha == hb
    assert cols == ["name", "cost", "mix"]
    assert frames.shared_columns(a, b, PROV) == (["name", "cost", "mix"], [], ["new_term"])


def test_shared_hash_still_sees_a_moved_value():
    """One ULP in a shared column is a difference whatever else was added."""
    a, b = _frame(), _frame()
    b["new_term"] = 1.0
    b.loc[1, "cost"] = np.nextafter(b.loc[1, "cost"], np.inf)
    ha, hb, _ = frames.shared_hash(a, b, PROV)
    assert ha != hb


def test_shared_hash_uses_one_order_for_both():
    """B's columns in another order hash in A's order, so the same values match."""
    a = _frame()
    b = a[list(reversed(a.columns))].copy()
    ha, hb, cols = frames.shared_hash(a, b, PROV)
    assert ha == hb and cols == ["name", "cost", "mix"]


def test_shared_hash_of_an_exact_reread_equals_memory():
    """A file that re-reads exactly gives the shared hash the frame in memory gives."""
    a = _frame()
    back = frames.read_exact(io.StringIO(frames.canonical_csv(a)))
    assert frames.frame_hash(back, PROV) == frames.frame_hash(a, PROV)
    back["extra"] = 1
    ha, hb, _ = frames.shared_hash(a, back, PROV)
    assert ha == hb
