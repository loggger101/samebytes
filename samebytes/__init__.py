# -*- coding: utf-8 -*-
"""samebytes: are these the same bytes?

Three levels of the one question, each a module:

  tree     does the working tree hold the bytes git says it holds?
  parity   can this host reproduce the committed numbers bit for bit?
  frames   are these two runs (pandas frames or CSVs) the same?

plus `provenance`, which records what produced a run (the commit and the
environment) when it happens, and `hooks`, which installs the sh hook that
repairs git's stat cache in a synced folder.  Split out of
loggger101/economicspace with its history.

And the house rules a family of repositories shares, so that each stops
keeping its own drifting copy:

  docs     do the docs hold together (links, anchors, structure, dashes),
           does the rules file copy no measurement, did a reorganisation
           lose no number, and is every git pin at one ref?
  source   do the sources follow the rules (docstrings, ASCII, imports, a
           quiet import, one version, a help comment on every config
           field), and what help does each field carry?
"""
__version__ = "0.5.0"
