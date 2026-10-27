"""
A recorded game, and one player's commands resolved into what they mean.

A replay is the command stream, not the game state: it says "these villagers
were right-clicked onto that object", never "this villager now carries wood".
This file reads the commands; `card.py` is where anything is inferred from them.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable
from pathlib import Path

from aoe2planner.gamedata import GameData

DATA = GameData.load()
CATALOGUE = DATA.resource_nodes["_catalogue"]
# Every unit name to its upgrade line, written by tools/fetch_card_icons.py.
UNIT_LINES: dict[str, dict] = json.loads(Path(__file__).with_name("units.json").read_text(encoding="utf-8"))

# Gaia newer than the .dat civdata.json was extracted from, so a right-click on
# one would set no job and the move would vanish from the card. Names and kinds
# are from AoE2ScenarioParser's unit tables (KSneijders), where each shares its
# description with the wild boar or the deer. Predators are left out: a
# villager sent at a wolf is fighting it, not gathering. 1613 is in no table;
# it is the forest every Arena base is ringed by.
NEW_GAIA = {
    1924: ("Walrus", "boar"), 2737: ("Elk", "boar"),
    2735: ("Seal", "deer"), 2739: ("Pheasant", "deer"),
    2731: ("Spruce", "wood"), 2732: ("Spruce (snow)", "wood"), 2733: ("Bush D", "wood"),
    1613: ("Arena forest", "wood"),
}
# 2556 is what the Muisca place at a lumber camp's time and again at a mining
# camp's; 1889 the Khitans' farm.
NEW_BUILDINGS = {2556: "Settlement", 1889: "Pasture"}

BOAR_TYPES = {48, 810, 822, 936, 1139, 1301, 2589}
DROPSITES = {"Lumber Camp": "wood", "Mill": "mill", "Mining Camp": "mine", "Farm": "farm",
             "Pasture": "pasture", "Folwark": "mill", "Mule Cart": "mine", "Settlement": "any"}
FIELDS = {"Farm", "Pasture"}  # the work itself rather than somewhere to take it
AGE_TECHS = {"Feudal Age": "feudal", "Castle Age": "castle", "Imperial Age": "imperial"}
UNPARSED = {"SPECIAL", "UNGARRISON"}  # mgz reads their unit ids a byte out of place
LAMED = {"sheep", "boar", "deer"}  # what a villager takes off the enemy rather than works
SOLDIERING = {"FORMATION", "PATROL", "STANCE", "DE_ATTACK_MOVE", "ATTACK_GROUND", "GUARD", "FOLLOW"}
BUILDING = {"BUILD", "REPAIR", "WALL"}
MATCH = 10.0           # a deleted id first named this long after a placement could be anything
BUILD_FALLBACK = 60.0  # seconds to build what the game data does not know
TOWN_CENTRE = 109
TOWERS = {"Watch Tower", "Guard Tower", "Keep", "Bombard Tower", "Donjon"}
CASTLES = {"Castle", "Krepost"}
PRODUCTION = {"Barracks", "Archery Range", "Stable"}
REACH = 40.0           # tiles from an enemy's Town Centre a spot counts as forward within
FORWARD = 0.75         # and how much nearer to it than to any of the team's own


def job_of_type(type_id: int) -> str | None:
    if type_id in NEW_GAIA:
        return NEW_GAIA[type_id][1]
    entry = CATALOGUE.get(str(type_id))
    if not entry:
        return None
    if entry["job"] == "hunt":
        return "boar" if type_id in BOAR_TYPES else "deer"
    return entry["job"]


def building_name(payload: dict) -> str:
    known = payload.get("building") or NEW_BUILDINGS.get(payload.get("building_id"))
    return known or f"#{payload.get('building_id')}"


def secs(action) -> float:
    return action.timestamp.total_seconds()


@dataclass
class Node:
    id: int
    type: int
    name: str | None
    x: float
    y: float
    owner: int


@dataclass
class Placed:
    t: float
    name: str
    x: float
    y: float


@dataclass
class Event:
    t: float
    kind: str  # assign | build | forward | rally | research | queue
    ids: list = field(default_factory=list)
    job: str | None = None
    building: str | None = None
    what: str | None = None
    amount: int = 1
    site: tuple[str, float] | None = None  # the building placed or worked on, and when it was placed
    target: int | None = None
    at: tuple[float, float] | None = None  # where the command sends its units


class Replay:
    def __init__(self, match):
        self.match = match
        self.nodes: dict[int, Node] = {}
        for o in match.gaia:
            self.nodes[o.instance_id] = Node(o.instance_id, o.object_id, o.name, o.position.x, o.position.y, 0)
        for p in match.players:
            for o in p.objects:
                self.nodes[o.instance_id] = Node(o.instance_id, o.object_id, o.name, o.position.x,
                                                 o.position.y, p.number)
        self.last_starting_id = max(self.nodes)
        self._resolve_selections()
        self._bound_ids, self._bounds = self._creation_bounds()
        self.commanded = {i for a in match.actions if a.type.name not in UNPARSED | {"DELETE"}
                          for i in a.payload.get("object_ids") or [] if isinstance(i, int)}

        self._sites: dict[str, list] = defaultdict(list)
        self._trees: dict[tuple, list] = defaultdict(list)
        for n in self.nodes.values():
            job = job_of_type(n.type)
            if job:
                self._sites[job].append((n.x, n.y))
            if job == "wood":
                self._trees[(int(n.x) // 4, int(n.y) // 4)].append((n.x, n.y))

    def _resolve_selections(self) -> None:
        """An empty unit list means "the units I last sent this kind of command
        to", remembered per player and per command type: a move straight after
        queueing at the Town Centre is not a move of the Town Centre."""
        last: dict[tuple, list] = {}
        for a in self.match.actions:
            if a.player is None or "object_ids" not in a.payload:
                continue
            key = (a.player.number, a.type.name)
            if a.payload["object_ids"]:
                last[key] = a.payload["object_ids"]
            else:
                a.payload["object_ids"] = list(last.get(key, []))

    def _creation_bounds(self) -> tuple[list, list]:
        """Ids are handed out in creation order, so nothing is younger than the
        first command naming any larger id. With eight players commanding new
        units all game, that bound sits close to the real moment."""
        first: dict[int, float] = {}
        for a in self.match.actions:
            if a.type.name in UNPARSED:
                continue
            ids = list(a.payload.get("object_ids") or [])
            if isinstance(a.payload.get("target_id"), int):
                ids.append(a.payload["target_id"])
            for i in ids:
                if isinstance(i, int) and self.last_starting_id < i < 1_000_000:
                    first.setdefault(i, secs(a))
        ids = sorted(first)
        bounds, low = [], math.inf
        for i in reversed(ids):
            low = min(low, first[i])
            bounds.append(low)
        return ids, bounds[::-1]

    def created_by(self, object_id: int) -> float:
        k = bisect_right(self._bound_ids, object_id) - 1
        if k >= 0 and self._bound_ids[k] == object_id:
            return self._bounds[k]
        return self._bounds[k + 1] if k + 1 < len(self._bounds) else math.inf

    def forward(self, enemies: set[int]) -> Callable[[float, float], bool]:
        """Whether a spot is at the enemy's end of the map: within `REACH` of
        an enemy's starting Town Centre and clearly nearer it than any Town
        Centre of one's own team. A castle half way across the map, or one by
        an ally's base that happens to face the enemy, defends. A nomad start
        has no Town Centres to measure from, so nothing is forward."""
        homes: dict[int, tuple[float, float]] = {}
        for n in self.nodes.values():
            if n.type == TOWN_CENTRE and n.owner:
                homes.setdefault(n.owner, (n.x, n.y))
        theirs = [homes[n] for n in enemies if n in homes]
        ours = [xy for n, xy in homes.items() if n not in enemies]
        if not theirs or not ours:
            return lambda x, y: False

        def ahead(x: float, y: float) -> bool:
            near = min(math.dist((x, y), xy) for xy in theirs)
            return near <= REACH and near < FORWARD * min(math.dist((x, y), xy) for xy in ours)
        return ahead

    def trees_near(self, x: float, y: float, reach: float = 3.0) -> int:
        cx, cy = int(x) // 4, int(y) // 4
        return sum(1 for i in (-1, 0, 1) for j in (-1, 0, 1)
                   for tx, ty in self._trees[(cx + i, cy + j)] if math.dist((x, y), (tx, ty)) <= reach)

    def tree_job(self, x: float, y: float) -> str:
        return "wood" if self.trees_near(x, y) >= 4 else "straggler"

    def nearest(self, x: float, y: float, jobs: set, within: float) -> str | None:
        best, best_d = None, within
        for job in jobs:
            for sx, sy in self._sites[job]:
                d = math.dist((x, y), (sx, sy))
                if d <= best_d:
                    best, best_d = job, d
        if best == "wood":
            return self.tree_job(x, y)
        return best


class PlayerLog:
    def __init__(self, replay: Replay, number: int, enemies: set[int] = frozenset()):
        self.r = replay
        self.player = next(p for p in replay.match.players if p.number == number)
        self.forward = replay.forward(enemies)
        self.actions = [a for a in replay.match.actions if a.player is self.player]
        own = [n for n in replay.nodes.values() if n.owner == number]
        self.tcs = {n.id for n in own if n.name == "Town Center"}
        self.start_villagers = [n.id for n in own if n.name == "Villager"]
        self.cancelled = self._cancelled()
        self.placed = [Placed(secs(a), building_name(a.payload), a.position.x, a.position.y)
                       for a in self.actions if self.built(a)]
        self.unresolved: Counter = Counter()
        self.soldiers = self._soldiers()

    def _cancelled(self) -> set[int]:
        """The BUILD commands whose foundation was deleted before one villager
        could have finished it, as the `id()` of each action.

        A replay never says a building was finished, and a DELETE names an id
        and nothing else. But ids are handed out in creation order, so an id
        nobody ever commanded belongs to the last thing this player placed
        before anything that new was named (`Replay.created_by`). Where that is
        more than `MATCH` seconds back, which placement it was is a guess, and
        the building stands; so does one destroyed before it was finished,
        which no command records at all."""
        placing = [a for a in self.actions if a.type.name in ("BUILD", "WALL")]
        out: set[int] = set()
        for a in self.actions:
            if a.type.name != "DELETE":
                continue
            for d in a.payload.get("object_ids") or []:
                if not isinstance(d, int) or d <= self.r.last_starting_id or d in self.r.commanded:
                    continue
                bound = self.r.created_by(d)
                placed = max((b for b in placing if secs(b) <= bound), key=secs, default=None)
                if placed is None or placed.type.name != "BUILD" or bound - secs(placed) > MATCH:
                    continue
                building = DATA.unit_by_id(placed.payload.get("building_id")) or {}
                if secs(a) - secs(placed) <= (building.get("build_time") or BUILD_FALLBACK):
                    out.add(id(placed))
        return out

    def built(self, action) -> bool:
        """A placed building that was not cancelled."""
        return action.type.name == "BUILD" and action.position is not None and id(action) not in self.cancelled

    def _soldiers(self) -> set[int]:
        """New units that were given soldiers' commands and never did a
        villager's work all game. A replay never says what a unit is, and a
        militia right-clicked onto a berry bush reads like a villager sent
        there: three of them once put a Roman four villagers over what one
        Town Centre could have trained. Villagers selected with soldiers get
        soldiers' commands too, so it is the work that decides."""
        drilled, worked = set(), set()
        for a in self.actions:
            ids = a.payload.get("object_ids") or []
            kind = a.type.name
            if kind in SOLDIERING:
                drilled.update(ids)
            elif kind in BUILDING:
                worked.update(ids)
            elif kind == "ORDER":
                node = self.r.nodes.get(a.payload.get("target_id"))
                if node is not None and job_of_type(node.type) in ("wood", "gold", "stone"):
                    worked.update(ids)
        return {i for i in drilled - worked if isinstance(i, int) and i > self.r.last_starting_id}

    def building_at(self, x: float, y: float, t: float) -> Placed | None:
        best, best_d = None, math.inf
        for b in self.placed:
            if b.t > t:
                break
            d = math.dist((x, y), (b.x, b.y))
            if d <= {"Farm": 2.2, "Town Center": 2.2, "Pasture": 2.9}.get(b.name, 1.6) and d < best_d:
                best, best_d = b, d
        return best

    def dropsite_job(self, b: Placed) -> str | None:
        kind = DROPSITES.get(b.name)
        if kind in ("wood", "farm", "pasture"):
            return kind
        if kind == "mill":
            return "berries" if self.r.nearest(b.x, b.y, {"berries"}, 6.0) else "farm"
        if kind == "mine":
            return self.r.nearest(b.x, b.y, {"gold", "stone"}, 6.0)
        if kind == "any":
            return self.r.nearest(b.x, b.y, {"wood", "gold", "stone", "berries"}, 6.0)
        return None

    def target(self, a) -> tuple[str | None, Placed | None]:
        """The job a right-click sets, and the building it landed on if any."""
        node = self.r.nodes.get(a.payload.get("target_id"))
        if node is not None:
            job = job_of_type(node.type)
            if job == "wood":
                job = self.r.tree_job(node.x, node.y)
            if not job and node.owner != self.player.number:
                self.unresolved[(node.type, node.name)] += 1
            return job, None
        if a.position is None:
            return None, None
        b = self.building_at(a.position.x, a.position.y, secs(a))
        return (self.dropsite_job(b), b) if b else (None, None)

    def rally_job(self, a) -> str | None:
        target_type = a.payload.get("target_type")
        if isinstance(target_type, int) and target_type >= 0:
            job = job_of_type(target_type)
            if job == "wood" and a.position is not None:
                job = self.r.tree_job(a.position.x, a.position.y)
            if job:
                return job
        job, _ = self.target(a)
        if job or a.position is None:
            return job
        return self.r.nearest(a.position.x, a.position.y,
                              {"sheep", "boar", "deer", "berries", "wood", "gold", "stone"}, 2.5)

    def villagers(self, ids) -> list[int]:
        return [i for i in ids if i in self.start_villagers
                or i > self.r.last_starting_id and i not in self.soldiers]

    def spot(self, a) -> tuple[float, float] | None:
        """Where a command sends its units: the click, or what was clicked."""
        if a.position is not None:
            return a.position.x, a.position.y
        node = self.r.nodes.get(a.payload.get("target_id"))
        return (node.x, node.y) if node else None

    def ahead(self, a) -> bool:
        """Whether a command sends its units forward (`Replay.forward`)."""
        at = self.spot(a)
        return at is not None and self.forward(*at)

    def events(self) -> list[Event]:
        """Villagers sent forward are on a job of their own, "forward", which is
        no work: walking there, putting up or helping to build anything there,
        fighting there, or going for the enemy's sheep, boar or deer -- laming.
        Gathering wood, gold or stone there is work like anywhere else. A
        forward walk or fight is a `forward` event rather than an `assign`,
        because its units need not be villagers: a men-at-arms nobody gave a
        soldier's command reads like one, and only work proves a villager.
        `what` says which of them a forward event is."""
        out: list[Event] = []
        for a in self.actions:
            t, kind, p = secs(a), a.type.name, a.payload
            at = self.spot(a)
            if self.built(a):
                b = Placed(t, building_name(p), a.position.x, a.position.y)
                job = self.dropsite_job(b) or ("forward" if self.ahead(a) else None)
                out.append(Event(t, "build", self.villagers(p.get("object_ids", [])),
                                 job=job, building=b.name, site=(b.name, t), at=at))
            elif kind == "WALL":
                # A dragged wall is its own command, not a BUILD.
                out.append(Event(t, "build", self.villagers(p.get("object_ids", [])),
                                 job="forward" if self.ahead(a) else None, building=building_name(p), at=at))
            elif kind == "ORDER":
                ids = self.villagers(p.get("object_ids", []))
                job, b = self.target(a) if ids else (None, None)
                if not ids:
                    continue
                if self.ahead(a) and (job in LAMED or not job):
                    what = "lame" if job else "build" if b else "fight"
                    out.append(Event(t, "forward", ids, job="forward", building=b.name if b else None,
                                     what=what, at=at))
                elif job:
                    out.append(Event(t, "assign", ids, job=job, building=b.name if b else None,
                                     site=(b.name, b.t) if b else None, target=p.get("target_id"), at=at))
            elif kind == "MOVE" and self.ahead(a):
                ids = self.villagers(p.get("object_ids", []))
                if ids:
                    out.append(Event(t, "forward", ids, job="forward", what="walk", at=at))
            elif kind == "GATHER_POINT" and set(p.get("object_ids", [])) & self.tcs:
                target = p.get("target_id")
                out.append(Event(t, "rally", job=self.rally_job(a),
                                 target=target if isinstance(target, int) and target >= 0 else None, at=at))
            elif kind == "RESEARCH":
                out.append(Event(t, "research", ids=list(p.get("object_ids", [])),
                                 what=p.get("technology") or f"#{p.get('technology_id')}"))
            elif kind == "DE_QUEUE":
                out.append(Event(t, "queue", ids=list(p.get("object_ids", [])),
                                 what=p.get("unit") or f"#{p.get('unit_id')}", amount=p.get("amount", 1)))
        return out
