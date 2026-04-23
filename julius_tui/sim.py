"""Pure-Python simulation inspired by the Julius engine.

Design notes:

- **Terrain bit flags** mirror `engine/src/map/terrain.h` — each tile
  carries a bitfield indicating what's on it (road, water, tree, garden,
  building, etc.). Buildings set TERRAIN_BUILDING plus an index into the
  buildings list.
- **Building types** mirror the relevant subset of
  `engine/src/building/type.h`. We cover terrain-changers (road, garden,
  plaza), housing (the 20-step tent→palace evolution chain), the core
  civic services (well, fountain, prefecture, engineer's post, market),
  farms (wheat, vegetable), a temple, and a forum/senate for taxes.
- **House evolution** is a simplified version of Julius's
  `engine/src/building/house_evolution.c`: each tick a house checks
  whether it has the required services in range (water, food, religion,
  entertainment, education). When it does, the level increases by one.
  When a critical service is missing for too long, it devolves.
- **Treasury** ticks monthly via a `finance.c`-ish model: housing pays
  tax (rate × population), farms and workshops produce goods sold at
  forum, wages deducted from workforce count.

Tick cadence matches Julius's internal clock: 50 sub-ticks per game
month, 12 months per year. The TUI drives `tick()` at 10 Hz → one game
month per ~5 seconds, which feels right for a terminal pace.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

# ---- Map dimensions ---------------------------------------------------

# Julius uses 162×162; we scale down for responsive pure-Python sim.
# See DECISIONS.md. 80×80 keeps gameplay snappy at Python speed.
MAP_W = 80
MAP_H = 80

# ---- Terrain bit flags (mirrors engine/src/map/terrain.h) -------------

TERRAIN_NONE = 0
TERRAIN_TREE = 0x001
TERRAIN_ROCK = 0x002
TERRAIN_WATER = 0x004
TERRAIN_BUILDING = 0x008
TERRAIN_SHRUB = 0x010
TERRAIN_GARDEN = 0x020
TERRAIN_ROAD = 0x040
TERRAIN_AQUEDUCT = 0x100
TERRAIN_MEADOW = 0x800
TERRAIN_RUBBLE = 0x1000
TERRAIN_FOUNTAIN_RANGE = 0x2000
TERRAIN_WELL_RANGE = 0x4000  # Julius uses reservoir_range; we repurpose
TERRAIN_CLEARABLE = (TERRAIN_TREE | TERRAIN_SHRUB | TERRAIN_GARDEN
                     | TERRAIN_ROAD | TERRAIN_BUILDING | TERRAIN_RUBBLE
                     | TERRAIN_AQUEDUCT)

# ---- Building types (subset of engine/src/building/type.h) ------------

# Kept as int enum-style constants so we can cheaply tag tiles.
BUILDING_NONE = 0
BUILDING_ROAD = 5
BUILDING_HOUSE_VACANT_LOT = 10
# Housing ladder mirrors the 20-level Julius chain. We model the main
# tiers as checkpoints; intermediate sub-tiers are rendered the same.
BUILDING_HOUSE_TENT = 11
BUILDING_HOUSE_SHACK = 13
BUILDING_HOUSE_HOVEL = 15
BUILDING_HOUSE_CASA = 17
BUILDING_HOUSE_INSULA = 19
BUILDING_HOUSE_VILLA = 23
BUILDING_HOUSE_PALACE = 27
# Services
BUILDING_WELL = 70
BUILDING_FOUNTAIN = 71
BUILDING_PREFECTURE = 55
BUILDING_ENGINEERS_POST = 100
BUILDING_MARKET = 86
# Farms
BUILDING_WHEAT_FARM = 75
BUILDING_VEGETABLE_FARM = 76
# Religion / Culture
BUILDING_SMALL_TEMPLE = 60
BUILDING_AMPHITHEATER = 30
# Government
BUILDING_SENATE = 175
BUILDING_FORUM = 174
# Beautification
BUILDING_GARDENS = 39
BUILDING_PLAZA = 38
BUILDING_SMALL_STATUE = 41

# House level → building type (for rendering & evolution gates)
_HOUSE_LEVELS = [
    BUILDING_HOUSE_TENT,
    BUILDING_HOUSE_SHACK,
    BUILDING_HOUSE_HOVEL,
    BUILDING_HOUSE_CASA,
    BUILDING_HOUSE_INSULA,
    BUILDING_HOUSE_VILLA,
    BUILDING_HOUSE_PALACE,
]

# Population per house level — Julius numbers are higher per tile because
# their tiles are 1/4 of ours (iso sub-grid). We use rounded-up values.
_HOUSE_POPULATION = {
    BUILDING_HOUSE_TENT:   6,
    BUILDING_HOUSE_SHACK:  10,
    BUILDING_HOUSE_HOVEL:  16,
    BUILDING_HOUSE_CASA:   25,
    BUILDING_HOUSE_INSULA: 35,
    BUILDING_HOUSE_VILLA:  50,
    BUILDING_HOUSE_PALACE: 80,
}

# Per Julius: each level demands progressively more services.
# Bit flags for service requirements.
SVC_WATER       = 0x01
SVC_FOOD        = 0x02
SVC_RELIGION    = 0x04
SVC_ENTERTAIN   = 0x08
SVC_EDUCATION   = 0x10

# Level → required service mask. Tents are happy with nothing;
# each tier up adds a need.
_HOUSE_REQUIREMENTS = {
    BUILDING_HOUSE_TENT:   0,
    BUILDING_HOUSE_SHACK:  SVC_WATER,
    BUILDING_HOUSE_HOVEL:  SVC_WATER | SVC_FOOD,
    BUILDING_HOUSE_CASA:   SVC_WATER | SVC_FOOD | SVC_RELIGION,
    BUILDING_HOUSE_INSULA: SVC_WATER | SVC_FOOD | SVC_RELIGION | SVC_ENTERTAIN,
    BUILDING_HOUSE_VILLA:  SVC_WATER | SVC_FOOD | SVC_RELIGION | SVC_ENTERTAIN | SVC_EDUCATION,
    BUILDING_HOUSE_PALACE: SVC_WATER | SVC_FOOD | SVC_RELIGION | SVC_ENTERTAIN | SVC_EDUCATION,
}

# Which buildings provide which services, and the radius they cover.
# Numbers tuned so a small city with two of each service buildings works.
_SVC_PROVIDERS = {
    BUILDING_WELL:           (SVC_WATER,     3),
    BUILDING_FOUNTAIN:       (SVC_WATER,     6),
    BUILDING_MARKET:         (SVC_FOOD,      5),
    BUILDING_SMALL_TEMPLE:   (SVC_RELIGION,  7),
    BUILDING_AMPHITHEATER:   (SVC_ENTERTAIN, 8),
}

# ---- Building footprints (in tiles, square) --------------------------

_FOOTPRINT = {
    BUILDING_ROAD:             1,
    BUILDING_GARDENS:          1,
    BUILDING_PLAZA:            1,
    BUILDING_HOUSE_VACANT_LOT: 1,
    BUILDING_WELL:             1,
    BUILDING_PREFECTURE:       1,
    BUILDING_ENGINEERS_POST:   1,
    BUILDING_SMALL_STATUE:     1,
    BUILDING_FOUNTAIN:         1,
    BUILDING_SMALL_TEMPLE:     2,
    BUILDING_MARKET:           2,
    BUILDING_AMPHITHEATER:     3,
    BUILDING_SENATE:           5,
    BUILDING_FORUM:            2,
    BUILDING_WHEAT_FARM:       3,
    BUILDING_VEGETABLE_FARM:   3,
}

# Cost per placement (denarii) — tuned to roughly match Julius.
_COST = {
    BUILDING_ROAD:            4,
    BUILDING_GARDENS:         12,
    BUILDING_PLAZA:           15,
    BUILDING_SMALL_STATUE:    12,
    BUILDING_WELL:            5,
    BUILDING_FOUNTAIN:        15,
    BUILDING_PREFECTURE:      30,
    BUILDING_ENGINEERS_POST:  30,
    BUILDING_MARKET:          40,
    BUILDING_SMALL_TEMPLE:    50,
    BUILDING_AMPHITHEATER:    100,
    BUILDING_SENATE:          400,
    BUILDING_FORUM:           75,
    BUILDING_WHEAT_FARM:      40,
    BUILDING_VEGETABLE_FARM:  40,
    BUILDING_HOUSE_VACANT_LOT: 10,
}

# Tool result codes — mirror Julius's conventions.
TOOLRESULT_OK = 1
TOOLRESULT_FAILED = 0
TOOLRESULT_NEED_CLEAR = -1
TOOLRESULT_NO_MONEY = -2
TOOLRESULT_OUT_OF_BOUNDS = -3


# ---- Months & rating aliases ------------------------------------------

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Building:
    """A placed structure. Mirrors a subset of Julius's building_t."""
    id: int
    type: int
    x: int
    y: int
    size: int  # footprint edge length in tiles
    # House-specific. Level is index into _HOUSE_LEVELS.
    house_level: int = 0
    house_population: int = 0
    # How long (in ticks) a house has been without a required service.
    devolve_pressure: int = 0
    # Work-building specific.
    active: bool = True


