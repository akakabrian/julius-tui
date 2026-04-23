"""Terrain / building → (glyph, class, style) lookup.

Rendering philosophy matches simcity-tui (see that project's tiles.py):

- 2-glyph pattern per tile class keyed on `(x + y) & 1` so the map
  reads as textured patterns, not letter spam.
- Brightness budget: terrain dim, infrastructure medium, housing +
  civic bright. Cursor + alerts highest.
- Single-cell Unicode symbols only in the grid (`⌂ ◈ ⚙ ♨ ⚓`). Real
  emoji are double-width and shift alignment — forbidden in tiles.
- Foreground + background colours both set; bg is a near-black tint
  that establishes category without fighting the fg glyph.
"""

from __future__ import annotations

from . import sim

# ---- Terrain classes (derived from terrain bitfield) ------------------

# When multiple bits are set, we pick the one most visually dominant —
# ROAD beats MEADOW; BUILDING beats everything (handled separately
# because buildings have their own type lookup).

_TERRAIN_ORDER = [
    (sim.TERRAIN_WATER, "water"),
    (sim.TERRAIN_ROCK, "rock"),
    (sim.TERRAIN_ROAD, "road"),
    (sim.TERRAIN_GARDEN, "garden"),
    (sim.TERRAIN_AQUEDUCT, "aqueduct"),
    (sim.TERRAIN_TREE, "tree"),
    (sim.TERRAIN_SHRUB, "shrub"),
    (sim.TERRAIN_MEADOW, "meadow"),
    (sim.TERRAIN_RUBBLE, "rubble"),
]


def terrain_class(bits: int) -> str:
    for flag, klass in _TERRAIN_ORDER:
        if bits & flag:
            return klass
    return "dirt"


# ---- Building-type classes --------------------------------------------

# Maps sim.BUILDING_* → short class key used for glyph/style lookup.
_BUILDING_CLASS = {
    sim.BUILDING_ROAD:            "road",
    sim.BUILDING_HOUSE_TENT:      "house_tent",
    sim.BUILDING_HOUSE_SHACK:     "house_shack",
    sim.BUILDING_HOUSE_HOVEL:     "house_hovel",
    sim.BUILDING_HOUSE_CASA:      "house_casa",
    sim.BUILDING_HOUSE_INSULA:    "house_insula",
    sim.BUILDING_HOUSE_VILLA:     "house_villa",
    sim.BUILDING_HOUSE_PALACE:    "house_palace",
    sim.BUILDING_WELL:            "well",
    sim.BUILDING_FOUNTAIN:        "fountain",
    sim.BUILDING_PREFECTURE:      "prefect",
    sim.BUILDING_ENGINEERS_POST:  "engineer",
    sim.BUILDING_MARKET:          "market",
    sim.BUILDING_SMALL_TEMPLE:    "temple",
    sim.BUILDING_AMPHITHEATER:    "amphi",
    sim.BUILDING_SENATE:          "senate",
    sim.BUILDING_FORUM:           "forum",
    sim.BUILDING_GARDENS:         "garden",
    sim.BUILDING_PLAZA:           "plaza",
    sim.BUILDING_SMALL_STATUE:    "statue",
    sim.BUILDING_WHEAT_FARM:      "farm_wheat",
    sim.BUILDING_VEGETABLE_FARM:  "farm_veg",
}


def building_class(btype: int) -> str:
    return _BUILDING_CLASS.get(btype, "unknown")


# ---- Glyph patterns ---------------------------------------------------

# 2-glyph pattern per class; render_line picks pattern[(x+y)&1].
# Classes without a pattern fall back to _SINGLE_GLYPH.
_PATTERN: dict[str, tuple[str, str]] = {
    "dirt":          (".", ","),
    "water":         ("~", "≈"),
    "tree":          ("♣", "^"),
    "shrub":         ("·", "ˑ"),
    "meadow":        ('"', "'"),
    "rubble":        ("▒", "░"),
    "road":          ("─", "─"),
    "garden":        ("♦", "♣"),
    "aqueduct":      ("═", "═"),
    # Housing — shading escalates with tier.
    "house_tent":    (".", "░"),
    "house_shack":   ("░", "▒"),
    "house_hovel":   ("▒", "▓"),
    "house_casa":    ("▓", "▒"),
    "house_insula":  ("█", "▓"),
    "house_villa":   ("▓", "█"),
    "house_palace":  ("█", "█"),
}

