"""
One player's opening as a card in the cards/ app's format.

Read straight off the replay: every building and when, every tech, the age
landings, the Town Centre's gather point, which villagers were right-clicked
onto what. Inferred, because a replay holds commands and not state: how many
villagers the Town Centre trained -- a queue click without the food is recorded
like any other -- and so where a villager nobody ever commanded was working.

The shape mirrors `cards/src/model/card.ts`; the app reads it through
`migrate.ts` like any imported file, so a field missing here is filled there.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter, defaultdict
from functools import cached_property
from pathlib import Path

from .game import (AGE_TECHS, CASTLES, DATA, DROPSITES, FIELDS, PRODUCTION, TOWERS, UNIT_LINES, Event,
                   PlayerLog, Replay)

ICON_DIR = Path(__file__).resolve().parents[1] / "cards" / "public" / "icons" / "aoe2"
ICON_KEYS = {p.stem for p in ICON_DIR.glob("*.png")}

JOB_ICON = {"forward": "command-forward", "sheep": "gaia-sheep", "hunt": "gaia-boar", "berries": "gaia-berries",
            "straggler": "gaia-straggler", "wood": "resource-wood", "gold": "resource-gold",
            "stone": "resource-stone", "farm": "building-farm", "pasture": "building-pasture",
            "fish": "gaia-fish"}
# Boar and deer are one job on a card: what the villagers do is hunt. Which
# animal it was survives only as the deer in the row's extras, one per deer.
HUNT = {"boar", "deer"}
AGE_ICON = {"feudal": "tech-feudal-age", "castle": "tech-middle-age", "imperial": "tech-imperial-age"}
AGE_SECONDS = {"feudal": 130, "castle": 160, "imperial": 190}
UNIT_ALIASES = {"Scout Cavalry": "unit-scout", "Camel Rider": "unit-camel"}
BUILDING_ALIASES = {"Palisade Gate": "building-gate"}
TECH_ALIASES = {"Wheelbarrow": "tech-wheel-barrow"}
TOWN_CENTRE_TECHS = {"Loom", "Wheelbarrow", "Hand Cart", "Town Watch", "Town Patrol"}
# What a trip forward has to put up there, or help to, for its villagers to be
# forward on the card.
FRONT = TOWERS | CASTLES | PRODUCTION | {"Town Center", "Siege Workshop"}
PHASES = [("Dark Age", "dark"), ("Going Feudal", "transition"), ("Feudal Age", "feudal"),
          ("Going Castle", "transition"), ("Castle Age", "castle")]

VILLAGER_SECONDS = 25.0
VILLAGER_SPEED = DATA.unit_by_id(83)["speed"]  # tiles a second
SPACING = 0.9       # of a villager's time: slack for a faster Town Centre, as Persian age-ups run 5-9% under the nominal time
REACTED = 5.0       # a gather point moved this soon before a villager's estimated spawn was moved for it
BRIEF = 30.0        # a task replaced this soon, or before the villager got there, is not on the card
ERRAND = 15.0       # but one to gold, stone or a building site is from this soon: "50 stone", a camp for others
ERRANDS = {"gold", "stone"}
FILLER = 90.0       # sheep eaten between two hunts for under this were eaten while the next animal came in
FIRST_ORDER = 15.0  # how long before a step a camp its villager put up, or a deer it was sent at, still belongs to it
ON_THE_WAY = 45.0   # and how long after: a camp the same villagers put up later is a camp of its own
MERGE = 45.0        # commands this close with the same meaning are one row
WAITED = 1.0        # a click this close to its turn may have found the Town Centre idle
SWAP = 90.0         # one villager each way inside a phase is a swap, not a change of plan
CASTLE_TAIL = 60.0


def slug(name: str, sep: str) -> str:
    return re.sub(r"[^a-z0-9]+", sep, name.lower()).strip(sep)


def known(key: str) -> str | None:
    return key if key in ICON_KEYS else None


def tech_icon(name: str) -> str | None:
    if name in AGE_TECHS:
        return AGE_ICON[AGE_TECHS[name]]
    # An upgrade to a unit -- Man-at-Arms, Crossbowman -- wears the unit, as
    # its button in the game does.
    return known(TECH_ALIASES.get(name) or "tech-" + slug(name, "-")) or unit_icon(name)


def building_icon(name: str) -> str | None:
    return known(BUILDING_ALIASES.get(name) or "building-" + slug(name, "_"))


def unit_icon(name: str) -> str | None:
    # An upgrade without an icon of its own wears its line's: an Elite
    # Skirmisher is drawn as the Skirmisher.
    return known(UNIT_ALIASES.get(name) or "unit-" + slug(name, "_")) or (UNIT_LINES.get(name) or {}).get("icon")


def card_job(job: str | None) -> str | None:
    return "hunt" if job in HUNT else job


def clock(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def _id() -> str:
    return str(uuid.uuid4())


def icon(key: str, caption: str = "") -> dict:
    return {"kind": "icon", "id": _id(), "icon": key, "caption": caption}


def count(value: int | str, total: str = "") -> dict:
    return {"kind": "count", "id": _id(), "value": str(value), "total": total}


def text(value: str) -> dict:
    return {"kind": "text", "id": _id(), "text": value}


def squeeze(items: list[dict]) -> list[dict]:
    """Three of a thing or more is one captioned ×N; two stay two, the way the
    sample card draws its pair of houses."""
    seen = Counter(i["icon"] for i in items if i["kind"] == "icon")
    out, done = [], set()
    for i in items:
        if i["kind"] == "icon" and seen[i["icon"]] >= 3:
            if i["icon"] not in done:
                done.add(i["icon"])
                out.append(icon(i["icon"], f"×{seen[i['icon']]}"))
            continue
        out.append(i)
    return out


def _in_order(timed: list[tuple[float, dict]]) -> list[dict]:
    return squeeze([item for _, item in sorted(timed, key=lambda x: x[0])])


def _place(items: list[dict], label: str = "") -> dict:
    return {"items": items, "label": label}


def _step(to: list[dict], label: str = "", extras: list[dict] | None = None) -> dict:
    """A row with only its new villagers' column. `moveTo` is always written,
    even empty: a row without it is the app's older one-sentence shape, which
    `migrate.ts` turns into a move wherever there is a source."""
    return {"id": _id(), "to": _place(to, label), "toFrom": None, "moveTo": None, "from": None,
            "extras": extras or []}


def _work(job: str, villagers: int = 0, via: list[dict] | None = None) -> dict:
    """A place: how many, the work, then what went up on the way. Forward is
    no work, so it wears the game's own aggressive-stance button, which names
    none: "5 forward tower"."""
    return _place(([count(villagers)] if villagers else []) + [icon(JOB_ICON[job])] + (via or []))


def _unit(row: dict, step: dict) -> dict:
    """A written row, and which column it fills: `new` names the works the
    first column is about on a row with nothing in the second -- where new
    villagers went and where any who joined them came from, or nothing for a
    Town Centre tech -- `move` the source and destination on a row with only
    a move."""
    unit = {"t": row["t"], "step": step, "new": None, "move": None}
    if row["research"]:
        unit["new"] = set()
    elif row["to"] is not None and row["new"]:
        unit["new"] = {row["to"], row["from"]} - {None}
    elif row["to"] is not None and row["from"]:
        unit["move"] = (row["from"], row["to"])
    return unit


def _paired(line: list[dict]) -> list[dict]:
    """A move shares the row beside it when that row has nothing in the
    second column: "3 boar" and "1 berries ← boar" are one row, and so are
    Loom and the move after it, however far apart in time, since nothing on
    the card comes between them. Not where the move goes to a work the first
    column names: the move is counted first, so the figure under it would
    miss what the first column then does there."""
    out: list[dict] = []
    for unit in line:
        last = out[-1] if out else None
        pair = last and sorted((last, unit), key=lambda u: u["new"] is None)
        if (pair and pair[0]["new"] is not None and pair[1]["move"]
                and pair[1]["move"][1] not in pair[0]["new"]):
            new, move = pair
            out[-1] = {"t": last["t"], "new": None, "move": None,
                       "step": move["step"] | {"to": new["step"]["to"], "toFrom": new["step"]["toFrom"],
                                               "extras": new["step"]["extras"] + move["step"]["extras"]}}
        else:
            out.append(unit)
    return out


def _merged(steps: list[dict]) -> list[dict]:
    """Rows next to each other whose first columns send new villagers to one
    work are one row, when only one of them has a move beside it: "3 sheep",
    "1 farm ← sheep" and then "1 sheep" are "4 sheep", "1 farm ← sheep". The
    move is counted before either, so every figure the merged row ends on is
    the one the second row ended on."""
    def work(step: dict) -> str | None:
        items = step["to"]["items"]
        plain = (len(items) >= 2 and items[0]["kind"] == "count" and items[0]["value"].isdigit()
                 and items[1]["kind"] == "icon" and not step["to"]["label"])
        return items[1]["icon"] if plain else None

    out: list[dict] = []
    for step in steps:
        last = out[-1] if out else None
        if (last and work(step) and work(step) == work(last) and not step["toFrom"]
                and not (last["moveTo"] and step["moveTo"])):
            a, b = last["to"]["items"], step["to"]["items"]
            total = count(int(a[0]["value"]) + int(b[0]["value"]))
            out[-1] = last | {"to": _place([total, a[1]] + squeeze(a[2:] + b[2:])),
                              "moveTo": last["moveTo"] or step["moveTo"], "from": last["from"] or step["from"],
                              "extras": last["extras"] + step["extras"]}
        else:
            out.append(step)
    return out


def _begun(plan: list[tuple], here: tuple[float, float] | None) -> list[tuple]:
    """The commands a villager acted on. A run of commands to one work counts
    only if the villager kept it for `BRIEF` -- `ERRAND` if it was gold, stone
    or putting something up, which a build order asks for in short stints --
    and long enough to reach its first target from wherever the previous
    command had got them to: sent to the wood and on to the boar before
    reaching the trees, they never cut any. The walk is estimated in a
    straight line at a villager's speed. Sheep between two hunts count from
    `FILLER`: the sheep under the Town Centre are what a crew eats while the
    next boar is lured or deer pushed, and a build order says nothing of
    it."""
    runs: list[list[tuple]] = []
    for p in plan:
        if runs and runs[-1][-1][1] == p[1]:
            runs[-1].append(p)
        else:
            runs.append([p])
    kept: list[tuple] = []
    for k, run in enumerate(runs):
        ends = runs[k + 1][0][0] if k + 1 < len(runs) else math.inf
        arrive = run[0][0]
        for j, p in enumerate(run):
            at = p[-1]
            if at is None or here is None:
                here = at or here
                continue
            walk = math.dist(here, at) / VILLAGER_SPEED
            if j == 0:
                arrive = p[0] + walk
            share = min(1.0, ((run[j + 1][0] if j + 1 < len(run) else ends) - p[0]) / walk) if walk else 1.0
            here = (here[0] + (at[0] - here[0]) * share, here[1] + (at[1] - here[1]) * share)
        brief = ERRAND if any(p[1] in ERRANDS or p[4] for p in run) else BRIEF
        if run[0][1] == "sheep" and 0 < k < len(runs) - 1 and runs[k - 1][0][1] == runs[k + 1][0][1] == "hunt":
            brief = FILLER
        if k + 1 == len(runs) or k == 0 and run[0][1] == "idle" or ends - run[0][0] >= brief and ends >= arrive:
            kept.extend(run)
    return kept


def _settled(kept: list[tuple]) -> list[tuple]:
    """A villager's steps: the same work twice is one step."""
    steps: list[tuple] = []
    for step in kept:
        if not steps or steps[-1][1] != step[1]:
            steps.append(step)
    return steps