@dataclass
class City:
    """Top-level city state. Julius equivalent: city/data.c."""
    name: str = "Roma Nova"
    treasury: int = 2500       # starting denarii — mirrors campaign level 1
    tax_rate: int = 7          # percent (Julius default)
    month: int = 0             # 0..11
    year: int = -50            # BC; rollover handled in tick
    sub_tick: int = 0          # 0..49 within a month
    population: int = 0
    rating_culture: int = 0
    rating_prosperity: int = 0
    rating_peace: int = 50     # Julius starts Peace at 50
    rating_favor: int = 50
    message_log: list[str] = field(default_factory=list)


class Sim:
    """Top-level simulation. Public API mirrors Micropolis's simTick /
    getTile / doTool so the TUI can swap almost unchanged from
    simcity-tui's shape."""

    # --- lifecycle -----------------------------------------------------

    def __init__(self, scenario: str = "fertilis", *, seed: int = 42) -> None:
        self.city = City(name="Roma Nova")
        self.rng = random.Random(seed)
        # Flat bitfield grid — row-major (y * W + x). Julius uses
        # column-major for some buffers, row-major for others; we pick
        # row-major throughout for simplicity.
        self.terrain = bytearray(MAP_W * MAP_H * 2)  # uint16 per cell
        # Building index grid — which building (if any) is at each tile.
        self.building_at = [-1] * (MAP_W * MAP_H)
        # Full building list. id == index; None marks a destroyed slot
        # (kept as a hole so existing ids stay stable).
        self.buildings: list[Optional[Building]] = []
        # Service coverage grids — recomputed on every monthly tick.
        self.service_mask = bytearray(MAP_W * MAP_H)
        # Bumped on any terrain write so the TUI can skip redraws.
        self.map_serial: int = 0
        self._scenario = scenario
        self._build_scenario(scenario)
        # Seed an initial service-coverage pass so first render is accurate.
        self._recompute_service_coverage()

    def _build_scenario(self, scenario: str) -> None:
        """Populate the map with terrain features. 'fertilis' (the
        default) gives a river across the top, some meadow patches for
        farms, and scattered trees/rocks."""
        rng = self.rng
        # River across rows 2–6, with some curvature.
        for y in range(2, 7):
            for x in range(MAP_W):
                # Curved river — sine-ish offset
                offset = int(2 * ((x * 0.07) % 6.28 - 3.14))
                if y + offset in range(2, 7):
                    self._set_terrain(x, y, TERRAIN_WATER)
        # Meadow patches — perfect for wheat farms.
        for _ in range(18):
            cx = rng.randint(5, MAP_W - 6)
            cy = rng.randint(10, MAP_H - 6)
            r = rng.randint(3, 6)
            for y in range(max(0, cy - r), min(MAP_H, cy + r)):
                for x in range(max(0, cx - r), min(MAP_W, cx + r)):
                    if (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                        # Don't overwrite water.
                        if self._get_terrain(x, y) == TERRAIN_NONE:
                            self._set_terrain(x, y, TERRAIN_MEADOW)
        # Trees — classic Caesar III "forested Italian countryside".
        for _ in range(180):
            x = rng.randint(0, MAP_W - 1)
            y = rng.randint(0, MAP_H - 1)
            if self._get_terrain(x, y) == TERRAIN_NONE:
                self._set_terrain(x, y, TERRAIN_TREE)
        # Rocks — blockers.
        for _ in range(40):
            x = rng.randint(0, MAP_W - 1)
            y = rng.randint(0, MAP_H - 1)
            if self._get_terrain(x, y) == TERRAIN_NONE:
                self._set_terrain(x, y, TERRAIN_ROCK)
        # Shrubs for flavour.
        for _ in range(120):
            x = rng.randint(0, MAP_W - 1)
            y = rng.randint(0, MAP_H - 1)
            if self._get_terrain(x, y) == TERRAIN_NONE:
                self._set_terrain(x, y, TERRAIN_SHRUB)

    # --- terrain accessors --------------------------------------------

    def _idx(self, x: int, y: int) -> int:
        return y * MAP_W + x

    def _set_terrain(self, x: int, y: int, bits: int) -> None:
        i = self._idx(x, y) * 2
        self.terrain[i] = bits & 0xFF
        self.terrain[i + 1] = (bits >> 8) & 0xFF
        self.map_serial += 1

    def _add_terrain(self, x: int, y: int, bits: int) -> None:
        self._set_terrain(x, y, self._get_terrain(x, y) | bits)

    def _clear_terrain(self, x: int, y: int, bits: int) -> None:
        self._set_terrain(x, y, self._get_terrain(x, y) & ~bits)

    def _get_terrain(self, x: int, y: int) -> int:
        i = self._idx(x, y) * 2
        return self.terrain[i] | (self.terrain[i + 1] << 8)

    def get_tile(self, x: int, y: int) -> tuple[int, int]:
        """Return (terrain_bits, building_id_or_-1) for the tile."""
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return (0, -1)
        return (self._get_terrain(x, y), self.building_at[self._idx(x, y)])

    def building_type_at(self, x: int, y: int) -> int:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return BUILDING_NONE
        bid = self.building_at[self._idx(x, y)]
        if bid < 0 or bid >= len(self.buildings):
            return BUILDING_NONE
        b = self.buildings[bid]
        return b.type if b else BUILDING_NONE

    # --- building placement --------------------------------------------

    def _tile_is_clear(self, x: int, y: int) -> bool:
        bits = self._get_terrain(x, y)
        return (bits & TERRAIN_CLEARABLE) == 0 and (bits & TERRAIN_WATER) == 0 \
            and (bits & TERRAIN_ROCK) == 0

    def _footprint_clear(self, x: int, y: int, size: int) -> bool:
        for dy in range(size):
            for dx in range(size):
                tx, ty = x + dx, y + dy
                if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
                    return False
                if not self._tile_is_clear(tx, ty):
                    return False
        return True

    def do_tool(self, building_type: int, x: int, y: int) -> int:
        """Place / remove a building. Mirrors Julius's
        building_construction_place_building()."""
        if building_type == BUILDING_NONE:
            return self._bulldoze(x, y)
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return TOOLRESULT_OUT_OF_BOUNDS
        if building_type == BUILDING_ROAD:
            return self._place_road(x, y)
        if building_type == BUILDING_GARDENS:
            return self._place_garden(x, y)
        if building_type == BUILDING_PLAZA:
            return self._place_plaza(x, y)
        # Generic footprint building.
        size = _FOOTPRINT.get(building_type, 1)
        cost = _COST.get(building_type, 0)
        if self.city.treasury < cost:
            return TOOLRESULT_NO_MONEY
        if not self._footprint_clear(x, y, size):
            return TOOLRESULT_NEED_CLEAR
        bid = self._alloc_building(building_type, x, y, size)
        # Mark all tiles.
        for dy in range(size):
            for dx in range(size):
                self._add_terrain(x + dx, y + dy, TERRAIN_BUILDING)
                self.building_at[self._idx(x + dx, y + dy)] = bid
        self.city.treasury -= cost
        return TOOLRESULT_OK

    def _place_road(self, x: int, y: int) -> int:
        bits = self._get_terrain(x, y)
        if bits & TERRAIN_ROAD:
            return TOOLRESULT_FAILED  # already a road
        if bits & (TERRAIN_BUILDING | TERRAIN_WATER | TERRAIN_ROCK):
            return TOOLRESULT_NEED_CLEAR
        if self.city.treasury < _COST[BUILDING_ROAD]:
            return TOOLRESULT_NO_MONEY
        # Roads can flatten trees/shrubs/meadow.
        self._clear_terrain(x, y, TERRAIN_TREE | TERRAIN_SHRUB | TERRAIN_MEADOW)
        self._add_terrain(x, y, TERRAIN_ROAD)
        self.city.treasury -= _COST[BUILDING_ROAD]
        return TOOLRESULT_OK

    def _place_garden(self, x: int, y: int) -> int:
        bits = self._get_terrain(x, y)
        if bits & (TERRAIN_GARDEN | TERRAIN_BUILDING | TERRAIN_WATER
                   | TERRAIN_ROCK | TERRAIN_ROAD):
            return TOOLRESULT_NEED_CLEAR
        if self.city.treasury < _COST[BUILDING_GARDENS]:
            return TOOLRESULT_NO_MONEY
        self._clear_terrain(x, y, TERRAIN_TREE | TERRAIN_SHRUB | TERRAIN_MEADOW)
        self._add_terrain(x, y, TERRAIN_GARDEN)
        self.city.treasury -= _COST[BUILDING_GARDENS]
        return TOOLRESULT_OK

    def _place_plaza(self, x: int, y: int) -> int:
        # Plaza requires an existing road.
        bits = self._get_terrain(x, y)
        if not (bits & TERRAIN_ROAD):
            return TOOLRESULT_FAILED
        if self.city.treasury < _COST[BUILDING_PLAZA]:
            return TOOLRESULT_NO_MONEY
        # We represent a plaza as a sub-bit alongside road.
        self._add_terrain(x, y, TERRAIN_GARDEN)  # reuse garden bit for render
        self.city.treasury -= _COST[BUILDING_PLAZA]
        return TOOLRESULT_OK

    def _alloc_building(self, type_: int, x: int, y: int, size: int) -> int:
        bid = len(self.buildings)
        pop = _HOUSE_POPULATION.get(type_, 0)
        self.buildings.append(Building(
            id=bid, type=type_, x=x, y=y, size=size,
            house_level=0, house_population=pop,
        ))
        return bid

    def _bulldoze(self, x: int, y: int) -> int:
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return TOOLRESULT_OUT_OF_BOUNDS
        idx = self._idx(x, y)
        bid = self.building_at[idx]
        bits = self._get_terrain(x, y)
        if bid >= 0 and self.buildings[bid]:
            b = self.buildings[bid]
            assert b is not None  # checked above via buildings[bid]
            # Clear the full footprint.
            for dy in range(b.size):
                for dx in range(b.size):
                    ti = self._idx(b.x + dx, b.y + dy)
                    self.building_at[ti] = -1
                    self._set_terrain(b.x + dx, b.y + dy, TERRAIN_NONE)
            self.buildings[bid] = None
            return TOOLRESULT_OK
        if bits & (TERRAIN_ROAD | TERRAIN_TREE | TERRAIN_SHRUB
                   | TERRAIN_GARDEN | TERRAIN_AQUEDUCT | TERRAIN_RUBBLE):
            self._set_terrain(x, y, TERRAIN_NONE)
            return TOOLRESULT_OK
        if bits == 0:
            return TOOLRESULT_FAILED  # already clear
        return TOOLRESULT_FAILED

    # --- place a vacant-lot house (starts evolution) -------------------

    def place_house(self, x: int, y: int) -> int:
        """Drop a vacant lot; evolution will upgrade it as services come
        in range. This is how Caesar III housing works — the player
        plants a lot, immigrants move in and upgrade it over time."""
        if not (0 <= x < MAP_W and 0 <= y < MAP_H):
            return TOOLRESULT_OUT_OF_BOUNDS
        if self.city.treasury < _COST[BUILDING_HOUSE_VACANT_LOT]:
            return TOOLRESULT_NO_MONEY
        if not self._tile_is_clear(x, y):
            return TOOLRESULT_NEED_CLEAR
        bid = self._alloc_building(BUILDING_HOUSE_TENT, x, y, 1)
        self._add_terrain(x, y, TERRAIN_BUILDING)
        self.building_at[self._idx(x, y)] = bid
        # Tents start empty — population trickles in via monthly growth.
        self.buildings[bid].house_population = 0  # type: ignore[union-attr]
        self.city.treasury -= _COST[BUILDING_HOUSE_VACANT_LOT]
        return TOOLRESULT_OK

    # --- simulation tick -----------------------------------------------

    def sim_tick(self) -> None:
        """Advance the simulation by one sub-tick.

        Julius's model: 50 sub-ticks per month, 12 months per year.
        Housing evolution runs every sub-tick (cheap); service coverage
        recomputes at month boundaries (expensive)."""
        self._evolve_houses_sub_tick()
        self.city.sub_tick += 1
        if self.city.sub_tick >= 50:
            self.city.sub_tick = 0
            self._monthly_tick()

    def _monthly_tick(self) -> None:
        self._recompute_service_coverage()
        self._collect_taxes()
        self._pay_wages()
        self._update_ratings()
        self.city.month += 1
        if self.city.month >= 12:
            self.city.month = 0
            self.city.year += 1
            # Year chime is handled by the UI.
        self._recompute_population()

    def _recompute_service_coverage(self) -> None:
        """Flood-fill service coverage from every provider building.
        Uses Chebyshev distance (square radius) — matches the way
        Caesar III treats service range for simplicity."""
        mask = bytearray(MAP_W * MAP_H)
        for b in self.buildings:
            if b is None or not b.active:
                continue
            prov = _SVC_PROVIDERS.get(b.type)
            if prov is None:
                continue
            service, radius = prov
            # Centre of the building
            cx = b.x + b.size // 2
            cy = b.y + b.size // 2
            for dy in range(-radius, radius + 1):
                ty = cy + dy
                if not (0 <= ty < MAP_H):
                    continue
                for dx in range(-radius, radius + 1):
                    tx = cx + dx
                    if not (0 <= tx < MAP_W):
                        continue
                    mask[ty * MAP_W + tx] |= service
        self.service_mask = mask

    def _evolve_houses_sub_tick(self) -> None:
        """Check each house's services; upgrade/downgrade as appropriate.
        We gate evolution on (a) service bitmask match, (b) cooldown so
        it doesn't happen every sub-tick, (c) small RNG so houses in the
        same cluster don't all evolve on the same frame."""
        # Only evaluate a sampled subset per sub-tick — amortised cost.
        if not self.buildings:
            return
        stride = 5
        offset = self.city.sub_tick % stride
        for i in range(offset, len(self.buildings), stride):
            b = self.buildings[i]
            if b is None:
                continue
            if b.type not in _HOUSE_POPULATION:
                continue
            self._evolve_one(b)

    def _evolve_one(self, b: Building) -> None:
        idx = self._idx(b.x, b.y)
        have = self.service_mask[idx]
        need = _HOUSE_REQUIREMENTS.get(b.type, 0)
        current_level = _HOUSE_LEVELS.index(b.type) if b.type in _HOUSE_LEVELS else 0
        # Tent fills with people even without services. Higher tiers
        # require services to fill beyond base pop.
        target_pop = _HOUSE_POPULATION[b.type]
        if b.house_population < target_pop:
            # Population growth: small per-tick drift upward.
            if self.rng.random() < 0.08:
                b.house_population += 1
        # Evolution check: do we have ALL services the next level needs?
        if current_level + 1 < len(_HOUSE_LEVELS):
            next_type = _HOUSE_LEVELS[current_level + 1]
            next_need = _HOUSE_REQUIREMENTS[next_type]
            if (have & next_need) == next_need and b.house_population >= target_pop - 1:
                if self.rng.random() < 0.02:  # infrequent upgrade cadence
                    b.type = next_type
                    b.devolve_pressure = 0
                    self.map_serial += 1
                    return
        # Devolution — losing a required service ticks pressure up; if
        # sustained, drop a level.
        if (have & need) != need:
            b.devolve_pressure += 1
            if b.devolve_pressure > 40 and current_level > 0:
                b.type = _HOUSE_LEVELS[current_level - 1]
                b.devolve_pressure = 0
                self.map_serial += 1
        else:
            b.devolve_pressure = max(0, b.devolve_pressure - 1)

    def _collect_taxes(self) -> None:
        """Tax income = population × rate / base. Julius uses a lookup
        by tier; we approximate with per-capita × level multiplier."""
        income = 0
        for b in self.buildings:
            if b is None or b.type not in _HOUSE_POPULATION:
                continue
            tier_idx = _HOUSE_LEVELS.index(b.type) if b.type in _HOUSE_LEVELS else 0
            # Each tier pays more tax — villas/palaces drive economy.
            per_capita = 1 + tier_idx
            income += (b.house_population * per_capita * self.city.tax_rate) // 100
        if income > 0:
            self.city.treasury += income
            # Surface meaningful tax events so the UI can show them.
            # (Threshold prevents spammy 0-denarii logs on brand-new cities.)
            if income > 50 and self.city.month == 0:
                self.city.message_log.append(
                    f"Annual tax collection: {income}dn."
                )

    def _pay_wages(self) -> None:
        """Very simplified — staffed civic buildings each cost upkeep.
        Real Julius does per-worker wages; we bundle per-building."""
        upkeep = 0
        for b in self.buildings:
            if b is None:
                continue
            if b.type in (BUILDING_PREFECTURE, BUILDING_ENGINEERS_POST,
                          BUILDING_MARKET, BUILDING_SMALL_TEMPLE,
                          BUILDING_AMPHITHEATER, BUILDING_SENATE,
                          BUILDING_FORUM, BUILDING_FOUNTAIN,
                          BUILDING_WHEAT_FARM, BUILDING_VEGETABLE_FARM):
                upkeep += 2
        self.city.treasury -= upkeep

    def _recompute_population(self) -> None:
        total = 0
        for b in self.buildings:
            if b is None:
                continue
            if b.type in _HOUSE_POPULATION:
                total += b.house_population
        self.city.population = total

    def _update_ratings(self) -> None:
        """Culture rises with temples + amphitheatres; prosperity with
        housing tier; peace stable; favor drifts toward 50."""
        temples = sum(1 for b in self.buildings
                      if b is not None and b.type == BUILDING_SMALL_TEMPLE)
        amphis = sum(1 for b in self.buildings
                     if b is not None and b.type == BUILDING_AMPHITHEATER)
        culture_target = min(100, temples * 8 + amphis * 12)
        self.city.rating_culture += (1 if culture_target > self.city.rating_culture
                                     else -1 if culture_target < self.city.rating_culture else 0)

        # Prosperity tracks highest-tier housing. Villas/palaces make it climb.
        high_tier = sum(1 for b in self.buildings
                        if b is not None and b.type in (
                            BUILDING_HOUSE_VILLA, BUILDING_HOUSE_PALACE
                        ))
        prosperity_target = min(100, high_tier * 5 + self.city.treasury // 200)
        self.city.rating_prosperity += (1 if prosperity_target > self.city.rating_prosperity
                                        else -1 if prosperity_target < self.city.rating_prosperity else 0)

        # Favor drifts toward 50 slowly (no emperor events modelled yet).
        if self.city.rating_favor < 50:
            self.city.rating_favor += 1
        elif self.city.rating_favor > 50:
            self.city.rating_favor -= 1

    # --- convenience accessors ----------------------------------------

    @property
    def building_count(self) -> int:
        return sum(1 for b in self.buildings if b is not None)

    def state_snapshot(self) -> dict:
        """JSON-able dict of current state. Intended for an agent API
        phase, but also handy for tests."""
        return {
            "name": self.city.name,
            "year": self.city.year,
            "month": MONTH_NAMES[self.city.month],
            "population": self.city.population,
            "treasury": self.city.treasury,
            "tax_rate": self.city.tax_rate,
            "buildings": self.building_count,
            "rating_culture": self.city.rating_culture,
            "rating_prosperity": self.city.rating_prosperity,
            "rating_peace": self.city.rating_peace,
            "rating_favor": self.city.rating_favor,
        }
