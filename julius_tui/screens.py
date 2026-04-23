"""Modal screens — Help, Tutorial, Legend.

Kept minimal for MVP; richer advisor/budget screens can follow the
simcity-tui playbook (ModalScreen subclasses with `+`/`-` editing keys
and a `Static` body).
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_TEXT = """[bold yellow]Julius TUI — Keybindings[/]

[bold]Movement[/]
  arrows      move cursor
  enter       place building at cursor
  space       same as enter

[bold]Building tools[/]
  1           road
  2           vacant house lot
  3           well (water service)
  4           market (food service)
  5           small temple (religion)
  6           amphitheatre (entertainment)
  7           prefecture (fire/crime)
  8           wheat farm (place on meadow)
  9           forum (tax collection)
  0           bulldoze

[bold]Game[/]
  p           pause / resume
  o           cycle service overlay
  F2          save game
  F3          load game
  t           tutorial
  l           legend
  ?           this help
  q           quit

Press [bold]escape[/] to close this dialog.
"""

_TUTORIAL_TEXT = """[bold yellow]Tutorial — Your First City[/]

Caesar has entrusted you with a new province. Here is the short version:

1. [bold]Roads first.[/] Press [bold]1[/] and place a line of roads
   from the edge inward. Immigrants arrive along roads.

2. [bold]Housing lots.[/] Press [bold]2[/] and place several vacant
   lots along your road. They start as [yellow]tents[/]; people move
   in over time.

3. [bold]Water.[/] Every house above tent level needs water in range.
   Press [bold]3[/] and place a [cyan]well[/] near your lots. Coverage
   radius is 3 tiles.

4. [bold]Food.[/] Place a [green]wheat farm[/] with [bold]8[/] on
   meadow tiles (the bright-green ones). Then a [orange]market[/]
   with [bold]4[/] inside the housing area so people can buy food.

5. [bold]Religion.[/] A [bold]5[/] temple lifts houses into the
   casa tier. Amphitheatre [bold]6[/] is the next step.

Watch the [bold]population[/] number climb in the status panel.
If you run out of denarii, raise taxes from the city status panel
(not yet editable in this MVP — Caesar provides).

Press [bold]escape[/] to close.
"""

_LEGEND_TEXT = """[bold yellow]Map Legend[/]

[bold]Terrain[/]
  [rgb(95,75,45)]. ,[/]  dirt / empty       [rgb(70,130,200)]~ ≈[/]  water
  [rgb(40,140,40)]♣ ^[/]  trees              [bold rgb(160,200,70)]" '[/]  meadow (farmable)
  [rgb(120,115,110)]▲[/]   rocks              [bold rgb(100,200,100)]♦ ♣[/]  garden

[bold]Infrastructure[/]
  [rgb(180,170,130)]─[/]   road               [bold rgb(120,170,220)]═[/]  aqueduct

[bold]Housing (evolution tiers)[/]
  [rgb(140,110,70)]░[/]   tent              [rgb(200,160,100)]▓[/]  hovel
  [rgb(220,180,120)]▒[/]   casa              [bold rgb(230,200,150)]█[/]  insula
  [bold rgb(240,220,180)]▓[/]   villa             [bold rgb(255,240,210)]█[/]  palace

[bold]Civic[/]
  [bold rgb(120,180,230)]○[/]   well              [bold rgb(150,210,255)]◉[/]  fountain
  [bold rgb(220,80,80)]◈[/]   prefecture        [bold rgb(200,200,100)]⚙[/]  engineer's post
  [bold rgb(230,150,80)]▤[/]   market            [bold rgb(240,230,140)]✝[/]  temple
  [bold rgb(230,170,230)]◎[/]   amphitheatre      [bold rgb(240,220,160)]⌂[/]  senate
  [bold rgb(220,200,140)]☗[/]   forum             [bold rgb(240,210,90)]※[/]  wheat farm

Press [bold]escape[/] to close.
"""


class _ModalText(ModalScreen):
    """Common base — shows a single Static text block, closes on escape."""

    BINDINGS = [("escape", "app.pop_screen", "Close")]

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self):
        with Vertical():
            yield Static(self._text, id="body")


class HelpScreen(_ModalText):
    def __init__(self) -> None:
        super().__init__(_HELP_TEXT)


class TutorialScreen(_ModalText):
    def __init__(self) -> None:
        super().__init__(_TUTORIAL_TEXT)


class LegendScreen(_ModalText):
    def __init__(self) -> None:
        super().__init__(_LEGEND_TEXT)
