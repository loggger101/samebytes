# -*- coding: utf-8 -*-
"""samebytes: are these the same bytes?

Three levels of the one question, each a module:

  tree     does the working tree hold the bytes git says it holds?
  parity   can this host reproduce the committed numbers bit for bit?
  frames   are these two runs (pandas frames or CSVs) the same?

plus `hooks`, which installs the sh hook that repairs git's stat cache in a
synced folder.  Split out of loggger101/economicspace with its history.
"""
__version__ = "0.1.0"
