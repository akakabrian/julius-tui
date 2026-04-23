"""Headless QA driver for julius-tui.

Each scenario boots a fresh `JuliusApp` under `App.run_test()`, drives
it via `pilot.press` / `pilot.click`, and asserts on live state. SVG
screenshots saved to tests/out/ for visual diffing.

    python -m tests.qa            # run all
    python -m tests.qa cursor     # filter by name
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from julius_tui import sim, tiles
from julius_tui.app import TOOLS, JuliusApp

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[JuliusApp, "object"], Awaitable[None]]


# ---- helpers ----------------------------------------------------------

async def find_clear(app: JuliusApp) -> tuple[int, int] | None:
    """Find a tile with no terrain bits set — safe to build on."""
    for y in range(sim.MAP_H):
        for x in range(sim.MAP_W):
            bits, bid = app.sim.get_tile(x, y)
            if bits == 0 and bid == -1:
                return (x, y)
    return None


# ---- scenarios --------------------------------------------------------

async def s_mount_clean(app, pilot):
    """App mounts without exceptions and all panels exist."""
    assert app.map_view is not None
    assert app.status_panel is not None
    assert app.ratings_panel is not None
    assert app.tools_panel is not None
    assert app.sim is not None


async def s_cursor_starts_centered(app, pilot):
    assert app.map_view.cursor_x == sim.MAP_W // 2
    assert app.map_view.cursor_y == sim.MAP_H // 2


async def s_cursor_moves(app, pilot):
    sx = app.map_view.cursor_x
    sy = app.map_view.cursor_y
    await pilot.press("right", "right", "right", "down", "down")
    assert app.map_view.cursor_x == sx + 3
    assert app.map_view.cursor_y == sy + 2


async def s_cursor_clamps(app, pilot):
    for _ in range(sim.MAP_W + 5):
        await pilot.press("left")
    assert app.map_view.cursor_x == 0
    for _ in range(sim.MAP_H + 5):
        await pilot.press("up")
    assert app.map_view.cursor_y == 0


async def s_tool_select(app, pilot):
    """Pressing '1' selects the road tool."""
    await pilot.press("1")
    assert TOOLS[app.tools_panel.selected].label == "Road"


async def s_apply_road_changes_tile(app, pilot):
    spot = await find_clear(app)
    assert spot is not None, "no clear tile found"
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    await pilot.press("1")
    await pilot.press("enter")
    await pilot.pause()
    bits, _ = app.sim.get_tile(*spot)
    assert bits & sim.TERRAIN_ROAD, (
        f"expected road at {spot}, got bits={bits}"
    )


async def s_apply_road_deducts_funds(app, pilot):
    spot = await find_clear(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    before = app.sim.city.treasury
    await pilot.press("1")
    await pilot.press("enter")
    await pilot.pause()
    assert app.sim.city.treasury < before, (
        f"treasury unchanged: {before} → {app.sim.city.treasury}"
    )


async def s_pause_halts_ticks(app, pilot):
    await pilot.pause(0.2)
    month_before = app.sim.city.month
    sub_before = app.sim.city.sub_tick
    await pilot.press("p")
    assert app.paused is True
    await pilot.pause(0.5)
    # Paused → sim_tick shouldn't run, so sub_tick stays put.
    assert app.sim.city.month == month_before
    assert app.sim.city.sub_tick == sub_before, (
        f"sub_tick advanced while paused: {sub_before} → {app.sim.city.sub_tick}"
    )
    await pilot.press("p")
    assert app.paused is False


async def s_help_opens(app, pilot):
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "Screen"


async def s_tutorial_opens(app, pilot):
    await pilot.press("t")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "TutorialScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_legend_opens(app, pilot):
    await pilot.press("l")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "LegendScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_bulldoze_clears(app, pilot):
    """Place a road, then bulldoze it, then confirm the bit is gone."""
    spot = await find_clear(app)
    assert spot is not None
    app.map_view.cursor_x, app.map_view.cursor_y = spot
    await pilot.pause()
    # Place road.
    await pilot.press("1")
    await pilot.press("enter")
    await pilot.pause()
    bits, _ = app.sim.get_tile(*spot)
    assert bits & sim.TERRAIN_ROAD
    # Bulldoze.
    await pilot.press("0")
    await pilot.press("enter")
    await pilot.pause()
    bits, _ = app.sim.get_tile(*spot)
    assert not (bits & sim.TERRAIN_ROAD), "road survived bulldoze"


async def s_status_panel_throttles(app, pilot):
    """StatusPanel refresh with no state change must skip rebuilding."""
    app.status_panel.refresh_panel()
    snap1 = app.status_panel._last_snapshot
    for _ in range(5):
        app.status_panel.refresh_panel()
    assert app.status_panel._last_snapshot == snap1


async def s_render_has_fg_and_bg(app, pilot):
    """Every rendered tile must carry both fg and bg colour."""
    app.map_view.scroll_to_cursor()
    await pilot.pause()
    y_vp = app.map_view.cursor_y - int(app.map_view.scroll_offset.y)
    strip = app.map_view.render_line(y_vp)
    fg_only = 0
    both = 0
    for seg in strip:
        if not seg.style:
            continue
        if seg.style.color and seg.style.bgcolor:
            both += 1
        elif seg.style.color and not seg.style.bgcolor:
            fg_only += 1
    assert both > 0, "no tiles rendered with background colour"
    assert fg_only <= 2, f"too many fg-only segments: {fg_only}"


async def s_cursor_has_highlight(app, pilot):
    """Exactly one cell in the cursor row carries the cursor style."""
    from rich.style import Style
    bright = Style.parse("bold black on rgb(255,220,80)")
    dim = Style.parse("bold rgb(40,40,0) on rgb(200,170,40)")
    app.map_view.scroll_to_cursor()
    await pilot.pause()
    y_vp = app.map_view.cursor_y - int(app.map_view.scroll_offset.y)
    strip = app.map_view.render_line(y_vp)
    hits = sum(
        len(seg.text) for seg in strip
        if seg.style == bright or seg.style == dim
    )
    assert hits == 1, f"expected 1 cursor cell, got {hits}"


async def s_house_evolution_with_services(app, pilot):
    """Place a house next to a well; after enough ticks, confirm the
    population > 0 and services are being computed."""
    spot = await find_clear(app)
    assert spot is not None
    x, y = spot
    # Place a well next to it.
    app.sim.do_tool(sim.BUILDING_WELL, x + 1, y)
    # Place a house.
    app.sim.place_house(x, y)
    # Run enough sub-ticks for evolution RNG to fire reliably.
    # Growth probability is 0.08/tick × 1-in-5 sampling; 500 ticks
    # gives ~100 opportunities, far beyond the tail of the distribution.
    for _ in range(500):
        app.sim.sim_tick()
    # Population should have grown.
    bid = app.sim.building_at[y * sim.MAP_W + x]
    assert bid >= 0
    b = app.sim.buildings[bid]
    assert b is not None
    assert b.house_population > 0, (
        f"house pop={b.house_population} after 120 ticks — evolution broken"
    )


async def s_tick_advances_clock(app, pilot):
    """50 sim-ticks must advance month by one."""
    month_start = app.sim.city.month
    year_start = app.sim.city.year
    for _ in range(50):
        app.sim.sim_tick()
    after = app.sim.city.month
    assert after != month_start or app.sim.city.year != year_start, (
        f"month did not advance: {month_start} → {after}"
    )


async def s_flash_bar_on_tool(app, pilot):
    """Selecting a tool puts feedback on the flash bar, not the log."""
    log_before = len(app.message_log.lines)
    await pilot.press("3")  # Well
    await pilot.pause()
    assert "Well" in str(app.flash_bar.content)
    assert len(app.message_log.lines) == log_before


async def s_rating_bars_survive_zero(app, pilot):
    """Ratings panel must render even with all-zero ratings without
    raising."""
    app.sim.city.rating_culture = 0
    app.sim.city.rating_prosperity = 0
    app.sim.city.rating_peace = 0
    app.sim.city.rating_favor = 0
    app.ratings_panel._last_snapshot = None  # force redraw
    app.ratings_panel.refresh_panel()


async def s_out_of_bounds_rejected(app, pilot):
    """do_tool must return OUT_OF_BOUNDS cleanly — no crash, no mutation."""
    result = app.sim.do_tool(sim.BUILDING_ROAD, -1, 5)
    assert result == sim.TOOLRESULT_OUT_OF_BOUNDS
    result = app.sim.do_tool(sim.BUILDING_ROAD, sim.MAP_W + 5, 5)
    assert result == sim.TOOLRESULT_OUT_OF_BOUNDS


async def s_water_animates(app, pilot):
    """Water glyph swaps between animation frames."""
    mv = app.map_view
    # Find water on the map.
    water_xy = None
    for y in range(sim.MAP_H):
        for x in range(sim.MAP_W):
            bits, _ = app.sim.get_tile(x, y)
            if bits & sim.TERRAIN_WATER:
                water_xy = (x, y)
                break
        if water_xy:
            break
    if water_xy is None:
        return  # no water, skip
    mv.scroll_to_region(
        __import__("textual.geometry", fromlist=["Region"]).Region(
            water_xy[0], water_xy[1], 1, 1),
        animate=False, force=True)
    await pilot.pause()
    vx = water_xy[0] - int(mv.scroll_offset.x)
    vy = water_xy[1] - int(mv.scroll_offset.y)
    mv._anim_frame = 0
    a = "".join(seg.text for seg in list(mv.render_line(vy)))[vx]
    mv._anim_frame = 1
    b = "".join(seg.text for seg in list(mv.render_line(vy)))[vx]
    assert a != b, f"water glyph did not change: {a!r} == {b!r}"


async def s_overlay_cycle(app, pilot):
    """Pressing 'o' must cycle through overlay modes and wrap."""
    modes = ["off", "water", "food", "religion", "entertain"]
    start = app.map_view.overlay_mode
    seen = [start]
    for _ in range(len(modes)):
        await pilot.press("o")
        await pilot.pause()
        seen.append(app.map_view.overlay_mode)
    assert seen[-1] == start, f"overlay didn't wrap: {seen}"
    assert set(seen) >= set(modes), f"missing modes: {set(modes) - set(seen)}"


async def s_mouse_click_places(app, pilot):
    """A left-click on the map selects the tile and applies the current tool."""
    spot = await find_clear(app)
    assert spot is not None
    await pilot.press("1")  # road
    await pilot.pause()
    app.map_view.scroll_to_region(
        __import__("textual.geometry", fromlist=["Region"]).Region(
            spot[0] - 2, spot[1] - 2, 5, 5),
        animate=False, force=True)
    await pilot.pause()
    offset = (spot[0] - int(app.map_view.scroll_offset.x),
              spot[1] - int(app.map_view.scroll_offset.y))
    funds_before = app.sim.city.treasury
    await pilot.click("MapView", offset=offset)
    await pilot.pause()
    assert (app.map_view.cursor_x, app.map_view.cursor_y) == spot
    bits, _ = app.sim.get_tile(*spot)
    assert bits & sim.TERRAIN_ROAD, f"click didn't place road at {spot}"
    assert app.sim.city.treasury < funds_before


SCENARIOS: list[Scenario] = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("cursor_starts_centered", s_cursor_starts_centered),
    Scenario("cursor_moves", s_cursor_moves),
    Scenario("cursor_clamps", s_cursor_clamps),
    Scenario("tool_select", s_tool_select),
    Scenario("apply_road_changes_tile", s_apply_road_changes_tile),
    Scenario("apply_road_deducts_funds", s_apply_road_deducts_funds),
    Scenario("pause_halts_ticks", s_pause_halts_ticks),
    Scenario("help_opens_and_closes", s_help_opens),
    Scenario("tutorial_opens", s_tutorial_opens),
    Scenario("legend_opens", s_legend_opens),
    Scenario("bulldoze_clears_tile", s_bulldoze_clears),
    Scenario("status_panel_throttles", s_status_panel_throttles),
    Scenario("render_has_fg_and_bg", s_render_has_fg_and_bg),
    Scenario("cursor_has_highlight", s_cursor_has_highlight),
    Scenario("tick_advances_clock", s_tick_advances_clock),
    Scenario("flash_bar_on_tool", s_flash_bar_on_tool),
    Scenario("ratings_panel_zero_ratings", s_rating_bars_survive_zero),
    Scenario("out_of_bounds_rejected", s_out_of_bounds_rejected),
    Scenario("water_animates", s_water_animates),
    Scenario("house_evolution_with_services", s_house_evolution_with_services),
    Scenario("overlay_cycle", s_overlay_cycle),
    Scenario("mouse_click_places", s_mouse_click_places),
]


# ---- driver -----------------------------------------------------------

async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = JuliusApp()
    try:
        async with app.run_test(size=(180, 60)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines()[:5]:
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