def _row(t: float, src: str | None, dst: str | None, via: set | None = None,
         who: set | None = None, new: set | None = None, deer: set | None = None) -> dict:
    """`via` holds the drop-off sites put up on the way, as (name, placed at):
    `via_moved` by the villagers taken off `src` (`who`), `via_new` by the new
    ones (`new`) -- `via` goes to whichever started the row. The other
    buildings of the moment go up on the way too (`built`); techs are only
    mentioned (`extras`). `research` marks a Town Centre tech's own row."""
    return {"t": t, "until": t, "from": src, "to": dst,
            "via_moved": (via or set()) if src else set(), "via_new": set() if src else (via or set()),
            "who": who or set(), "new": new or set(), "built": [], "extras": [],
            "deer": deer or set(), "research": False}


class Opening:
    def __init__(self, replay: Replay, number: int, enemies: set[int] = frozenset()):
        self.r = replay
        self.log = PlayerLog(replay, number, enemies)
        self.events = self.log.events()
        self.ages, self.clicked = self._ages()
        if "castle" in self.ages:
            self.end = self.ages["castle"][1] + CASTLE_TAIL
        else:
            self.end = self.ages["feudal"][1] + 300 if "feudal" in self.ages else 900.0

    def _ages(self) -> tuple[dict[str, tuple[float, float]], dict[str, float]]:
        """age -> (research started, landing), and age -> click. The landing is the game's own
        message; the click is the last one before it. Clicks without the food
        are recorded too, but none comes after the one that starts the
        research: in 144 age-ups not one fell inside its research time.
        Reading the click off the nominal time instead dates a Persian or
        Malay click too early, since they research faster. The research
        starts at the click, or later if villagers queued before it were still
        to come out -- the nominal time back from the landing says when, and
        in 101 of those 144 one was."""
        names = {"FEUDAL_AGE": "feudal", "CASTLE_AGE": "castle", "IMPERIAL_AGE": "imperial"}
        landed: dict[str, float] = {}
        for u in self.r.match.uptimes:
            if u.player is self.log.player and u.age.name in names:
                landed.setdefault(names[u.age.name], u.timestamp.total_seconds())
        out, clicked = {}, {}
        for age, landing in landed.items():
            clicks = [e.t for e in self.events
                      if e.kind == "research" and AGE_TECHS.get(e.what) == age and e.t <= landing]
            clicked[age] = clicks[-1] if clicks else landing - AGE_SECONDS[age]
            out[age] = (max(clicked[age], landing - AGE_SECONDS[age]), landing)
        return out, clicked

    def section_of(self, t: float) -> str:
        name = "Dark Age"
        for age, going, there in (("feudal", "Going Feudal", "Feudal Age"), ("castle", "Going Castle", "Castle Age")):
            if age in self.ages:
                click, landing = self.ages[age]
                if t >= click:
                    name = going
                if t >= landing:
                    name = there
        return name

    # ---------------------------------------------------------- villagers

    @cached_property
    def _loom(self) -> Event | None:
        loom = [e for e in self.events if e.kind == "research" and e.what == "Loom" and set(e.ids) & self.log.tcs]
        return loom[-1] if loom else None

    def _busy(self, loom_done: float | None) -> list[tuple[float, float]]:
        spans = list(self.ages.values())
        if self._loom and loom_done is not None:
            spans.append((loom_done - self._loom.takes, loom_done))
        return sorted(spans)

    def _tc_start(self, t: float) -> float:
        """When a Town Centre tech clicked at `t` started: one clicked after an
        age-up waits behind it in the queue until the age lands."""
        for age in ("feudal", "castle"):
            if age in self.ages and self.clicked[age] <= t < self.ages[age][1]:
                return self.ages[age][1]
        return t

    def _tc_done(self, research: Event, spawns: list[tuple[float, int | None]] | None = None) -> float:
        """When a Town Centre tech was done: its click and its time, or later
        if villagers were queued ahead of it, as whichever of `_chained` and
        `_queued_ahead` says later."""
        begun = self._tc_start(research.t)
        done = max(self._chained(research), self._queued_ahead(research, spawns) + research.takes)
        for start, _ in self.ages.values():
            if begun < start <= done:
                return start - 0.001
        return done

    def _chained(self, research: Event) -> float:
        """The queue is first in, first out, and the next age-up's start is
        known from its landing, so if the Town Centre was still busy at that
        click, the tech was done just in time for whatever was queued in
        between: Loom clicked behind three villagers, with Feudal next, is
        done when Feudal starts. That holds only if each thing in between
        waited for its turn; one clicked as its turn came may have found the
        Town Centre idle for any time before it. A villager clicked without
        the food counts as one that waited."""
        begun = self._tc_start(research.t)
        done = begun + research.takes
        tc = set(research.ids) & self.log.tcs
        age_ups = [e for e in self.events if e.kind == "research" and e.what in AGE_TECHS
                   and e.t > research.t and set(e.ids) & tc]
        age = next((AGE_TECHS[e.what] for e in age_ups if self.clicked.get(AGE_TECHS[e.what]) == e.t), None)
        if age and self.clicked[age] < self.ages[age][0] - WAITED:
            between = {}
            for e in self.events:
                if (research.t < e.t < self.clicked[age] and set(e.ids) & tc
                        and (e.kind == "queue" or e.kind == "research" and e.what not in AGE_TECHS)):
                    between[e.what if e.kind == "research" else id(e)] = e
            end = self.ages[age][0]
            for e in sorted(between.values(), key=lambda e: e.t, reverse=True):
                end -= e.takes * e.amount
                if e.t > end - WAITED:
                    break
            else:
                done = max(done, end)
        for start, _ in self.ages.values():
            if begun < start <= done:
                return start - 0.001
        return done

    def _queued_ahead(self, research: Event, spawns: list[tuple[float, int | None]] | None = None) -> float:
        """When the villagers queued ahead of a Town Centre tech had come out.
        Every villager trained before the next age-up started was queued ahead
        of the tech, except those clicked after it, and none came out sooner
        than if every click had been paid for at once. That dates Loom clicked
        behind a full queue when the Town Centre went idle before the age-up,
        which leaves `_chained` nothing to count back from. "Trained" is
        what `spawns` reads, so this is an inference, not a bound."""
        tc = set(research.ids) & self.log.tcs
        nxt = min((age for age, click in self.clicked.items() if click > research.t and age in self.ages),
                  key=lambda age: self.clicked[age], default=None)
        if nxt is None:
            return research.t
        clicks_until, horizon = self.clicked[nxt], self.ages[nxt][0]
        if any(e.kind == "build" and e.building == "Town Center" and e.t < horizon for e in self.events):
            return research.t
        last = {e.what: e for e in self.events if e.kind == "research"}
        ends: list[float] = []
        free, after = 0.0, 0
        for e in self.events:
            if not set(e.ids) & tc or e.t >= clicks_until:
                continue
            if e.kind == "queue" and e.what == "Villager":
                for _ in range(e.amount):
                    free = max(free, e.t) + e.takes
                    if e.t < research.t:
                        ends.append(free)
                    else:
                        after += 1
            elif e.kind == "research" and e.what in AGE_TECHS:
                if AGE_TECHS[e.what] in self.ages and self.clicked[AGE_TECHS[e.what]] == e.t:
                    free = max(free, self.ages[AGE_TECHS[e.what]][1])
            elif e.kind == "research" and last[e.what] is e:
                free = max(free, e.t) + e.takes
        if not ends:
            return research.t
        # Villagers out before the first click could have trained one came
        # with the civilisation, not from this queue.
        first = ends[0] - (1 - SPACING) * VILLAGER_SECONDS
        trained = sum(1 for t, _ in (self.spawns if spawns is None else spawns) if first <= t < horizon)
        ahead = min(trained - after, len(ends))
        return ends[ahead - 1] if ahead > 0 else research.t

    @cached_property
    def spawns(self) -> list[tuple[float, int | None]]:
        """Loom takes a villager's time from the queue, and when depends on
        how many villagers were ahead of it, which depends on where it was:
        each is read again with the other's answer until Loom stops moving.
        It only ever moves later, and never past the age-up it came before."""
        done = self._chained(self._loom) if self._loom else None
        while True:
            out = self._spawns(self._busy(done))
            later = self._tc_done(self._loom, out) if self._loom else done
            if done is None or later <= done + 0.5:
                return out
            done = later

    def _spawns(self, busy: list[tuple[float, float]]) -> list[tuple[float, int | None]]:
        """(time, id) for every villager the Town Centre trained, the id None
        where nobody ever commanded the villager so the replay never names it.

        A commanded villager is placed at the latest moment one Town Centre
        could have trained it: its id bounds it, and so does every villager
        after it, each of which needed the Town Centre for a villager's time.
        Its id alone is not enough, because a bound can be late by a minute
        and then the gap in front of it looks like villagers nobody commanded.
        Between two commanded villagers the Town Centre is assumed to have
        kept training while queue clicks were outstanding and the next one
        still had room, and never while it was researching an age or Loom."""
        step = VILLAGER_SECONDS

        def clear(end: float) -> float:
            """The latest training ending by `end` that misses every research."""
            moved = True
            while moved:
                moved = False
                for a, b in busy:
                    if end - step < b and end > a:
                        end, moved = a, True
            return end

        def after(last: float) -> float:
            nxt = last + step
            for a, b in busy:
                if a - 1 <= nxt - step < b or a < nxt <= b:
                    nxt = max(nxt, b + step)
            return nxt

        # From the second Town Centre on, two can train at once, so spacing
        # says nothing.
        second = min((e.t for e in self.events if e.kind == "build" and e.building == "Town Center"),
                     default=math.inf)
        seen = sorted({i for e in self.events if e.kind in ("assign", "build")
                       for i in e.ids if i > self.r.last_starting_id})
        landings = [landing for _, landing in self.ages.values()]
        observed: list[tuple[float, int]] = []
        later = math.inf
        for i in reversed(seen):
            bound = self.r.created_by(i)
            if bound < second:
                # Never back across a landing: more villagers just after one
                # than a Town Centre can train came with the age, as the
                # Bengalis' two do at every one.
                floor = max((t for t in landings if t <= bound), default=0.0)
                bound = max(floor, clear(min(bound, later - SPACING * step)))
            observed.append((bound, i))
            later = bound
        observed.reverse()
        queued = sorted(e.t for e in self.events if e.kind == "queue" and e.what == "Villager"
                        and set(e.ids) & self.log.tcs for _ in range(e.amount))

        out: list[tuple[float, int | None]] = []
        last = 0.0
        for t, i in observed + [(self.end, None)]:
            while True:
                nxt = after(last)
                if (after(nxt) > t + (1 - SPACING) * step
                        or sum(q <= nxt - step for q in queued) <= len(out)):
                    break
                out.append((nxt, None))
                last = nxt
            if i is None:
                break
            out.append((t, i))
            last = max(last, t)
        return [s for s in out if s[0] <= self.end]

    def rally_at(self, t: float, previous: float) -> Event | None:
        """The gather point a villager that came out at `t` walked to, the one
        before it at `previous`. A gather point moved just before `t` most
        likely moved because this villager had come out: a player sets the
        next one's the moment one appears, and `spawns` places a villager as
        late as it can. So when it was moved within `REACTED` of `t`, and one
        Town Centre could have trained the villager by then, it went where the
        gather point was before."""
        rallies = [e for e in self.events if e.kind == "rally" and e.t <= t]
        moved = len(rallies)
        while moved > 1 and rallies[moved - 2].job == rallies[-1].job:
            moved -= 1
        if (0 < moved - 1 and t - rallies[moved - 1].t <= REACTED
                and rallies[moved - 1].t - previous >= SPACING * VILLAGER_SECONDS):
            return rallies[moved - 2]
        return rallies[-1] if rallies else None

    def population_at(self, t: float) -> int:
        return len(self.log.start_villagers) + sum(1 for s, _ in self.spawns if s <= t)

    def _before_going(self, t: float) -> float:
        """No villager is added while an age is being researched, so one first
        put to work in a Going band is written in the band before it. Most were
        still in the Town Centre's queue at the click, which puts the age-up
        behind them; the rest were idle, or came from a second Town Centre."""
        for age in ("feudal", "castle"):
            if age in self.ages and self.ages[age][0] <= t < self.ages[age][1]:
                return self.ages[age][0] - 0.001
        return t

    def transitions(self) -> list[tuple]:
        """(t, villager, from, to, sites, deer), after misclicks and errands are gone.

        `deer` are the deer the villager was sent to on that step: the ids it was
        right-clicked or rallied onto, "?" for one the replay does not name.
        Villagers walk on to the next carcass by themselves, so it is the deer
        somebody chose, which is at most the deer eaten.

        `sites` are the drop-off sites the villager put up on the way, or helped
        to. They are matched to a step by its job afterwards rather than being a
        step of their own: whether a build survives as a step depends on what
        was clicked next, and a mill built by someone already on the berries
        changes no job at all. Only on the way, though: a second lumber camp
        the same crew puts up ten minutes later goes up when it went up. A trip
        forward is the exception, and keeps all it put up there."""
        plans: dict = defaultdict(list)
        built: dict = defaultdict(list)
        raised: dict = defaultdict(list)  # when each villager did something forward worth the trip
        nodes = self.r.nodes
        home = next(((nodes[i].x, nodes[i].y) for i in self.log.tcs if i in nodes), None)
        origin = {v: (nodes[v].x, nodes[v].y) for v in self.log.start_villagers if v in nodes}
        for v in self.log.start_villagers:
            plans[v].append((0.0, "idle", None, None, False, None))
        for k, (t, i) in enumerate(self.spawns):
            rally = self.rally_at(t, self.spawns[k - 1][0] if k else -math.inf)
            raw, target, at = (rally.job, rally.target, rally.at) if rally else (None, None, None)
            plans[i if i is not None else f"unseen{k}"].append((t, card_job(raw) or "idle", raw, target, False, at))
        for e in self.events:
            if e.t > self.end or e.kind not in ("assign", "build", "forward") or not e.job:
                continue
            # What goes up forward is the trip's, as a camp is its work's.
            site = (e.site if e.site and (e.site[0] in DROPSITES and e.site[0] not in FIELDS or e.job == "forward")
                    and e.t - e.site[1] <= MERGE else None)
            put_up = e.kind == "build" or e.what == "build" or site is not None
            for v in e.ids:
                if v in plans:
                    plans[v].append((e.t, card_job(e.job), e.job, e.target, put_up, e.at))
                    if site:
                        built[v].append((e.t, card_job(e.job), site))
                    if e.job == "forward" and (e.building in FRONT or e.what in ("fight", "lame")):
                        raised[v].append(e.t)

        out = []
        for v, plan in plans.items():
            plan.sort(key=lambda p: p[0])
            kept = _begun(plan, origin.get(v, home))
            steps = _settled(kept)
            # A trip forward that fought nobody, took nothing and put up
            # nothing to fight with is a walk or a team game's wall along its
            # front, not a plan: on a small map the far side of the middle is
            # forward.
            steps = _settled([step for k, step in enumerate(steps) if step[1] != "forward" or any(
                step[0] - FIRST_ORDER <= when < (steps[k + 1][0] if k + 1 < len(steps) else math.inf)
                for when in raised[v])])
            previous = None
            for k, (t, job, *_) in enumerate(steps):
                until = steps[k + 1][0] if k + 1 < len(steps) else float("inf")
                way = until if job == "forward" else min(until, t + ON_THE_WAY)
                sites = {site for when, on, site in built[v] if on == job and t - FIRST_ORDER <= when < way}
                deer = {target or "?" for when, _, raw, target, *_ in kept
                        if raw == "deer" and t - FIRST_ORDER <= when < until}
                if job != "idle":
                    out.append((t, v, previous, job, sites, deer))
                previous = job
        return sorted(out, key=lambda x: x[0])

    # ---------------------------------------------------------------- rows

    def rows(self) -> list[dict]:
        """`who` are the villagers a row takes from its source; `new` are the
        ones that join them there without leaving anything, so a row reads
        "1 hunt" and "hunt ← 3 sheep": three off the sheep and one more
        besides. A new villager joins the last row before it whenever that row
        went where it goes, however long ago, so one villager off the sheep
        building the mill and the next four sent after them are one row, and a
        move joins the latest move row of the phase when it is the same move."""
        moved = self.transitions()
        joins = [x for x in moved if x[2] in (None, "idle")]

        rows: list[dict] = []
        arrived: dict = {}
        left: dict = {}
        for t, v, src, dst, sites, deer in moved:
            on_since = arrived.get(v, 0.0)
            left[(v, on_since)] = t
            arrived[v] = t
            if src in (None, "idle"):
                continue
            # Only a villager already on the source when the move began joins
            # it. One that got there since -- new, or back again -- would be
            # taken off a row before the card has put it there.
            latest = next((row for row in reversed(rows) if self.section_of(row["t"]) == self.section_of(t)), None)
            same = next((row for row in reversed(rows)
                         if (t - row["until"] <= MERGE or row is latest)
                         and (row["from"], row["to"]) == (src, dst) and on_since <= row["t"]
                         and self.section_of(row["t"]) == self.section_of(t)), None)
            if same:
                same["who"].add(v)
                same["via_moved"] |= sites
                same["deer"] |= deer
                same["until"] = t
            else:
                rows.append(_row(t, src, dst, set(sites), who={v}, deer=set(deer)))
        rows = self._drop_swaps(sorted(rows, key=lambda r: r["t"]))

        def crossed(a: float, b: float, job: str) -> bool:
            lo, hi = sorted((a, b))
            return any(lo < row["t"] < hi and job in (row["from"], row["to"]) for row in rows)

        for t, v, _, dst, sites, deer in joins:
            gone = left.get((v, t), math.inf)
            t = self._before_going(t)
            # Folded into another row only while still there when it starts,
            # and never across a row that moves anyone on or off the same
            # work, or the figures between the two would count it wrong.
            host = min((row for row in rows if row["from"] and row["to"] == dst
                        and row["t"] - MERGE <= t <= row["until"] + MERGE and row["t"] < gone
                        and not crossed(row["t"], t, dst)
                        and self.section_of(row["t"]) == self.section_of(t)),
                       key=lambda row: abs(t - row["t"]), default=None)
            # Ties are the villagers moved back out of a Going band, latest last.
            last = max(reversed([row for row in rows
                                 if row["t"] <= t and self.section_of(row["t"]) == self.section_of(t)]),
                       key=lambda row: row["t"], default=None)
            if not host and last and last["to"] == dst:
                host = last
            if host:
                host["new"].add(v)
                host["via_new"] |= sites
                host["deer"] |= deer
            else:
                rows.append(_row(t, None, dst, set(sites), new={v}, deer=set(deer)))
        rows.sort(key=lambda r: r["t"])

        # The new villagers' column names a place once in a run: "1 wood ←
        # lumber camp" and then "3 wood" are "4 wood ← lumber camp", unless
        # somebody left that work in between.
        run: dict[str, dict | None] = {}
        for row in rows:
            band = self.section_of(row["t"])
            if run.get(band) and row["from"] == run[band]["to"]:
                run[band] = None
            if not row["new"]:
                continue
            if run.get(band) and run[band]["to"] == row["to"]:
                run[band]["new"] |= row["new"]
                run[band]["via_new"] |= row["via_new"]
                if not row["from"]:
                    run[band]["deer"] |= row["deer"]
                row["new"], row["via_new"] = set(), set()
            else:
                run[band] = row
        rows = [row for row in rows if row["new"] or row["from"]]

        # A deer is drawn once, on the first row that went for it, so a card's
        # deer add up to the herd rather than to the crews that shared one.
        drawn: set = set()
        for row in rows:
            row["deer"] -= drawn
            drawn |= row["deer"]
        # So is a camp: several rows' villagers can have helped build it.
        placed: set = set()
        for row in rows:
            for half in ("via_moved", "via_new"):
                row[half] -= placed
                placed |= row[half]

        working: dict = defaultdict(list)
        for t, v, _, dst, *_ in moved:
            working[v].append((t, dst))

        def work_of(ids: list, t: float) -> str | None:
            jobs = Counter(next((job for when, job in reversed(working[v]) if when <= t), None) for v in ids)
            jobs.pop(None, None)
            return jobs.most_common(1)[0][0] if jobs else None

        def attach(t: float, item: dict, part: str, work: str | None = None, by: str | None = None) -> None:
            """Onto the row being worked when it happened, never across a phase
            band: a castle dropped on landing is Castle Age, whatever came last.
            Never onto a trip forward either, or a house at home reads as built
            at the enemy's. A camp or a mill goes onto the latest row sending
            villagers to the work it serves, if one has none yet: built a minute
            after its builder reached the berries, a mill drawn beside the boar
            reads as the hunters'. Anything else goes onto the latest row
            sending villagers to its builders' work (`by`), and where the phase
            has none it is only mentioned: a barracks a wood villager put up,
            drawn beside the boar, reads as the hunters' too."""
            here = [row for row in rows if self.section_of(row["t"]) == self.section_of(t)
                    and not row["research"] and row["to"] != "forward"]
            if not here:
                here = [_row(t, None, None)]
                rows.append(here[0])
            target = here[0]
            for row in here:
                if row["t"] <= t:
                    target = row
            if work:
                serving = [row for row in here if row["t"] <= t and row["to"] == work
                           and item["icon"] not in {i.get("icon") for _, i in row["built"]}
                           | {building_icon(name) for name, _ in row["via_moved"] | row["via_new"]}]
                target = serving[-1] if serving else target
            elif by:
                theirs = [row for row in here if row["t"] <= t and row["to"] == by]
                target, part = (theirs[-1], part) if theirs else (target, "extras" if target["to"] else part)
            target[part].append((t, item))

        # A tech is dated by its last click, since none can follow the one
        # that starts it, and drawn when it is done; a unit when it comes out.
        last = {e.what: e for e in self.events if e.kind == "research" and e.t <= self.end}
        walled, queued = set(), set()
        for e in self.events:
            if e.t > self.end:
                break
            # A building no step claimed -- a house, or a camp whose builder's
            # step was a misclick or an errand -- still went up, on the way.
            if e.kind == "build" and e.building not in FIELDS and e.site not in placed:
                if e.building.endswith("Wall"):
                    if (self.section_of(e.t), e.building) in walled:
                        continue
                    walled.add((self.section_of(e.t), e.building))
                key = building_icon(e.building)
                serves = e.building in DROPSITES and e.job != "forward" and key
                attach(e.t, icon(key) if key else text(e.building), "built", card_job(e.job) if serves else None,
                       None if serves else work_of(e.ids, e.t))
            elif e.kind == "research" and e.what not in AGE_TECHS and last[e.what] is e:
                key = tech_icon(e.what)
                item = icon(key) if key else text(e.what)
                if e.what in TOWN_CENTRE_TECHS or set(e.ids) & self.log.tcs:
                    # The Town Centre's work for that while, so a step of its
                    # own like an age-up, not a mention on someone else's.
                    done = self._tc_done(e)
                    tech = _row(done, None, None)
                    tech["research"] = True
                    tech["extras"].append((done, item))
                    rows.append(tech)
                else:
                    attach(e.t + e.takes, item, "extras")
            elif (e.kind == "queue" and e.what != "Villager" and not set(e.ids) & self.log.tcs
                  and (self.section_of(e.t + e.takes), e.what) not in queued):
                # Soldiers are what the row mentions, not where villagers went.
                queued.add((self.section_of(e.t + e.takes), e.what))
                attach(e.t + e.takes, icon(unit_icon(e.what)) if unit_icon(e.what) else text(e.what), "extras")
        return sorted(rows, key=lambda r: r["t"])

    def _drop_swaps(self, rows: list[dict]) -> list[dict]:
        gone: set[int] = set()
        for i, a in enumerate(rows):
            if i in gone or a["from"] is None or len(a["who"]) != 1:
                continue
            for j in range(i + 1, len(rows)):
                b = rows[j]
                if b["t"] - a["t"] > SWAP:
                    break
                if j not in gone and len(b["who"]) == 1 and (b["from"], b["to"]) == (a["to"], a["from"]) \
                        and self.section_of(a["t"]) == self.section_of(b["t"]):
                    gone.update((i, j))
                    break
        return [r for k, r in enumerate(rows) if k not in gone]

    # ---------------------------------------------------------------- card

    def card(self, name: str, civ: str, setting: str) -> dict:
        sections = {label: {"id": _id(), "label": label, "tone": tone, "steps": []} for label, tone in PHASES}
        lines: dict[str, list[dict]] = defaultdict(list)
        for row in self.rows():
            def drawn(sites: set) -> list[dict]:
                return [icon(building_icon(name)) if building_icon(name) else text(name)
                        for name, _ in sorted(sites, key=lambda site: site[1])]

            # What goes up on the way follows the work it was built for, drawn
            # small. The other buildings of the moment go beside the new
            # villagers, or beside the moved ones on a row that has none.
            moved_via, new_via = drawn(row["via_moved"]), drawn(row["via_new"])
            (new_via if row["new"] or not row["from"] else moved_via).extend(_in_order(row["built"]))
            if row["new"] and row["from"]:
                moved_via, new_via = [], moved_via + new_via
            extras = _in_order(row["extras"])
            # A place takes icons and numbers only, so a building nothing can
            # draw is named among the extras instead.
            unnamed = [i for i in moved_via + new_via if i["kind"] != "icon"]
            moved_via = squeeze([i for i in moved_via if i["kind"] == "icon"])
            new_via = squeeze([i for i in new_via if i["kind"] == "icon"])
            line = lines[self.section_of(row["t"])]
            if row["to"] is None:
                # A Town Centre tech is the row; anything else is only mentioned.
                main = [i for i in extras if i["kind"] == "icon"] if row["research"] else []
                line.append(_unit(row, _step(new_via + main, extras=unnamed + [i for i in extras if i not in main])))
                continue
            if row["to"] == "hunt" and row["deer"]:
                herd = len(row["deer"])
                extras = ([count(herd)] if herd > 1 else []) + [icon("gaia-deer")] + extras
            step = _step([], extras=unnamed + extras)
            if row["new"] and row["from"]:
                # New villagers and a move to the same place are one place,
                # the number on the source saying how many of them moved.
                step |= {"to": _work(row["to"], len(row["new"]) + len(row["who"]), new_via),
                         "toFrom": _work(row["from"], len(row["who"]))}
            elif row["new"]:
                step["to"] = _work(row["to"], len(row["new"]), new_via)
            elif row["from"]:
                step |= {"moveTo": _work(row["to"], len(row["who"]), moved_via), "from": _work(row["from"])}
            line.append(_unit(row, step))

        for label, line in lines.items():
            sections[label]["steps"] = _merged([unit["step"] for unit in _paired(line)])

        for age, going in (("feudal", "Going Feudal"), ("castle", "Going Castle")):
            if age in self.ages:
                started, landing = self.ages[age]
                label = f"{clock(started)} → {clock(landing)} at {self.population_at(started)} vils"
                sections[going]["steps"].insert(0, _step([icon(AGE_ICON[age])], label=label))

        ages = ", ".join(f"{age.title()} {clock(landing)}" for age, (_, landing) in self.ages.items()
                         if age in ("feudal", "castle"))
        return {
            "id": _id(),
            "name": f"{name} {civ} {setting}",
            "title": f"{name} · {civ}",
            "subtitle": f"{setting} · {ages}" if ages else setting,
            "totals": True,
            "sections": [s for s in sections.values() if s["steps"]],
            "updated": 0,
        }
