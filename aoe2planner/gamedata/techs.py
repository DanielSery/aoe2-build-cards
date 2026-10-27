"""
Tech resolver: runs the game's own bonus mechanism instead of re-describing it.

Civ bonuses in AoE2 are technologies. Each has a gate -- "any N of these other
techs" -- and the engine auto-researches it, for free and instantly, the moment
the gate is satisfied. Franks' foragers gate on nothing, so they fire at t=0;
Chinese tech discounts gate on the age techs, so they escalate by age;
Burgundians get eco upgrades an age early because a civ-only marker tech
satisfies the count in place of the age tech.

So there is no civ table here. Feed the resolver the facts the simulator knows
(which buildings exist, which techs the player has researched), call `resolve`,
and read the resulting numbers back.

Team bonuses are extracted but deliberately not applied -- the planner models
1v1 only. Walking and drop-off distance are likewise out of scope: this layer
reports work rate and carry capacity, and the simulator turns those into
throughput.
"""

from __future__ import annotations

from . import (AGE_TECHS, BUILDING_LABELS, BUILDING_REPLACEMENTS,
               BUILDING_UNITS, JOB_UNITS, REPLACEABLE_ROLES, VILLAGER_UNIT,
               Cost, DataError, GameData)

# A building's existence is reported to the tech tree as a costless "shadow"
# tech that nothing can research -- the engine sets it when the building goes
# up. Age-ups gate on these, which is why houses do not count towards an age.
BUILDING_PREREQ_TECH = {
    "town_center": 307,
    "mill": 110,
    "lumber_camp": 258,
    "barracks": 122,
    "mining_camp": 282,
    "archery_range": 132,
    "blacksmith": 106,
    "stable": 130,
    "market": 128,
    "castle": 266,
}

# Guards against a patch renumbering the shadow techs under us.
_PREREQ_NAME_HINTS = {
    307: "tc", 110: "mill", 258: "saw mill", 122: "barracks", 282: "mine",
    132: "archery", 106: "blacksmith", 130: "stable", 128: "market",
    266: "castle",
}

RESOURCE_BY_ID = {0: "food", 1: "wood", 2: "stone", 3: "gold"}

ATTR_COST = {103: "food", 104: "wood", 105: "stone", 106: "gold"}
ATTR_ALL_COST = 100
ATTR_WORK_RATE = 13
ATTR_CARRY = 14
ATTR_CREATION_TIME = 101


