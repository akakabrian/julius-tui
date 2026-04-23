"""Entry point — `python julius.py [scenario]`."""

from __future__ import annotations

import argparse

from julius_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="julius-tui")
    p.add_argument("scenario", nargs="?", default="fertilis",
                   help="scenario name (default: fertilis)")
    args = p.parse_args()
    run(args.scenario)


if __name__ == "__main__":
    main()