_SINGLE_GLYPH: dict[str, str] = {
    "rock":     "▲",
    "well":     "○",
    "fountain": "◉",
    "prefect":  "◈",     # shield
    "engineer": "⚙",     # gear
    "market":   "▤",
    "temple":   "✝",     # stand-in for pagan column
    "amphi":    "◎",     # ring
    "senate":   "⌂",     # big-house glyph
    "forum":    "☗",     # classical building
    "plaza":    "▦",
    "statue":   "♞",
    "farm_wheat": "※",   # wheat sheaf proxy
    "farm_veg":   "✿",   # carrot flower
    "unknown":  "?",
}


def glyph_for(klass: str, x: int, y: int) -> str:
    pattern = _PATTERN.get(klass)
    if pattern is not None:
        return pattern[(x + y) & 1]
    return _SINGLE_GLYPH.get(klass, "?")


# ---- Colours ----------------------------------------------------------

# Foreground (main glyph colour).
COLOR: dict[str, str] = {
    # Terrain — dim.
    "dirt":     "rgb(95,75,45)",
    "water":    "rgb(70,130,200)",
    "rock":     "rgb(120,115,110)",
    "tree":     "rgb(40,140,40)",
    "shrub":    "rgb(80,120,50)",
    "meadow":   "bold rgb(160,200,70)",  # the wheat-farm colour
    "rubble":   "rgb(110,80,60)",
    # Infrastructure — medium.
    "road":     "rgb(180,170,130)",
    "garden":   "bold rgb(100,200,100)",
    "aqueduct": "bold rgb(120,170,220)",
    "plaza":    "rgb(200,190,160)",
    "statue":   "bold rgb(230,220,200)",
    # Housing ladder — progressively warmer + brighter.
    "house_tent":   "rgb(140,110,70)",
    "house_shack":  "rgb(170,140,90)",
    "house_hovel":  "rgb(200,160,100)",
    "house_casa":   "rgb(220,180,120)",
    "house_insula": "bold rgb(230,200,150)",
    "house_villa":  "bold rgb(240,220,180)",
    "house_palace": "bold rgb(255,240,210)",
    # Services / civic — bright.
    "well":     "bold rgb(120,180,230)",
    "fountain": "bold rgb(150,210,255)",
    "prefect":  "bold rgb(220,80,80)",     # Red for law & order
    "engineer": "bold rgb(200,200,100)",
    "market":   "bold rgb(230,150,80)",
    "temple":   "bold rgb(240,230,140)",   # Pale gold
    "amphi":    "bold rgb(230,170,230)",
    "senate":   "bold rgb(240,220,160)",
    "forum":    "bold rgb(220,200,140)",
    "farm_wheat": "bold rgb(240,210,90)",
    "farm_veg":   "bold rgb(220,120,160)",
    "unknown":  "bold rgb(255,0,255)",
}

# Background — near-black tints to establish category without fighting fg.
BG: dict[str, str] = {
    "dirt":     "rgb(28,22,12)",
    "water":    "rgb(8,20,45)",
    "rock":     "rgb(30,28,26)",
    "tree":     "rgb(10,25,10)",
    "shrub":    "rgb(15,22,10)",
    "meadow":   "rgb(25,38,12)",
    "rubble":   "rgb(35,22,15)",
    "road":     "rgb(22,18,10)",
    "garden":   "rgb(15,38,18)",
    "aqueduct": "rgb(12,25,40)",
    "plaza":    "rgb(35,30,20)",
    "statue":   "rgb(28,26,22)",
    # Housing — backgrounds get slightly warmer with tier.
    "house_tent":   "rgb(30,22,12)",
    "house_shack":  "rgb(35,25,14)",
    "house_hovel":  "rgb(40,28,16)",
    "house_casa":   "rgb(45,32,18)",
    "house_insula": "rgb(50,36,22)",
    "house_villa":  "rgb(55,42,28)",
    "house_palace": "rgb(60,48,32)",
    # Civic backgrounds get a tint matching the service.
    "well":     "rgb(15,25,40)",
    "fountain": "rgb(18,32,52)",
    "prefect":  "rgb(45,15,15)",
    "engineer": "rgb(40,38,15)",
    "market":   "rgb(45,28,12)",
    "temple":   "rgb(45,40,15)",
    "amphi":    "rgb(40,25,45)",
    "senate":   "rgb(42,35,18)",
    "forum":    "rgb(40,32,16)",
    "farm_wheat": "rgb(40,34,10)",
    "farm_veg":   "rgb(40,18,30)",
    "unknown":  "rgb(40,0,40)",
}


def style_for(klass: str) -> str:
    fg = COLOR.get(klass, "rgb(255,0,255)")
    bg = BG.get(klass, "rgb(0,0,0)")
    return f"{fg} on {bg}"