class TechEngine:
    def __init__(self, data: GameData, civ_name: str, lobby: dict | None = None):
        self.data = data
        self.civ_name = civ_name
        self._civ = data.raw_civ(civ_name)
        self.civ_id = self._civ["civ_id"]
        self._verify_prereq_techs()

        self.researched: set[int] = set()
        self.attrs: dict[tuple[int, int], float] = {}
        self.tech_cost_override: dict[int, dict] = {}
        self.tech_time_override: dict[int, float] = {}
        self.spawns: dict[int, int] = {}
        self.disabled_units: set[int] = set()
        self.enabled_units: set[int] = set()
        self.upgrades: dict[int, int] = {}
        self.disabled_techs: set[int] = set()
        self.globals: dict[str, float] = {}
        self.skipped: list[dict] = []

        # The simulator asks for the same handful of unit attributes every
        # second of every villager, and they only ever move when a tech lands.
        # `resolve()` runs after every mutation, so it is the one place the
        # cache has to be dropped -- and `version` is how anything downstream
        # holding derived numbers knows to drop its own.
        self._cache: dict = {}
        self.version = 0

        self.starting = dict(
            lobby or {"food": 200, "wood": 200, "gold": 100, "stone": 200})

        # The civ's tech-tree effect is the game's own "make this civ this
        # civ" step: unit availability, free techs, per-civ tech discounts.
        tree = self._civ.get("tech_tree")
        if tree:
            self._apply(tree["availability"] + tree["modifiers"])
        # The player starts with a Town Center; several civ bonuses (extra
        # starting villagers, cheaper TCs) gate on its existence.
        self.researched.add(BUILDING_PREREQ_TECH["town_center"])
        self.resolve()

    # --- inputs from the simulator ---

    def add_building(self, key: str) -> None:
        tech_id = BUILDING_PREREQ_TECH.get(key)
        if tech_id is not None and tech_id not in self.researched:
            self.researched.add(tech_id)
            self.resolve()

    def research(self, tech_id: int) -> None:
        if tech_id in self.researched:
            return
        self.researched.add(tech_id)
        self._apply_tech_effect(tech_id)
        self.resolve()

    def enter_age(self, age: str) -> None:
        self.research(self.age_tech_id(age))

    def resolve(self) -> None:
        """Auto-research every free tech whose gate is now satisfied."""
        changed = True
        while changed:
            changed = False
            for tech_id, tech in self.data.techs.items():
                if tech_id in self.researched or not tech["auto_research"]:
                    continue
                if tech_id in self.disabled_techs:
                    continue
                if tech["civ"] not in (-1, self.civ_id):
                    continue
                if not self.gate_satisfied(tech_id):
                    continue
                self.researched.add(tech_id)
                self._apply_tech_effect(tech_id)
                changed = True
        self._cache.clear()
        self.version += 1

    # --- queries ---

    def gate_satisfied(self, tech_id: int) -> bool:
        tech = self.data.techs[tech_id]
        met = sum(1 for r in tech["required_techs"] if r in self.researched)
        return met >= tech["required_tech_count"]

    def can_research(self, tech_id: int) -> bool:
        return (tech_id not in self.researched
                and tech_id not in self.disabled_techs
                and self.data.techs[tech_id]["civ"] in (-1, self.civ_id)
                and self.gate_satisfied(tech_id))

    def age_tech_id(self, age: str) -> int:
        return self.data.tech_by_name(AGE_TECHS[age])["id"]

    def tech_cost(self, tech_id: int) -> Cost:
        base = dict(self.data.techs[tech_id]["cost"])
        base.update(self.tech_cost_override.get(tech_id, {}))
        mult = self.globals.get("research_cost_multiplier", 1.0)
        return Cost.from_json({k: max(0, round(v * mult)) for k, v in base.items()})

    def tech_time(self, tech_id: int) -> int:
        t = self.tech_time_override.get(
            tech_id, self.data.techs[tech_id]["research_time"] or 0)
        return max(0, round(t * self.globals.get("research_time_multiplier", 1.0)))

    def age_up(self, age: str) -> tuple[Cost, int]:
        tid = self.age_tech_id(age)
        return self.tech_cost(tid), self.tech_time(tid)

    def work_rate(self, job: str) -> float:
        key = ("work_rate", job)
        if key not in self._cache:
            self._cache[key] = self._attr(self._unit_id(JOB_UNITS[job][0]),
                                          ATTR_WORK_RATE)
        return self._cache[key]

    def carry_capacity(self, job: str) -> float:
        key = ("carry_capacity", job)
        if key not in self._cache:
            self._cache[key] = self._attr(self._unit_id(JOB_UNITS[job][0]),
                                          ATTR_CARRY)
        return self._cache[key]

    def work_rate_of(self, internal_name: str) -> float | None:
        """A non-villager's own work rate -- a farm growing its food, say.

        None when the extraction carries no base for it, which is how a caller
        can tell "not in the data" from a real zero.
        """
        uid = self._unit_id(internal_name)
        if (uid, ATTR_WORK_RATE) in self.attrs:
            return float(self.attrs[(uid, ATTR_WORK_RATE)])
        base = self._base_attr(uid, ATTR_WORK_RATE)
        return None if base is None else float(base)

    def gather_rates(self) -> dict:
        return {job: self.work_rate(job) for job in JOB_UNITS}

    def unit_cost(self, internal_name: str) -> Cost:
        uid = self._unit_id(internal_name)
        entry = self.data.unit_by_id(uid)
        return Cost.from_json({
            res: max(0, round(self._attr(uid, attr)))
            for attr, res in ATTR_COST.items() if res in entry["cost"]
        } | ({"pop": entry["cost"]["pop"]} if "pop" in entry["cost"] else {}))

    def build_time(self, internal_name: str) -> int:
        uid = self._unit_id(internal_name)
        t = self._attr(uid, ATTR_CREATION_TIME)
        # Spanish build faster through a global construction rate rather than
        # through each building's time, so it has to be divided back out here.
        # Units train at their creation time regardless.
        if "build_time" in (self.data.unit_by_id(uid) or {}):
            t /= self.globals.get("construction_rate_modifier", 1.0)
        return max(0, round(t))

    def villager_cost(self) -> Cost:
        return self.unit_cost(VILLAGER_UNIT)

    def building_for(self, key: str) -> str:
        """The building this civ actually puts up in `key`'s role.

        Three civ groups do not build the default. Poles upgrade the Mill into
        a Folwark, so they never place one; Armenians and Georgians have the
        Lumber and Mining Camps disabled and a Mule Cart enabled instead; the
        South American civs lose all three to the Settlement. Every one of
        those is read off the tech graph -- the Settlement's own enabling tech
        is `civ == -1` and fires for everybody, so what picks it is the default
        being disabled, not the Settlement being switched on.

        The role is what the rest of the sim talks in: a Settlement built to
        serve the gold is this civ's mining camp, and costs and pop room come
        from whatever the role resolved to.
        """
        name = BUILDING_UNITS[key]
        # A role nothing stands in for stays itself even when the civ has it
        # disabled: the Huns lose the House and get nothing back, and it is the
        # population rules that have to say so, not this name.
        if self.is_available(name) or key not in REPLACEABLE_ROLES:
            return self._upgraded(name)
        replacement = BUILDING_REPLACEMENTS.get(self.lost_roles)
        if replacement is None:
            raise DataError(
                f"{self.civ_name} cannot build {key!r} ({name}) and no "
                f"replacement covers {sorted(self.lost_roles)}; "
                f"BUILDING_REPLACEMENTS needs an entry for "
                f"{self.data.meta['dat_version']}")
        return self._upgraded(replacement)

    @property
    def lost_roles(self) -> frozenset:
        return frozenset(k for k in REPLACEABLE_ROLES
                         if not self.is_available(BUILDING_UNITS[k]))

    def building_label(self, key: str) -> str:
        """What to call this civ's `key` on screen."""
        return BUILDING_LABELS.get(self.building_for(key), key)

    def _upgraded(self, name: str) -> str:
        """Follow a free upgrade chain to what stands there now.

        The per-age variants are the same building with different art, so
        walking to the end costs nothing and keeps a Castle Age Folwark from
        reading as a Mill.
        """
        uid = self._unit_id(name)
        seen = {uid}
        while self.upgrades.get(uid) not in (None, *seen):
            uid = self.upgrades[uid]
            seen.add(uid)
        entry = self.data.unit_by_id(uid)
        return entry["internal_name"] if entry else name

    def building_cost(self, key: str) -> tuple[Cost, int]:
        name = self.building_for(key)
        return self.unit_cost(name), self.build_time(name)

    def starting_resources(self) -> dict:
        return {k: int(v) for k, v in self.starting.items()}

    def starting_villagers(self) -> int:
        base = int(self._civ.get("starting_villagers") or 3)
        return base + self.spawns.get(self._unit_id(VILLAGER_UNIT), 0)

    def is_available(self, internal_name: str) -> bool:
        return self._unit_id(internal_name) not in self.disabled_units

    # --- effect application ---

    def _apply_tech_effect(self, tech_id: int) -> None:
        effect_id = self.data.techs[tech_id]["effect_id"]
        effect = self.data.effects.get(effect_id)
        if effect:
            self._apply(effect["commands"])

    def _apply(self, commands: list) -> None:
        for c in commands:
            handler = getattr(self, f"_cmd_{c['type']}", None)
            if handler is None:
                self.skipped.append(c)
            else:
                handler(c)

    def _cmd_0(self, c):   # ATTRIBUTE_SET
        self._write_attr(c, lambda cur, d: d)

    def _cmd_4(self, c):   # ATTRIBUTE_ADD
        self._write_attr(c, lambda cur, d: cur + d)

    def _cmd_5(self, c):   # ATTRIBUTE_MULTIPLY
        self._write_attr(c, lambda cur, d: cur * d)

    def _cmd_1(self, c):   # RESOURCE_MODIFY
        self._write_resource(c, absolute=(c["b"] == 0))

    def _cmd_6(self, c):   # RESOURCE_MULTIPLY
        name = c["resource"]
        self.globals[name] = self.globals.get(name, 1.0) * c["d"]

    def _cmd_2(self, c):   # UNIT_ENABLED
        if c["b"]:
            self.disabled_units.discard(c["a"])
            self.enabled_units.add(c["a"])
        else:
            self.disabled_units.add(c["a"])
            self.enabled_units.discard(c["a"])

    def _cmd_7(self, c):   # SPAWN_UNIT
        self.spawns[c["a"]] = self.spawns.get(c["a"], 0) + int(c["c"])

    def _cmd_101(self, c):  # TECH_COST_MODIFY
        res = RESOURCE_BY_ID.get(c["b"])
        if res is None:
            return
        cur = self.tech_cost_override.setdefault(
            c["a"], dict(self.data.techs.get(c["a"], {}).get("cost", {})))
        cur[res] = c["d"] if c["c"] == 0 else cur.get(res, 0) + c["d"]

    def _cmd_102(self, c):  # TECH_TOGGLE
        self.disabled_techs.add(int(c["d"]))

    def _cmd_103(self, c):  # TECH_TIME_MODIFY
        base = self.data.techs.get(c["a"], {}).get("research_time") or 0
        cur = self.tech_time_override.get(c["a"], base)
        self.tech_time_override[c["a"]] = c["d"] if c["c"] == 0 else cur + c["d"]

    def _cmd_3(self, c):   # UNIT_UPGRADE
        # Almost all of these are military lines the planner does not model.
        # The one that matters is the Poles', which turns the Mill they would
        # have built into a Folwark before the game starts.
        self.upgrades[c["a"]] = c["b"]

    def _cmd_8(self, c):   # RESEARCH_TIME_MODIFY
        self.tech_time_override[c["a"]] = c["d"]

    # --- attribute store ---

    def _write_attr(self, c, combine) -> None:
        if c["a"] < 0:
            # class-targeted; villager jobs are always unit-targeted, so this
            # only ever drops military bonuses the planner does not model.
            self.skipped.append(c)
            return
        attrs = ([a for a, res in ATTR_COST.items()
                  if res in (self.data.unit_by_id(c["a"]) or {}).get("cost", {})]
                 if c["c"] == ATTR_ALL_COST else [c["c"]])
        for attr in attrs:
            key = (c["a"], attr)
            cur = self.attrs.get(key)
            if cur is None:
                cur = self._base_attr(c["a"], attr)
                if cur is None:
                    self.skipped.append(c)
                    continue
            self.attrs[key] = combine(cur, c["d"])

    def _write_resource(self, c, absolute: bool) -> None:
        name = c["resource"]
        if name.startswith("starting_") and name != "starting_villagers":
            res = name.removeprefix("starting_")
            if res in self.starting:
                self.starting[res] = (c["d"] if absolute
                                      else self.starting[res] + c["d"])
        elif name in ("research_cost_multiplier", "research_time_multiplier"):
            self.globals[name] = (c["d"] if absolute
                                  else self.globals.get(name, 1.0) + c["d"])
        else:
            self.globals[name] = c["d"]

    def _attr(self, unit_id: int, attr: int) -> float:
        key = (unit_id, attr)
        if key in self.attrs:
            return self.attrs[key]
        base = self._base_attr(unit_id, attr)
        if base is None:
            raise KeyError(f"no base value for unit {unit_id} attribute {attr}")
        return base

    def _base_attr(self, unit_id: int, attr: int) -> float | None:
        entry = self.data.unit_by_id(unit_id)
        if entry is None:
            return None
        if attr == ATTR_WORK_RATE:
            return entry.get("work_rate")
        if attr == ATTR_CARRY:
            return entry.get("carry_capacity")
        if attr == ATTR_CREATION_TIME:
            return entry.get("train_time") or entry.get("build_time")
        if attr in ATTR_COST:
            return entry.get("cost", {}).get(ATTR_COST[attr])
        return None

    def _unit_id(self, internal_name: str) -> int:
        key = ("unit_id", internal_name)
        if key not in self._cache:
            self._cache[key] = self.data.unit_by_name(internal_name)["id"]
        return self._cache[key]

    def _verify_prereq_techs(self) -> None:
        for tech_id, hint in _PREREQ_NAME_HINTS.items():
            name = self.data.techs.get(tech_id, {}).get("internal_name", "")
            if hint not in name.lower():
                raise ValueError(
                    f"tech {tech_id} is {name!r}, expected something matching "
                    f"{hint!r}; BUILDING_PREREQ_TECH needs re-deriving for "
                    f"{self.data.meta['dat_version']}")

    def __repr__(self) -> str:
        return (f"<TechEngine {self.civ_name} researched={len(self.researched)} "
                f"skipped={len(self.skipped)}>")
