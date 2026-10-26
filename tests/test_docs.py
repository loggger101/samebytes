# -*- coding: utf-8 -*-
"""samebytes.docs: each check passes a clean tree and fails each planted defect."""
import textwrap

from samebytes import docs


def write(root, name, text):
    """Write `text` (dedented) to root/name, making directories; return name."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return name


def test_slugs_follow_github():
    """Underscores kept, punctuation and code ticks dropped, repeats numbered, fences skipped."""
    text = textwrap.dedent("""
        # Title
        ## Reading `profitability_catalog.csv`
        ## Notes (2026)
        ### Verification
        ### Verification
        ```bash
        # Verification
        ```
        ## Closed ##
    """)
    assert docs.slugs(text) == {"title", "reading-profitability_catalogcsv", "notes-2026",
                                "verification", "verification-1", "closed"}


def test_links_clean(tmp_path):
    """Links to files, anchors in this file and in another, up from a subdirectory."""
    write(tmp_path, "README.md", """
        # Top
        See [the code](src/a.py), [below](#top), [sub](sub/NOTES.md#part-two),
        [space](my%20file.txt), [web](https://example.com/x) and [mail](mailto:a@b).
    """)
    write(tmp_path, "src/a.py", "x = 1\n")
    write(tmp_path, "my file.txt", "")
    write(tmp_path, "sub/NOTES.md", """
        # Notes
        ## Part two
        Back [up](../README.md#top).
    """)
    bad, n = docs.links(str(tmp_path), ["README.md", "sub/NOTES.md"])
    assert bad == [] and n == 3


def test_links_planted(tmp_path):
    """A missing file, a missing anchor here and there, and a listed doc not on disk."""
    write(tmp_path, "README.md", """
        # Top
        [gone](nope.md) [here](#nowhere) [there](OTHER.md#missing) [ok](OTHER.md#other)
    """)
    write(tmp_path, "OTHER.md", "# Other\n")
    bad, n = docs.links(str(tmp_path), ["README.md", "GHOST.md"])
    assert bad == ["GHOST.md is listed and is not on disk",
                   "README.md -> nope.md  (no such file)",
                   "README.md -> #nowhere  (no such anchor)",
                   "README.md -> OTHER.md#missing  (no such anchor)"]
    assert n == 3


def test_links_resolve_from_the_linking_file(tmp_path):
    """A subdirectory doc's `../X.md` resolves; resolving from the root would call it broken."""
    write(tmp_path, "A.md", "# A\n")
    write(tmp_path, "sub/B.md", "# B\n[a](../A.md) [wrong](A.md)\n")
    bad, _ = docs.links(str(tmp_path), ["sub/B.md"])
    assert bad == ["sub/B.md -> A.md  (no such file)"]


def test_structure_clean(tmp_path):
    """One h1, steady levels, square tables, repeated h3s, a heading in a fence ignored."""
    write(tmp_path, "README.md", """
        # Title
        ## One
        ### Verification
        | a | b |
        |---|---|
        | 1 | 2 |
        ## Two
        ### Verification
        ```
        # not a heading
        #### nor this
        ```
    """)
    assert docs.structure(str(tmp_path), ["README.md"]) == ([], 1)


def test_structure_planted(tmp_path):
    """Each defect is reported once, and a table at end of file is still checked."""
    write(tmp_path, "BAD.md", """
        # Title
        #### Jump
        ## Same
        ## Same
        # Second title
        ```
        unclosed
    """)
    # No newline after the last row: the table ends with the file, not a blank line.
    (tmp_path / "TAIL.md").write_text("# Tail\n| a | b |\n|---|---|---|", encoding="utf-8")
    bad, n = docs.structure(str(tmp_path), ["BAD.md", "TAIL.md", "GHOST.md"])
    assert n == 2
    assert bad == ["GHOST.md is listed and is not on disk",
                   "BAD.md: unbalanced code fences (last at line 6)",
                   "BAD.md: heading jumps h1 -> h4 at line 2",
                   "BAD.md: 2 h1 headings, want exactly 1",
                   "BAD.md: duplicate heading '## Same' (2x)",
                   "TAIL.md: ragged table at line 2"]


def test_structure_one_h1_can_be_waived(tmp_path):
    """A history divided into parts by h1s passes with one_h1=False, and only then."""
    write(tmp_path, "H.md", "# Part one\n## a\n# Part two\n## b\n")
    assert docs.structure(str(tmp_path), ["H.md"], one_h1=False) == ([], 1)
    assert docs.structure(str(tmp_path), ["H.md"])[0] == ["H.md: 2 h1 headings, want exactly 1"]


def test_dashes(tmp_path):
    """Whole files are checked everywhere; prose_only sources in comments and docstrings only."""
    em, en = "\u2014", "\u2013"
    write(tmp_path, "README.md", "# T\nfine, here\nA %s B\n, orphan\n" % em)
    write(tmp_path, "data.py", '"""Doc %s here."""\n# note %s\nNOTES = "data %s kept"\n'
          "# , orphan comment\n" % (en, em, em))
    bad, n = docs.dashes(str(tmp_path), ["README.md"], prose_only=["data.py"])
    assert n == 2
    assert [b.split("  ")[0] + "  " + b.split("  ")[1] for b in bad] == [
        "README.md:3  em/en dash", "README.md:4  line opens with a bare comma",
        "data.py:1  em/en dash", "data.py:2  em/en dash",
        "data.py:4  line opens with a bare comma"]


def test_dashes_unparseable_prose_only_source(tmp_path):
    """A prose_only file that does not parse is a finding, not a silent skip."""
    write(tmp_path, "broken.py", "def f(:\n")
    bad, n = docs.dashes(str(tmp_path), [], prose_only=["broken.py"])
    assert n == 1 and len(bad) == 1 and bad[0].startswith("broken.py: could not parse")


def test_structure_no_h1(tmp_path):
    """A doc with no title at all is as wrong as one with two."""
    write(tmp_path, "N.md", "## Only a section\n")
    assert docs.structure(str(tmp_path), ["N.md"])[0] == ["N.md: 0 h1 headings, want exactly 1"]


def test_figures_drop_versions_links_years_and_small_numbers():
    """Decimals and thousands count; versions, link targets, years and short integers do not."""
    line = ("calc v1.21.0 [notes](v.md#calc-v1120--x-v1100) in 2026: "
            "12.5 s, 1,555,667 rows, 64 cells, 1999 and 4096")
    assert docs.figures(line) == {"12.5", "1,555,667", "4096"}


def test_pairs_clean(tmp_path):
    """Answers may share with each other; the rules file may share two numbers, or registered ones."""
    write(tmp_path, "README.md", "# R\nTook 12.5 s over 1,555,667 rows at 0.73.\n")
    write(tmp_path, "MODEL.md", "# M\nSame 12.5 s, 1,555,667 rows, 0.73.\n")
    write(tmp_path, "CLAUDE.md", """
        # C
        Only 12.5 and 0.73 here.
        Registered: 3.46 and 18.5 and 12.1.

        | the shared measurement | where |
        |---|---|
        | 3.46, 18.5, 12.1 | README |
    """)
    write(tmp_path, "OTHER.md", "# O\nCrossing at 3.46 AU, 18.5 against 12.1 km/s.\n")
    bad, n = docs.pairs(str(tmp_path), ["README.md", "MODEL.md", "OTHER.md"], "CLAUDE.md",
                        register_header="| the shared measurement | where |")
    assert bad == [] and n == 1


def test_pairs_planted(tmp_path):
    """An unregistered pair is named once per number set, and a listed file not on disk is a finding."""
    write(tmp_path, "README.md", "# R\nTook 12.5 s over 1,555,667 rows at 0.73.\nAgain 12.5 and 1,555,667 and 0.73.\n")
    write(tmp_path, "CLAUDE.md", "# C\nA rule quoting 0.73 and 12.5 and 1,555,667.\n")
    bad, n = docs.pairs(str(tmp_path), ["README.md", "GHOST.md"], "CLAUDE.md")
    assert n == 2
    assert bad == ["GHOST.md is listed and is not on disk",
                   "README.md:2 and CLAUDE.md:2 both quote 0.73, 1,555,667, 12.5, "
                   "not on the register"]


def test_pairs_register_rows_are_not_a_side(tmp_path):
    """A register row quotes what it registers; it is never itself one side of a pair."""
    write(tmp_path, "README.md", "# R\n1.25 and 2.5 and 3.75 measured.\n")
    write(tmp_path, "CLAUDE.md", "# C\n| reg |\n|---|\n| 1.25 2.5 3.75 |\n")
    bad, n = docs.pairs(str(tmp_path), ["README.md"], "CLAUDE.md", register_header="| reg |")
    assert bad == [] and n == 0


def test_transfer_clean(tmp_path):
    """A number that moved to any of the new files survives; years and short integers are not tracked."""
    write(tmp_path, "OLD.md", "# Old\nIt took 12.5 s and 1,555,667 rows in 2026, 64 cells, 4096 B.\n")
    write(tmp_path, "A.md", "# A\n12.5 s\n")
    write(tmp_path, "B.md", "# B\n1,555,667 rows, 4096 B\n")
    bad, n = docs.transfer(str(tmp_path), "OLD.md", ["A.md", "B.md"])
    assert bad == [] and n == 3


def test_transfer_planted(tmp_path):
    """A dropped number is named with its source line, sorted; a missing file is a finding, never a skip."""
    write(tmp_path, "OLD.md", "# Old\nAnd 1,555,667 rows.\nIt took 12.5 s.\nThen 0.25 left.\n"
                              "Kept 0.73.\n")
    write(tmp_path, "NEW.md", "# New\nKept 0.73.\n")
    bad, n = docs.transfer(str(tmp_path), "OLD.md", ["NEW.md", "GONE.md"])
    assert n == 4
    assert bad == ["GONE.md is listed and is not on disk",
                   "0.25           | Then 0.25 left.",
                   "1,555,667      | And 1,555,667 rows.",
                   "12.5           | It took 12.5 s."]
    assert docs.transfer(str(tmp_path), "NOPE.md", ["NEW.md"]) == (
        ["NOPE.md is listed and is not on disk"], 0)
