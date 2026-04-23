"""Textual app — 4-panel Julius TUI.

Structure mirrors simcity-tui's app.py (ScrollView-based MapView with
render_line, side panels with memoised refresh_panel()), adapted to
our pure-Python Sim and Caesar III-flavoured tool set.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Region, Size
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Footer, Header, RichLog, Static

from . import sim, tiles
from .screens import HelpScreen, LegendScreen, TutorialScreen


@dataclass(frozen=True)
class ToolDef:
    key: str
    label: str
    building: int
    glyph: str
    style: str


# Tool palette — keyed on digit/letter keys. Uses sim.BUILDING_NONE as
# the "bulldoze" sentinel (do_tool dispatches on that).
TOOLS: list[ToolDef] = [
    ToolDef("1", "Road",            sim.BUILDING_ROAD,
            "─", "bold rgb(180,170,130) on rgb(22,18,10)"),
    ToolDef("2", "House (vacant)",  sim.BUILDING_HOUSE_VACANT_LOT,
            "░", "bold rgb(140,110,70) on rgb(30,22,12)"),
    ToolDef("3", "Well",            sim.BUILDING_WELL,
            "○", "bold rgb(120,180,230) on rgb(15,25,40)"),
    ToolDef("4", "Market",          sim.BUILDING_MARKET,
            "▤", "bold rgb(230,150,80) on rgb(45,28,12)"),
    ToolDef("5", "Small Temple",    sim.BUILDING_SMALL_TEMPLE,
            "✝", "bold rgb(240,230,140) on rgb(45,40,15)"),
    ToolDef("6", "Amphitheatre",    sim.BUILDING_AMPHITHEATER,
            "◎", "bold rgb(230,170,230) on rgb(40,25,45)"),
    ToolDef("7", "Prefecture",      sim.BUILDING_PREFECTURE,
            "◈", "bold rgb(220,80,80) on rgb(45,15,15)"),
    ToolDef("8", "Wheat Farm",      sim.BUILDING_WHEAT_FARM,
            "※", "bold rgb(240,210,90) on rgb(40,34,10)"),
    ToolDef("9", "Forum",           sim.BUILDING_FORUM,
            "☗", "bold rgb(220,200,140) on rgb(40,32,16)"),
    ToolDef("0", "Bulldoze",        sim.BUILDING_NONE,
            " ", "on rgb(120,96,64)"),
    # Letter keys for the less-common tools.
    ToolDef("f", "Fountain",        sim.BUILDING_FOUNTAIN,
            "◉", "bold rgb(150,210,255) on rgb(18,32,52)"),
    ToolDef("g", "Garden",          sim.BUILDING_GARDENS,
            "♦", "bold rgb(100,200,100) on rgb(15,38,18)"),
    ToolDef("v", "Vegetable Farm",  sim.BUILDING_VEGETABLE_FARM,
            "✿", "bold rgb(220,120,160) on rgb(40,18,30)"),
    ToolDef("e", "Engineer's Post", sim.BUILDING_ENGINEERS_POST,
            "⚙", "bold rgb(200,200,100) on rgb(40,38,15)"),
    ToolDef("s", "Senate",          sim.BUILDING_SENATE,
            "⌂", "bold rgb(240,220,160) on rgb(42,35,18)"),
]


class MapView(ScrollView):
    """Renders the 80×80 tile grid with a highlighted cursor.

    Same line-rendering approach as simcity-tui — Textual calls
    render_line(y) per visible row, we viewport-crop the x range, and
    build run-length-compressed segments."""

    DEFAULT_CSS = """
    MapView { padding: 0; }
    """

    cursor_x: reactive[int] = reactive(sim.MAP_W // 2)
    cursor_y: reactive[int] = reactive(sim.MAP_H // 2)

    class ToolApply(Message):
        def __init__(self, x: int, y: int) -> None:
            self.x, self.y = x, y
            super().__init__()

    def __init__(self, s: sim.Sim) -> None:
        super().__init__()
        self.sim = s
        self.virtual_size = Size(sim.MAP_W, sim.MAP_H)
        # Pre-parse every class's style once — per-cell Style.parse()
        # dominated the render loop in simcity-tui until this was added.
        self._styles: dict[str, Style] = {
            klass: Style.parse(tiles.style_for(klass)) for klass in tiles.COLOR
        }
        self._cursor_style = Style.parse("bold black on rgb(255,220,80)")
        self._cursor_dim = Style.parse("bold rgb(40,40,0) on rgb(200,170,40)")
        self._unknown_style = Style.parse("bold rgb(255,0,255) on black")
        self._anim_frame = 0
        self._last_map_serial = -1

    # --- animation -----------------------------------------------------

    def advance_animation(self) -> None:
        self._anim_frame ^= 1
        self.refresh()

    # --- rendering -----------------------------------------------------

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        tile_y = y + int(scroll_y)
        width = self.size.width
        if tile_y < 0 or tile_y >= sim.MAP_H:
            return Strip.blank(width)

        start_x = max(0, int(scroll_x))
        end_x = min(sim.MAP_W, start_x + width)

        s = self.sim
        cx, cy = self.cursor_x, self.cursor_y
        styles = self._styles
        unknown = self._unknown_style
        cursor_now = self._cursor_dim if self._anim_frame == 1 else self._cursor_style

        segments: list[Segment] = []
        run_chars: list[str] = []
        run_style: Style | None = None

        for x in range(start_x, end_x):
            bits, bid = s.get_tile(x, tile_y)
            if bid >= 0 and bid < len(s.buildings) and s.buildings[bid] is not None:
                b = s.buildings[bid]
                # Mypy/pyright: narrow-via-None-check above.
                assert b is not None
                klass = tiles.building_class(b.type)
            else:
                klass = tiles.terrain_class(bits)

            glyph = tiles.glyph_for(klass, x, tile_y)

            # Water animation — 2-frame glyph swap.
            if klass == "water":
                glyph = ("~", "≈")[self._anim_frame]

            if x == cx and tile_y == cy:
                style = cursor_now
            else:
                style = styles.get(klass, unknown)

            if style is run_style:
                run_chars.append(glyph)
            else:
                if run_chars:
                    segments.append(Segment("".join(run_chars), run_style))
                run_chars = [glyph]
                run_style = style
        if run_chars:
            segments.append(Segment("".join(run_chars), run_style))

        visible_cols = end_x - start_x
        if visible_cols < width:
            segments.append(Segment(" " * (width - visible_cols)))
        return Strip(segments, width)

    # --- refresh / invalidation ---------------------------------------

    def refresh_all_tiles(self) -> None:
        self._last_map_serial = self.sim.map_serial
        self.refresh()

    def refresh_if_map_changed(self) -> bool:
        serial = self.sim.map_serial
        if serial != self._last_map_serial:
            self._last_map_serial = serial
            self.refresh()
            return True
        return False

    def scroll_to_cursor(self) -> None:
        self.scroll_to_region(
            Region(self.cursor_x - 4, self.cursor_y - 2, 9, 5),
            animate=False, force=True,
        )

    def _refresh_row(self, tile_y: int) -> None:
        self.refresh(Region(0, tile_y, sim.MAP_W, 1))

    def watch_cursor_x(self, old: int, new: int) -> None:
        if not self.is_mounted:
            return
        self._refresh_row(self.cursor_y)
        self.scroll_to_cursor()

    def watch_cursor_y(self, old: int, new: int) -> None:
        if not self.is_mounted:
            return
        self._refresh_row(old)
        self._refresh_row(new)
        self.scroll_to_cursor()

    # --- mouse ---------------------------------------------------------

    def _event_to_tile(self, event: events.MouseEvent) -> tuple[int, int] | None:
        tx = event.x + int(self.scroll_offset.x)
        ty = event.y + int(self.scroll_offset.y)
        if 0 <= tx < sim.MAP_W and 0 <= ty < sim.MAP_H:
            return (tx, ty)
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        spot = self._event_to_tile(event)
        if spot is None:
            return
        self.cursor_x, self.cursor_y = spot
        self.post_message(self.ToolApply(*spot))


class StatusPanel(Static):
    """City status — population, treasury, tax rate, month/year."""

    def __init__(self, s: sim.Sim) -> None:
        super().__init__()
        self.sim = s
        self.border_title = "CITY STATUS"
        self._last_snapshot: tuple | None = None

    def refresh_panel(self) -> None:
        c = self.sim.city
        snap = (c.population, c.treasury, c.tax_rate, c.month, c.year,
                self.sim.building_count)
        if snap == self._last_snapshot:
            return
        self._last_snapshot = snap

        year_label = f"{abs(c.year)} {'BC' if c.year < 0 else 'AD'}"
        t = Text()
        t.append(f"{c.name}\n", style="bold yellow")
        t.append(f"{sim.MONTH_NAMES[c.month]} {year_label}\n\n", style="dim")
        t.append(f"Population    {c.population:>6,}\n", style="bold green")
        t.append(f"Treasury      {c.treasury:>6,} dn\n",
                 style="bold yellow" if c.treasury >= 0 else "bold red")
        t.append(f"Tax rate         {c.tax_rate:>3d}%\n")
        t.append(f"Buildings     {self.sim.building_count:>6}\n")
        self.update(t)


class RatingsPanel(Static):
    """Culture / Prosperity / Peace / Favor bars."""

    def __init__(self, s: sim.Sim) -> None:
        super().__init__()
        self.sim = s
        self.border_title = "RATINGS"
        self._last_snapshot: tuple | None = None

    _FILLED = "█"
    _EMPTY = "░"

    def _bar(self, val: int, width: int = 12) -> Text:
        n = max(0, min(width, val * width // 100))
        t = Text()
        t.append(self._FILLED * n, style="bold")
        t.append(self._EMPTY * (width - n), style="rgb(70,70,70)")
        return t

    def refresh_panel(self) -> None:
        c = self.sim.city
        snap = (c.rating_culture, c.rating_prosperity,
                c.rating_peace, c.rating_favor)
        if snap == self._last_snapshot:
            return
        self._last_snapshot = snap
        t = Text()
        t.append("Culture     ", style="bold cyan")
        t.append_text(self._bar(c.rating_culture))
        t.append(f"  {c.rating_culture:>3d}\n")
        t.append("Prosperity  ", style="bold yellow")
        t.append_text(self._bar(c.rating_prosperity))
        t.append(f"  {c.rating_prosperity:>3d}\n")
        t.append("Peace       ", style="bold green")
        t.append_text(self._bar(c.rating_peace))
        t.append(f"  {c.rating_peace:>3d}\n")
        t.append("Favor       ", style="bold magenta")
        t.append_text(self._bar(c.rating_favor))
        t.append(f"  {c.rating_favor:>3d}\n")
        self.update(t)


class ToolsPanel(Static):
    """Clickable tool list."""

    class Selected(Message):
        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.border_title = "TOOLS"
        self.selected: int = 0

    def on_click(self, event: events.Click) -> None:
        idx = event.y
        if 0 <= idx < len(TOOLS):
            self.post_message(self.Selected(idx))

    def refresh_panel(self) -> None:
        t = Text()
        for i, tool in enumerate(TOOLS):
            prefix = "▶ " if i == self.selected else "  "
            t.append(prefix + tool.key + " ",
                     style="bold reverse" if i == self.selected else "")
            t.append(tool.glyph, style=tool.style or None)
            t.append(f" {tool.label:<18}",
                     style="bold" if i == self.selected else "")
            t.append("\n")
        t.append("\n")
        t.append_text(Text.from_markup(
            "[dim]arrows move · enter apply · click to place[/]\n"
            "[dim]p pause  t tutorial  l legend  ? help  q quit[/]"
        ))
        self.update(t)


class JuliusApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "Julius — Terminal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("t", "tutorial", "Tutorial"),
        Binding("l", "legend", "Legend"),
        Binding("question_mark", "help", "Help"),
        # priority=True so arrow keys and enter aren't consumed by the
        # scrollable MapView.
        Binding("enter", "apply_tool", "Apply", priority=True),
        Binding("space", "apply_tool", "Apply", show=False, priority=True),
        Binding("up",    "move_cursor(0,-1)", "↑", show=False, priority=True),
        Binding("down",  "move_cursor(0,1)",  "↓", show=False, priority=True),
        Binding("left",  "move_cursor(-1,0)", "←", show=False, priority=True),
        Binding("right", "move_cursor(1,0)",  "→", show=False, priority=True),
        *[Binding(tool.key, f"select_tool({i})", show=False)
          for i, tool in enumerate(TOOLS)],
    ]

    paused: reactive[bool] = reactive(False)

    def __init__(self, scenario: str = "fertilis") -> None:
        super().__init__()
        self.sim = sim.Sim(scenario=scenario)
        self.map_view = MapView(self.sim)
        self.status_panel = StatusPanel(self.sim)
        self.ratings_panel = RatingsPanel(self.sim)
        self.tools_panel = ToolsPanel()
        self.message_log = RichLog(id="log", highlight=False, markup=True,
                                   wrap=False, max_lines=500)
        self.message_log.border_title = "MESSAGE LOG"
        self.flash_bar = Static(" ", id="flash-bar")
        self._flash_timer = None
        self._last_month = -1

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="map-col"):
                yield self.map_view
                yield self.flash_bar
                yield self.message_log
            with Vertical(id="side"):
                yield self.status_panel
                yield self.ratings_panel
                yield self.tools_panel
        yield Footer()

    async def on_mount(self) -> None:
        self.map_view.border_title = f"{self.sim.city.name}  —  {sim.MAP_W}×{sim.MAP_H}"
        self.map_view.refresh_all_tiles()
        self.map_view.scroll_to_cursor()
        self.status_panel.refresh_panel()
        self.ratings_panel.refresh_panel()
        self.tools_panel.refresh_panel()
        self.log_msg("[bold yellow]Ave, Caesar![/] — welcome to Roma Nova.")
        self.log_msg("New? Press [bold]t[/] for tutorial or [bold]?[/] for keys.")
        self._show_hover_info(self.map_view.cursor_x, self.map_view.cursor_y,
                              force=True)
        self.set_interval(0.1, self.tick)
        self.set_interval(1.0, self.redraw_map)
        # 2 Hz animation — water ripples, cursor blink.
        self.set_interval(0.5, self.map_view.advance_animation)

    # --- lifecycle -----------------------------------------------------

    def tick(self) -> None:
        if self.paused:
            return
        self.sim.sim_tick()
        self.status_panel.refresh_panel()
        self.ratings_panel.refresh_panel()
        self.update_header()
        if self.sim.city.month != self._last_month:
            if self._last_month == 11 and self.sim.city.month == 0:
                year_label = (f"{abs(self.sim.city.year)} "
                              f"{'BC' if self.sim.city.year < 0 else 'AD'}")
                self.log_msg(
                    f"New year — [bold]{year_label}[/]. "
                    f"Pop {self.sim.city.population:,}  "
                    f"Treasury {self.sim.city.treasury} dn",
                    level="news",
                )
            self._last_month = self.sim.city.month
            # Drain the sim's message queue into the log.
            while self.sim.city.message_log:
                msg = self.sim.city.message_log.pop(0)
                self.log_msg(msg, level="money")

    def redraw_map(self) -> None:
        self.map_view.refresh_if_map_changed()

    def update_header(self) -> None:
        c = self.sim.city
        year_label = f"{abs(c.year)} {'BC' if c.year < 0 else 'AD'}"
        paused = " · ⏸ PAUSED" if self.paused else ""
        self.sub_title = (
            f"{sim.MONTH_NAMES[c.month]} {year_label}  ·  "
            f"{c.treasury:,} dn  ·  Pop {c.population:,}{paused}"
        )
        cx, cy = self.map_view.cursor_x, self.map_view.cursor_y
        bits, bid = self.sim.get_tile(cx, cy)
        if bid >= 0 and self.sim.buildings[bid] is not None:
            b = self.sim.buildings[bid]
            assert b is not None
            klass = tiles.building_class(b.type)
        else:
            klass = tiles.terrain_class(bits)
        self.map_view.border_title = (
            f"{c.name}  ·  cursor ({cx},{cy}) [{klass}]"
        )

    # --- logging -------------------------------------------------------

    _LOG_LEVELS = {
        "info":     ("ℹ ", "cyan"),
        "success":  ("✓ ", "green"),
        "warn":     ("⚠ ", "yellow"),
        "error":    ("✗ ", "red"),
        "money":    ("$ ", "yellow"),
        "news":     ("★ ", "magenta"),
    }

    def log_msg(self, msg: str, level: str = "info") -> None:
        c = self.sim.city
        year_label = f"{abs(c.year)}{'BC' if c.year < 0 else 'AD'}"
        stamp = f"[dim][{sim.MONTH_NAMES[c.month]} {year_label}][/]"
        icon, color = self._LOG_LEVELS.get(level, self._LOG_LEVELS["info"])
        self.message_log.write(f"{stamp} [bold {color}]{icon}[/]{msg}")

    def flash_status(self, msg: str, seconds: float = 1.5) -> None:
        self.flash_bar.update(Text.from_markup(msg))
        if self._flash_timer is not None:
            self._flash_timer.stop()

        def _clear():
            self._flash_timer = None
            self._show_hover_info(self.map_view.cursor_x, self.map_view.cursor_y,
                                  force=True)

        self._flash_timer = self.set_timer(seconds, _clear)

    def _show_hover_info(self, x: int, y: int, force: bool = False) -> None:
        if not force and self._flash_timer is not None:
            return
        bits, bid = self.sim.get_tile(x, y)
        if bid >= 0 and self.sim.buildings[bid] is not None:
            b = self.sim.buildings[bid]
            assert b is not None
            klass = tiles.building_class(b.type)
            extra = ""
            if b.type in sim._HOUSE_POPULATION:
                extra = f"  pop {b.house_population}"
        else:
            klass = tiles.terrain_class(bits)
            extra = ""
        style = tiles.style_for(klass)
        glyph = tiles.glyph_for(klass, x, y)
        self.flash_bar.update(Text.from_markup(
            f"[{style}] {glyph} [/]  ({x},{y})  [bold]{klass}[/]{extra}"
        ))

    # --- actions -------------------------------------------------------

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        self.flash_status("[yellow]⏸ paused[/]" if self.paused
                          else "[green]▶ resumed[/]")
        self.update_header()

    def action_move_cursor(self, dx: str, dy: str) -> None:
        cx = max(0, min(sim.MAP_W - 1, self.map_view.cursor_x + int(dx)))
        cy = max(0, min(sim.MAP_H - 1, self.map_view.cursor_y + int(dy)))
        self.map_view.cursor_x = cx
        self.map_view.cursor_y = cy
        self.update_header()
        self._show_hover_info(cx, cy)

    def action_select_tool(self, idx: str) -> None:
        i = int(idx)
        if 0 <= i < len(TOOLS):
            self.tools_panel.selected = i
            self.tools_panel.refresh_panel()
            self.flash_status(f"Tool: [bold]{TOOLS[i].label}[/]")

    def action_apply_tool(self) -> None:
        tool = TOOLS[self.tools_panel.selected]
        cx, cy = self.map_view.cursor_x, self.map_view.cursor_y
        # Vacant-lot placement has its own entry point so it behaves
        # like Caesar III's "housing lot" — plant, wait for immigrants.
        if tool.building == sim.BUILDING_HOUSE_VACANT_LOT:
            result = self.sim.place_house(cx, cy)
        else:
            result = self.sim.do_tool(tool.building, cx, cy)
        if result == sim.TOOLRESULT_OK:
            self.flash_status(f"[green]✓ {tool.label}[/] @ ({cx},{cy})")
        elif result == sim.TOOLRESULT_NO_MONEY:
            self.flash_status(f"[red]✗ not enough denarii[/] for {tool.label}")
        elif result == sim.TOOLRESULT_NEED_CLEAR:
            self.flash_status("[red]✗ tile needs clearing first[/]")
        elif result == sim.TOOLRESULT_OUT_OF_BOUNDS:
            self.flash_status("[red]✗ outside the city boundary[/]")
        else:
            self.flash_status(f"[red]✗ can't place {tool.label} here[/]")
        self.map_view.refresh_all_tiles()
        self.status_panel.refresh_panel()
        self.update_header()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_tutorial(self) -> None:
        self.push_screen(TutorialScreen())

    def action_legend(self) -> None:
        self.push_screen(LegendScreen())

    def on_tools_panel_selected(self, message: ToolsPanel.Selected) -> None:
        self.action_select_tool(str(message.index))

    def on_map_view_tool_apply(self, message: MapView.ToolApply) -> None:
        # Mouse click — apply at the click location.
        self.action_apply_tool()


def run(scenario: str = "fertilis") -> None:
    app = JuliusApp(scenario=scenario)
    try:
        app.run()
    finally:
        import sys
        # Reset terminal mouse tracking — see simcity-tui's app.py for
        # why this belt-and-suspenders block matters.
        sys.stdout.write(
            "\033[?1000l\033[?1002l\033[?1003l\033[?1006l\033[?1015l\033[?25h"
        )
        sys.stdout.flush()
