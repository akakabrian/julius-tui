# Design decisions for julius-tui

## Engine strategy: pure-Python sim inspired by Julius, not FFI into Julius

**Reference:** simcity-tui wraps Micropolis via SWIG, which works because
Micropolis had an existing SWIG `.i` file and a clean C++ engine separable
from the SDL frontend.

**Julius is different.** It's a monolithic SDL2 application with no
headless mode, no Python bindings, and the simulation is tightly
interleaved with graphics/sound/input subsystems. More critically, **Julius
cannot boot without original Caesar III asset files** (`c3.eng`,
`c3_north.eng`, `c3_map.eng`, `.555` and `.sg2` image archives from the
1998 Sierra CD). We don't have those assets, and the engine refuses to
initialize without them.

**Decision:** reimplement a minimal faithful Caesar III-style simulation
in pure Python, cribbing from Julius's source for:

- Terrain bit flags (`TERRAIN_TREE`, `TERRAIN_WATER`, `TERRAIN_ROAD`,
  `TERRAIN_MEADOW`, etc. — see `engine/src/map/terrain.h`)
- Building type enum (`BUILDING_ROAD`, `BUILDING_HOUSE_*`,
  `BUILDING_WHEAT_FARM`, `BUILDING_PREFECTURE`, etc. — see
  `engine/src/building/type.h`)
- House evolution tiers (tent → shack → hovel → casa → insula → villa →
  palace — see `engine/src/building/house_evolution.c`)
- City-finance model (treasury, taxes, wages, trade — see
  `engine/src/city/finance.c`)
- 162×162 isometric map dimensions (constant from `engine/src/map/grid.h`)

This mirrors the **JS reimplementation path** the skill calls out:
"For JS: either reimplement in Python or run via Node subprocess." The C
case would normally be SWIG, but Julius doesn't separate cleanly enough.

The vendored `engine/` source tree remains in the repo as a reference for
constants, formulas, and behaviour, but is **not linked into the Python
process**.

## Map dimensions: 80×80 (not Julius's 162×162)

Julius uses a 162×162 grid. At 1 char per tile that's still tractable
terminal-side, but the simulation throughput (housing evolution, figure
pathing, desirability sweeps) on pure Python would slow tick rate below
4 Hz. We scale to 80×80 for responsive gameplay — still large enough to
feel like a proper city, and matches the "small map" size in Caesar III.

## Isometric vs top-down

The real Julius is isometric with diamond tiles. True isometric in a
terminal eats vertical space (each iso row is half a text row tall, tiles
overlap). We render **top-down** — each grid cell is one terminal
character — and use glyph + colour to convey the tile contents. This is
what both Micropolis's TUI port and the vast majority of roguelike city
builders do. The map reads as "top-down Rome" rather than forcing iso
into a character grid.

## Rendering & scale

Following simcity-tui conventions:
- `ScrollView` with per-row `render_line(y)` for viewport-cropped rendering
- Pre-parsed `rich.style.Style` per tile class, cached at init
- Run-length segments (same-style cells → one `Segment`)
- 2-glyph pattern per class keyed on `(x + y) & 1` so zones don't read as
  letter spam
- 2 Hz animation frame counter for water ripples and cursor blink

## Out of scope for MVP

- Walkers (figures — patricians, market ladies, prefects): the Julius
  figure system is ~3000 lines of C with pathfinding, morale, attack
  behaviour. Phase 7E-ish if we get there.
- Gods, festivals, emperor's requests: distinctive Caesar III features
  but not required for "boot + render + build" gate.
- Military / legion management, enemy invasions.
- Trade routes with foreign cities.
- The 54-scenario campaign. MVP ships one sandbox scenario.

## Directory conventions (mirrors simcity-tui)

```
julius-tui/
├── julius.py                    # argparse entry point
├── pyproject.toml
├── Makefile                     # venv, run, test, clean
├── DECISIONS.md                 # this file
├── engine/                      # vendored Julius source (reference only)
└── julius_tui/
    ├── __init__.py
    ├── sim.py                   # pure-Python simulation (Julius-inspired)
    ├── tiles.py                 # terrain/building → (glyph, style)
    ├── app.py                   # Textual App + MapView + panels
    ├── screens.py               # modal screens
    └── tui.tcss
└── tests/
    ├── qa.py
    └── perf.py
```
