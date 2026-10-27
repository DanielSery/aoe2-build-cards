"""
Civ-aware game data, loaded from `civdata.json` (see `tools/extract_dat.py`).

Everything here is read from the game's own `.dat`. The one thing that is a
judgement call is `JOB_UNITS` / `BUILDING_UNITS` below: mapping the sim's
vocabulary onto Genie unit ids. Those maps are by internal name and raise on a
miss rather than silently falling back, so a patch that renames something
fails the next load instead of quietly changing the numbers.

Gather rates here are the raw work rates from the .dat. They do NOT include
walking to and from the drop-off point, so a villager never achieves them in a
real game -- the walking model belongs in the simulator, not in this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

DATA_FILE = Path(__file__).with_name("civdata.json")

AGE_ORDER = ("dark", "feudal", "castle", "imperial")

# Sim job -> the villager unit variants that do it. Rates differ per variant,
# which is why food is four jobs rather than one.
JOB_UNITS = {
    "sheep": ("VMSHE", "VFSHE"),
    "boar": ("VMHUN", "VFHUN"),
    "deer": ("VMHUN", "VFHUN"),
    "berries": ("VMFOR", "VFFOR"),
    "farm": ("VMFAR", "VFFAR"),
    "wood": ("VMLUM", "VFLUM"),
    # A straggler is the same lumberjack on the same tree. What separates it
    # from the wood line is where it stands and where the load goes.
    "stragglers": ("VMLUM", "VFLUM"),
    "gold": ("VMGLD", "VFGLD"),
    "stone": ("VMMIN", "VFMIN"),
    "fish": ("VMFIS", "VFFIS"),
}

JOB_RESOURCE = {
    "sheep": "food", "boar": "food", "deer": "food", "berries": "food",
    "farm": "food", "fish": "food",
    "wood": "wood", "stragglers": "wood", "gold": "gold", "stone": "stone",
}

# Sim building name -> Genie internal name of its Dark Age variant. The
# suffixed variants (HOUS2, STBL3, ...) are per-age art, same stats.
BUILDING_UNITS = {
    "town_center": "RTWC",
    "house": "HOUS",
    "barracks": "Barracks Age1",
    "stable": "STBL",
    "archery_range": "ARRG",
    "blacksmith": "BLAC",
    "mill": "MILL",
    "lumber_camp": "SMIL",
    "mining_camp": "MINE",
    "farm": "FARM",
    "market": "MRKT",
}

# A civ that loses this whole set of roles builds this instead. The set is the
# key because it is the only thing that tells the replacements apart: the Mule
# Cart stands in for the two camps, the Settlement for the camps and the Mill
# together. Read the enable side instead and Tupi and the Incas come out with
# no drop-off at all -- their Settlement's enabling tech is `civ == -1` and a
# regional-tech toggle gets to it first.
#
# The Folwark is deliberately absent: Poles keep the Mill and the game upgrades
# it in place, which `_upgraded` follows on its own.
BUILDING_REPLACEMENTS = {
    frozenset({"lumber_camp", "mining_camp"}): "MULECART",
    frozenset({"mill", "lumber_camp", "mining_camp"}): "SETTL1",
}

REPLACEABLE_ROLES = frozenset().union(*BUILDING_REPLACEMENTS)

# What to call the thing on screen when it is not the default. Age variants
# share a label for the same reason they share their stats.
BUILDING_LABELS = {
    "FOLWARK1": "folwark", "FOLWARK2": "folwark", "FOLWARK3": "folwark",
    "SETTL1": "settlement", "SETTL2": "settlement", "SETTL3": "settlement",
    "MULECART": "mule cart",
}

VILLAGER_UNIT = "VMBAS"

# Sim unit name -> (Genie internal name, the building role that trains it).
#
# The Genie names are legacy and three of them lie outright: `SPRMN` is the
# Militia, `PKEMN` the Spearman and `XBOWM` the Skirmisher. Each was identified
# by its cost and train time rather than by its name, and `check.py` asserts
# both, so a re-extraction that renumbers anything fails loudly instead of
# quietly training the wrong unit. Add a unit here and nothing else needs
# editing -- the building comes off the role, so the civ's own replacement for
# it is resolved the same way a drop-off is.
MILITARY_UNITS = {
    "militia": ("SPRMN", "barracks"),
    "spearman": ("PKEMN", "barracks"),
    "archer": ("ARCHR", "archery_range"),
    "skirmisher": ("XBOWM", "archery_range"),
    "scout": ("SCOUT", "stable"),
}

# Everything a building can be told to make. The villager is in here rather
# than beside it because the Town Centre is a production building like any
# other -- it just also researches, which is what `towncentre.py` is left
# owning once the door itself is `production.py`.
TRAINED_UNITS = {"villager": (VILLAGER_UNIT, "town_center"), **MILITARY_UNITS}

# Internal tech names are shifted one age from the display names: the tech the
# game calls "Middle Age" is what players click to reach Feudal.
AGE_TECHS = {"feudal": "Middle Age", "castle": "Feudal Age", "imperial": "Imperial Age"}


def _age_index(age: str) -> int:
    return AGE_ORDER.index("dark" if age == "start" else age)


class DataError(KeyError):
    pass


@dataclass(frozen=True)
class Cost:
    food: int = 0
    wood: int = 0
    gold: int = 0
    stone: int = 0
    pop: int = 0

    @classmethod
    def from_json(cls, d: dict) -> "Cost":
        return cls(**{k: int(v) for k, v in d.items() if k in cls.__annotations__})


class CivProfile:
    """One civ's view of the game data, with its bonuses resolved by age."""

    def __init__(self, data: "GameData", name: str, raw: dict):
        self._data = data
        self.name = name
        self._raw = raw

    @property
    def civ_id(self) -> int:
        return self._raw["civ_id"]

    def _mods(self, kind: str, age: str):
        limit = _age_index(age)
        for m in self._raw["eco_modifiers"]:
            if m["kind"] == kind and _age_index(m["applies_from"]) <= limit:
                yield m

    def _mods_for_units(self, kind: str, age: str, units: tuple):
        """Modifiers hitting any of `units`, counted once per bonus.

        A bonus that applies to a villager job is written once per gender
        variant in the .dat; both name the same job, so applying every match
        would square the multiplier.
        """
        seen = set()
        for m in self._mods(kind, age):
            if m.get("target_unit") not in units:
                continue
            key = (m["tech_name"], m["mode"], m.get("attribute"), m["d"])
            if key in seen:
                continue
            seen.add(key)
            yield m

    def gather_rate(self, job: str, age: str = "dark") -> float:
        """Raw work rate for `job`, with this civ's work-rate bonuses applied."""
        units = JOB_UNITS[job]
        base = self._data.work_rate(units[0])
        factor = 1.0
        for m in self._mods_for_units("work_rate", age, units):
            if m["mode"] == "multiply":
                factor *= m["d"]
            elif m["mode"] == "add":
                base += m["d"]
            else:
                base = m["d"]
        return base * factor

    def gather_rates(self, age: str = "dark") -> dict:
        return {job: self.gather_rate(job, age) for job in JOB_UNITS}

    def carry_capacity(self, job: str, age: str = "dark") -> float:
        units = JOB_UNITS[job]
        cap = float(self._data.carry_capacity(units[0]))
        for m in self._mods_for_units("carry_capacity", age, units):
            cap = cap * m["d"] if m["mode"] == "multiply" else cap + m["d"]
        return cap

    def starting_resources(self, lobby: dict | None = None) -> dict:
        """Lobby start plus this civ's deltas.

        Absolute start amounts are a lobby setting, not game data, so the
        standard-start defaults live here and the .dat supplies only the civ
        deltas.
        """
        out = dict(lobby or {"food": 200, "wood": 200, "gold": 100, "stone": 200})
        for m in self._mods("starting_resource", "dark"):
            res = m["resource"].removeprefix("starting_")
            if res not in out:
                continue
            out[res] = out[res] + m["d"] if m["mode"] == "add" else m["d"]
        return {k: int(v) for k, v in out.items()}

    def _fires_at_start(self, bonus: dict) -> bool:
        """Whether the engine has already fired this bonus at 0:00.

        Wei spawn a villager for every economic technology researched, so each
        of those sixteen bonuses names a real tech; the Chinese three name only
        shadow techs, which cost nothing and are auto-researched. Counting them
        alike starts Wei with nineteen villagers.
        """
        return all(self._data.techs.get(r["tech_id"], {}).get("auto_research")
                   for r in bonus["requires"])

    @property
    def starting_villagers(self) -> int:
        n = int(self._raw.get("starting_villagers") or 3)
        for b in self._raw["bonuses"]:
            if not self._fires_at_start(b):
                continue
            for c in b["commands"]:
                if (c["kind"] == "spawn_unit"
                        and c.get("target_unit") == VILLAGER_UNIT):
                    n += int(c.get("count", 0))
        return n

    def villager(self, age: str = "dark") -> tuple[Cost, int]:
        return self._unit_cost_time(VILLAGER_UNIT, age)

    def building(self, key: str, age: str = "dark") -> tuple[Cost, int]:
        return self._unit_cost_time(BUILDING_UNITS[key], age)

    def _unit_cost_time(self, internal_name: str, age: str) -> tuple[Cost, int]:
        entry = self._data.unit_by_name(internal_name)
        cost = dict(entry["cost"])
        time = entry.get("train_time") or entry.get("build_time")
        for m in self._mods("unit_cost", age):
            if m.get("target_unit") != internal_name:
                continue
            fields = ({"food": "food_cost", "wood": "wood_cost",
                       "stone": "stone_cost", "gold": "gold_cost"}
                      if m["attribute"] != "cost" else None)
            for res in ("food", "wood", "stone", "gold"):
                if fields and m["attribute"] != fields[res]:
                    continue
                if res not in cost:
                    continue
                cost[res] = (cost[res] * m["d"] if m["mode"] == "multiply"
                             else cost[res] + m["d"] if m["mode"] == "add"
                             else m["d"])
        for m in self._mods("train_time", age):
            if m.get("target_unit") == internal_name:
                time = (time * m["d"] if m["mode"] == "multiply"
                        else time + m["d"] if m["mode"] == "add" else m["d"])
        return Cost.from_json({k: round(v) for k, v in cost.items()}), round(time)

    def age_up(self, target_age: str) -> tuple[Cost, int]:
        """Cost and research time to click `target_age`, with civ bonuses."""
        tech = self._data.tech_by_name(AGE_TECHS[target_age])
        cost = dict(tech["cost"])
        time = float(tech["research_time"])
        for m in self._mods("tech_time", target_age):
            if m["a"] in (tech["id"], -1):
                time = time + m["d"] if m["c"] else m["d"]
        for m in self._mods("tech_cost", target_age):
            if m["a"] != tech["id"]:
                continue
            res = {0: "food", 1: "wood", 2: "stone", 3: "gold"}.get(m["b"])
            if res in cost:
                cost[res] = cost[res] + m["d"] if m["c"] else m["d"]
        return Cost.from_json({k: round(v) for k, v in cost.items()}), round(time)

    def unmodelled_bonuses(self) -> list[dict]:
        """Bonuses this civ has that the sim cannot express.

        Two sources: effect commands whose kind is outside the eco set, and
        marker techs whose meaning lives in the tech tree (free techs, techs
        unlocked an age early) and so has no decodable command at all.
        """
        return [
            {"tech_name": b["tech_name"], "reason": "tech_tree_marker",
             "requires": [r["tech_name"] for r in b["requires"]]}
            for b in self._raw["bonuses"]
            if b["mechanism"] == "tech_tree_marker" and b["tech_name"].strip()
        ]

    def __repr__(self) -> str:
        return f"<CivProfile {self.name} id={self.civ_id}>"


