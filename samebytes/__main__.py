# -*- coding: utf-8 -*-
"""Command line.

    python -m samebytes tree [REPO]                     exit 0 match, 1 finding, 2 skipped
    python -m samebytes parity [--record] [--reference FILE]
                                                        exit 0 match, 1 differ, 2 no reference
    python -m samebytes hooks install [REPO] [--no-config]
    python -m samebytes hooks check [REPO] [--require-config]
                                                        exit 0 clean, 1 findings
    python -m samebytes --version

ASCII output only: a Windows console's cp1252 stdout cannot print much else.
"""
import os
import sys


def _hooks(argv) -> int:
    """`hooks install` / `hooks check`."""
    import argparse
    from . import hooks
    ap = argparse.ArgumentParser(prog="python -m samebytes hooks")
    ap.add_argument("action", choices=("install", "check"))
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--no-config", action="store_true",
                    help="install: do not set core.hooksPath")
    ap.add_argument("--require-config", action="store_true",
                    help="check: also require core.hooksPath to be .githooks")
    args = ap.parse_args(argv)
    repo = os.path.abspath(args.repo)
    if args.action == "install":
        changed = hooks.install(repo, set_config=not args.no_config)
        for c in changed:
            print("  wrote %s" % c)
        print("  %d hook file(s) written; commit them with "
              "`git add --chmod=+x .githooks/*`" % len(changed) if changed
              else "  hooks already current")
        return 0
    findings = hooks.check(repo, require_config=args.require_config)
    for f in findings:
        print("  ! " + f)
    print("  hooks      %s" % ("%d finding(s)" % len(findings) if findings
                               else "%d files match the packaged copies" % len(hooks.HOOKS)))
    return 1 if findings else 0


def main(argv=None) -> int:
    """Dispatch to a module's command line."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "--version":
        from . import __version__
        print("samebytes " + __version__)
        return 0
    if cmd == "tree":
        from . import tree
        return tree.main(rest[0] if rest else None)
    if cmd == "parity":
        from . import parity
        return parity.main(rest)
    if cmd == "hooks":
        return _hooks(rest)
    print("unknown command %r\n\n%s" % (cmd, __doc__.strip()))
    return 2


if __name__ == "__main__":
    sys.exit(main())
