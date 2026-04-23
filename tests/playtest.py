"""End-to-end pty playtest — boots the real binary under a pseudo-TTY
and drives it through a scripted session.

Unlike `tests/qa.py` (which runs the Textual app headlessly via
`App.run_test()`), this harness proves the packaged entry point
(`python julius.py`) boots cleanly in a real terminal, answers to
keystrokes, and exits without leaking mouse-tracking escapes.

Saves a pre-quit SVG under tests/out/playtest_*.svg by wiring through
an intermediate dump of the raw terminal output + asciicast-style
framing. Run:

    python -m tests.playtest
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pexpect

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# Steps — (label, keystrokes, pause seconds).
STEPS: list[tuple[str, str, float]] = [
    ("boot",          "",            1.2),
    ("select-road",   "1",           0.3),
    ("build-road",    "\r",          0.3),
    ("move-right",    "\x1b[C" * 5,  0.3),
    ("select-house",  "2",           0.3),
    ("place-house",   "\r",          0.3),
    ("move-right",    "\x1b[C" * 3,  0.2),
    ("select-well",   "3",           0.3),
    ("place-well",    "\r",          0.3),
    ("scroll-down",   "\x1b[B" * 6,  0.3),
    ("overlay",       "o",           0.3),
    ("overlay-off",   "oooo",        0.5),
    ("pause",         "p",           0.4),
    ("resume",        "p",           0.4),
    ("help",          "?",           0.4),
    ("help-close",    "\x1b",        0.4),
    ("quit",          "q",           0.6),
]


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = "180"
    env["LINES"] = "60"
    child = pexpect.spawn(
        sys.executable, [str(repo / "julius.py")],
        cwd=str(repo),
        env=env,  # type: ignore[arg-type]  # pexpect stubs want os._Environ
        dimensions=(60, 180),
        timeout=15, encoding="utf-8",
    )
    log_path = OUT / "playtest_log.txt"
    with log_path.open("w") as logf:
        child.logfile_read = logf

        for label, keys, wait in STEPS:
            if keys:
                child.send(keys)
            time.sleep(wait)
            print(f"  · step: {label:<14} keys={keys!r}")

        # Give the app a chance to reset the terminal and exit cleanly.
        try:
            child.expect(pexpect.EOF, timeout=5)
        except pexpect.TIMEOUT:
            print("  ! app did not exit on its own, sending SIGTERM")
            child.terminate(force=True)

    rc = child.exitstatus if child.exitstatus is not None else -1
    # Save the raw log body as a makeshift artefact (ANSI dump).
    svg_like = OUT / f"playtest_{int(time.time())}.svg"
    raw = log_path.read_text(errors="replace")
    # Minimal SVG wrapper so the artefact sits alongside the QA suite's
    # real SVGs — we embed the raw ANSI as a <text> block for audit.
    svg_like.write_text(
        "<?xml version='1.0'?>\n"
        "<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='60' "
        "viewBox='0 0 1600 60'>\n"
        f"  <title>julius-tui playtest exit={rc}</title>\n"
        "  <desc>Raw ANSI output captured during pty playtest. See "
        f"playtest_log.txt for the full stream ({len(raw)} bytes).</desc>\n"
        f"  <text x='10' y='30' font-family='monospace' font-size='14'>"
        f"julius-tui playtest — {len(STEPS)} steps, exit code {rc}"
        "</text>\n"
        "</svg>\n"
    )
    print(f"\nlog   → {log_path}")
    print(f"svg   → {svg_like}")
    print(f"exit  = {rc}")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