class GameData:
    def __init__(self, payload: dict):
        self._p = payload
        # One unit can appear in several sections (a gatherer variant also has
        # a cost); merge them so lookups see the union of fields.
        self._by_name = {}
        for section in ("units", "buildings", "gatherers"):
            for entry in payload[section].values():
                merged = self._by_name.setdefault(entry["internal_name"], {})
                for k, v in entry.items():
                    merged.setdefault(k, v)
        self._techs_by_name = {t["internal_name"]: t for t in payload["techs"].values()}
        self._by_id = {}
        for section in ("units", "buildings", "gatherers"):
            for entry in payload[section].values():
                merged = self._by_id.setdefault(entry["id"], {})
                for k, v in entry.items():
                    merged.setdefault(k, v)
        self.techs = {int(k): v for k, v in payload["techs"].items()}
        self.resource_nodes = payload.get("resource_nodes", {})
        self.effects = {int(k): v for k, v in payload.get("effects", {}).items()}

    @classmethod
    def load(cls, path: Path | str = DATA_FILE) -> "GameData":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def meta(self) -> dict:
        return self._p["meta"]

    def unit_by_name(self, internal_name: str) -> dict:
        try:
            return self._by_name[internal_name]
        except KeyError:
            raise DataError(
                f"no unit named {internal_name!r} in {self.meta['source_file']} "
                f"({self.meta['dat_version']}); update the name maps in "
                f"aoe2planner/gamedata/__init__.py") from None

    def unit_by_id(self, unit_id: int) -> dict | None:
        return self._by_id.get(unit_id)

    def raw_civ(self, name: str) -> dict:
        return self._p["civs"][name]

    def tech_by_name(self, internal_name: str) -> dict:
        try:
            return self._techs_by_name[internal_name]
        except KeyError:
            raise DataError(f"no tech named {internal_name!r}") from None

    def work_rate(self, internal_name: str) -> float:
        return self.unit_by_name(internal_name)["work_rate"]

    def carry_capacity(self, internal_name: str) -> int:
        return self.unit_by_name(internal_name)["carry_capacity"]

    @cached_property
    def civ_names(self) -> tuple:
        return tuple(self._p["civs"])

    def civ(self, name: str) -> CivProfile:
        try:
            return CivProfile(self, name, self._p["civs"][name])
        except KeyError:
            raise DataError(
                f"unknown civ {name!r}; have {', '.join(self.civ_names)}") from None
