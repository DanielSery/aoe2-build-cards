"""
What a player was doing, in a few words: "men-at-arms → archers", "boom,
knights", "unique unit, fast imp → hand cannoneers".

Read off what decides a build: the units made, the towers and castles built
forward, a douche (the starting Town Centre deleted and one built forward),
extra Town Centres, and how soon after Castle Age Imperial was clicked. Each is a plan with a span of time. Plans that overlap inside one age
are listed with a comma; the next one after an arrow.

A unit is named as the upgrade its line had when it was queued — scouts, light
cavalry, hussars — because a replay queues the line's first unit whatever has
been researched, and the upgrade is a research of the same name. Units are
counted off queue clicks, which are recorded with or without the resources to
pay for them (see `card.py`), so a count is an upper bound. The thresholds
below are judgement, not measurement.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .game import UNIT_LINES, PlayerLog, Replay, secs

AGES = ("FEUDAL_AGE", "CASTLE_AGE", "IMPERIAL_AGE")
TOWN_CENTRE = 109
SIEGE_WORKSHOP = 49
NOT_A_PLAN = {"Villager", "Fishing Ship", "Trade Cart", "Trade Cog", "Transport Ship", "Petard",
              "Trebuchet (Packed)", "King"}
LABELS = {"Militia": "militia", "Scout Cavalry": "scouts", "Camel Rider": "camels", "Heavy Camel Rider": "heavy camels",
          "Imperial Camel Rider": "imperial camels", "Man-at-Arms": "men-at-arms",
          "Eagle Scout": "eagles"}
TOWERS = {"Watch Tower", "Guard Tower", "Keep", "Bombard Tower", "Donjon"}
CASTLES = {"Castle", "Krepost"}
PRODUCTION = {"Barracks", "Archery Range", "Stable"}

FEW = 3            # fewer of a line than this in an age is no plan
SHARE = 0.2        # nor is a line under this share of the age's army
PER_AGE = 2        # lines named per age, most made first
BOOM = 2           # Town Centres beyond the first that make a boom
FAST_IMP = 300.0   # Imperial clicked this soon after reaching Castle Age
IMP_SECONDS = 190.0
REACH = 40.0       # tiles from an enemy's Town Centre a forward building is within
FORWARD = 0.75     # and how much nearer to it than to any of the team's own
AFTER_IMP = 360.0  # how far into Imperial Age the plan is read
SHOWN = 5


@dataclass
class Plan:
    label: str
    start: float
    end: float


def strategy(replay: Replay, number: int, enemies: set[int]) -> str:
    log = PlayerLog(replay, number)
    landed: dict[str, float] = {}
    for u in replay.match.uptimes:
        if u.player is log.player and u.age.name in AGES:
            landed.setdefault(u.age.name, u.timestamp.total_seconds())
    stages = [landed.get(name, math.inf) for name in AGES]

    def age(t: float) -> int:
        return sum(t >= s for s in stages)

    end = stages[2] + AFTER_IMP if stages[2] < math.inf else replay.match.duration.total_seconds()
    plans = _units(log, age, stages, end) + _boom(log, stages, end) + _fast_imp(log, stages)
    aggressive, forward = _aggression(replay, log, enemies, age, end)
    # A barracks at their door is how the units after it were meant, not a plan
    # of its own.
    for t in forward:
        made = next((p for p in sorted(plans, key=lambda p: p.start)
                     if p.label not in ("boom", "fast imp") and t - 60 <= p.start <= t + 240), None)
        if made and not made.label.startswith("forward"):
            made.label = "forward " + made.label
    return _sentence(sorted(plans + aggressive, key=lambda p: p.start)[:SHOWN], age)


def _upgrades(log: PlayerLog, end: float) -> dict[str, list[tuple[float, str]]]:
    """line -> [(when, upgrade)], in the order researched. The last click of
    each: one without the resources is recorded too, and none can follow the
    one that starts the research."""
    clicked: dict[str, float] = {}
    for a in log.actions:
        name = a.payload.get("technology")
        if a.type.name == "RESEARCH" and name in UNIT_LINES and secs(a) <= end:
            clicked[name] = secs(a)
    out: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for name, t in sorted(clicked.items(), key=lambda kv: kv[1]):
        out[UNIT_LINES[name]["line"]].append((t, name))
    return out


def _label(line: dict, unit: str, t: float, stage: int, upgrades: dict, men_at_arms: bool) -> str:
    version = unit
    for when, name in upgrades.get(line["line"], []):
        if when <= t:
            version = name
    if line["unique"]:
        return "elite unique unit" if version != unit else "unique unit"
    if line["line"] == "Militia" and version == "Militia" and stage <= 1:
        # Militia that were going to be men-at-arms are the start of that
        # rush; only without the upgrade are they a drush.
        return "men-at-arms" if men_at_arms else "drush"
    return LABELS.get(version) or _plural(version.lower())


def _plural(name: str) -> str:
    if name.endswith("man"):
        return name[:-3] + "men"
    if name.endswith(("cavalry", "s")):
        return name
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return name[:-1] + "ies"
    return name + "s"


def _units(log: PlayerLog, age, stages: list[float], end: float) -> list[Plan]:
    upgrades = _upgrades(log, end)
    men_at_arms = any(name == "Man-at-Arms" and t < stages[1] for t, name in upgrades.get("Militia", []))
    made: dict[int, Counter] = defaultdict(Counter)       # age -> line -> units
    versions: dict[tuple[int, str], Counter] = defaultdict(Counter)
    spans: dict[tuple[int, str], list[float]] = {}
    for a in log.actions:
        t = secs(a)
        if t > end:
            break
        unit = a.payload.get("unit")
        if a.type.name != "DE_QUEUE" or not unit:
            continue
        line = UNIT_LINES.get(unit) or {"line": unit, "unique": False, "building": None}
        if line["line"] in NOT_A_PLAN or line["building"] == SIEGE_WORKSHOP:
            continue
        stage = age(t)
        label = _label(line, unit, t, stage, upgrades, men_at_arms)
        amount = a.payload.get("amount", 1)
        made[stage][line["line"]] += amount
        versions[(stage, line["line"])][label] += amount
        span = spans.setdefault((stage, label), [t, t])
        span[1] = t

    # A line is judged whole, then named by each upgrade it was made as:
    # five scouts and ten light cavalry are one line worth naming, twice.
    plans: dict[str, Plan] = {}
    for stage, lines in made.items():
        army = sum(lines.values())
        for line, n in lines.most_common(PER_AGE):
            if n < FEW or n < SHARE * army:
                continue
            named = versions[(stage, line)]
            for label, m in named.items():
                if m < FEW and label != named.most_common(1)[0][0]:
                    continue
                first, last = spans[(stage, label)]
                if label in plans:
                    plans[label].start = min(plans[label].start, first)
                    plans[label].end = max(plans[label].end, last)
                else:
                    plans[label] = Plan(label, first, last)
    return list(plans.values())


def _boom(log: PlayerLog, stages: list[float], end: float) -> list[Plan]:
    built = [b.t for b in log.placed if b.name == "Town Center" and stages[0] <= b.t <= end]
    return [Plan("boom", built[0], built[-1])] if len(built) >= BOOM else []


def _fast_imp(log: PlayerLog, stages: list[float]) -> list[Plan]:
    clicks = [secs(a) for a in log.actions
              if a.type.name == "RESEARCH" and a.payload.get("technology") == "Imperial Age"
              and secs(a) <= stages[2]]
    if not clicks or clicks[-1] - stages[1] > FAST_IMP:
        return []
    landing = stages[2] if stages[2] < math.inf else clicks[-1] + IMP_SECONDS
    return [Plan("fast imp", clicks[-1], landing)]


def _aggression(replay: Replay, log: PlayerLog, enemies: set[int], age,
                end: float) -> tuple[list[Plan], list[float]]:
    """Towers, castles and a douche's Town Centre built forward, and when a
    production building was.

    Forward is within `REACH` of an enemy's starting Town Centre and clearly
    nearer it than any Town Centre of one's own team: a castle half way across
    the map, or one by an ally's base that happens to face the enemy, defends.
    A nomad start has no Town Centres to measure from, so nothing is forward."""
    homes: dict[int, tuple[float, float]] = {}
    for n in replay.nodes.values():
        if n.type == TOWN_CENTRE and n.owner:
            homes.setdefault(n.owner, (n.x, n.y))
    theirs = [homes[n] for n in enemies if n in homes]
    ours = [xy for n, xy in homes.items() if n not in enemies]
    if not theirs or not ours:
        return [], []
    deleted = min((secs(a) for a in log.actions
                   if a.type.name == "DELETE" and set(a.payload.get("object_ids") or []) & log.tcs),
                  default=math.inf)
    plans: dict[str, Plan] = {}
    forward: list[float] = []
    for b in log.placed:
        if b.t > end:
            break
        near = min(math.dist((b.x, b.y), xy) for xy in theirs)
        if near > REACH or near >= FORWARD * min(math.dist((b.x, b.y), xy) for xy in ours):
            continue
        if b.name in PRODUCTION:
            forward.append(b.t)
            continue
        if b.name in TOWERS:
            label = "tower rush" if age(b.t) <= 1 else "towers"
        elif b.name in CASTLES:
            label = "castle drop"
        elif b.name == "Town Center" and deleted <= b.t:
            plans.setdefault("douche", Plan("douche", deleted, b.t))
            continue
        else:
            continue
        plans.setdefault(label, Plan(label, b.t, b.t)).end = b.t
    return list(plans.values()), forward


def _sentence(plans: list[Plan], age) -> str:
    out = ""
    for k, plan in enumerate(plans):
        if k:
            before = plans[k - 1]
            together = age(plan.start) == age(before.start) and plan.start < before.end
            out += ", " if together else " → "
        out += plan.label
    return out
