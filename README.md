# julius-tui

Terminal-native Caesar III-style city builder, inspired by the
[Julius engine](https://github.com/bvschaik/julius).

Unlike its sibling `simcity-tui` (which wraps Micropolis via SWIG), this
project reimplements Caesar III's core simulation concepts in pure
Python. The Julius C source is vendored under `engine/` as a reference
for constants and formulas, but is **not** linked into the process — see
`DECISIONS.md` for the rationale (Julius is tightly coupled to SDL2 and
refuses to boot without original 1998 Caesar III asset files we don't
have).

## Quick start

```bash
make           # create venv, install
make run       # launch the TUI
make test      # run the headless QA harness
make perf      # print hot-path benchmarks
```

## Gameplay

- Arrow keys move the cursor.
- Digit keys select a tool; `enter` places at the cursor.
- `1` road, `2` vacant house lot, `3` well, `4` market, `5` temple,
  `6` amphitheatre, `7` prefecture, `8` wheat farm, `9` forum,
  `0` bulldoze.
- `f` fountain, `g` garden, `v` vegetable farm, `e` engineer's post,
  `s` senate.
- `p` pause, `o` cycle service overlay, `t` tutorial, `l` legend,
  `?` help, `q` quit.

## Status

Stages 1-5 of the `/home/brian/.claude/skills/tui-game-build/SKILL.md`
process complete:

- [x] Research & decision: pure-Python port (see DECISIONS.md)
- [x] "Engine integration": in-process Python sim module
- [x] 4-panel Textual scaffold (map / status / ratings / tools + log)
- [x] QA harness, 23 scenarios green
- [x] Perf baseline established (4.6 ms full-viewport render; well
      under 60 fps budget, no optimization needed)

Phase 6 polish partially started (service-coverage overlay done;
submenus, agent REST API, sound, LLM advisor still to come).
