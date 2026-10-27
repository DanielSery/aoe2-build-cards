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

from .game import AGE_TECHS, DROPSITES, UNIT_LINES, Event, PlayerLog, Replay

ICON_DIR = Path(__file__).resolve().parents[1] / "cards" / "public" / "icons" / "aoe2"
ICON_KEYS = {p.stem for p in ICON_DIR.glob("*.png")}

JOB_ICON = {"sheep": "gaia-sheep", "hunt": "gaia-boar", "berries": "gaia-berries",
            "straggler": "gaia-straggler", "wood": "resource-wood", "gold": "resource-gold",
            "stone": "resource-stone", "farm": "building-farm", "fish": "gaia-fish"}
# Boar and deer are one job on a card: what the villagers do is hunt. Which
# animal it was survives only as the deer in the row's extras, one per deer.
HUNT = {"boar", "deer"}
AGE_ICON = {"feudal": "tech-feudal-age", "castle": "tech-middle-age", "imperial": "tech-imperial-age"}
AGE_SECONDS = {"feudal": 130, "castle": 160, "imperial": 190}
UNIT_ALIASES = {"Scout Cavalry": "unit-scout", "Camel Rider": "unit-camel"}
BUILDING_ALIASES = {"Palisade Gate": "building-gate"}
TECH_ALIASES = {"Wheelbarrow": "tech-wheel-barrow"}
TOWN_CENTRE_TECHS = {"Loom", "Wheelbarrow", "Hand Cart", "Town Watch", "Town Patrol"}
PHASES = [("Dark Age", "dark"), ("Going Feudal", "transition"), ("Feudal Age", "feudal"),
          ("Going Castle", "transition"), ("Castle Age", "castle")]

VILLAGER_SECONDS = 25.0
SPACING = 0.9       # of a villager's time: slack for a faster Town Centre, as Persian age-ups run 5-9% under the nominal time
BRIEF = 15.0        # a task replaced this soon -- a misclick, a change of mind, a gather point left at once -- is not on the card
FIRST_ORDER = 15.0  # how long before a step a camp its villager put up, or a deer it was sent at, still belongs to it
ROUND_TRIP = 25.0   # there and straight back is an errand, not a reassignment
MERGE = 45.0        # commands this close with the same meaning are one row
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
    return {"id": _id(), "to": _place(to, label), "moveTo": None, "from": None, "extras": extras or []}


def _unit(row: dict, step: dict) -> dict:
    """A written row, and which column it fills: `new` names where the new
    villagers went on a row with only those, `move` the source and destination
    on a row with only a move."""
    unit = {"t": row["t"], "step": step, "new": None, "move": None}
    if row["to"] is not None and bool(row["new"]) != bool(row["from"]):
        unit["new" if row["new"] else "move"] = row["to"] if row["new"] else (row["from"], row["to"])
    return unit


def _paired(line: list[dict]) -> list[dict]:
    """New villagers sent to one place and a move to another at the same time
    are one row: "2 wood", then "boar ← 2 sheep", then the deer. Not where the
    new villagers go is the move's source or destination: the move is counted
    first, which would be the wrong order for those."""
    out: list[dict] = []
    for unit in line:
        last = out[-1] if out else None
        pair = last and sorted((last, unit), key=lambda u: not u["new"])
        if (pair and pair[0]["new"] and pair[1]["move"] and abs(unit["t"] - last["t"]) <= MERGE
                and pair[0]["new"] not in pair[1]["move"]):
            new, move = pair
            out[-1] = {"t": last["t"], "new": None, "move": None,
                       "step": move["step"] | {"to": new["step"]["to"],
                                               "extras": new["step"]["extras"] + move["step"]["extras"]}}
        else:
            out.append(unit)
    return out


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
    def __init__(self, replay: Replay, number: int):
        self.r = replay
        self.log = PlayerLog(replay, number)
        self.events = self.log.events()
        self.ages = self._ages()
        if "castle" in self.ages:
            self.end = self.ages["castle"][1] + CASTLE_TAIL
        else:
            self.end = self.ages["feudal"][1] + 300 if "feudal" in self.ages else 900.0

    def _ages(self) -> dict[str, tuple[float, float]]:
        """age -> (click, landing). The landing is the game's own message; the
        click is the last one before it. Clicks without the food are recorded
        too, but none comes after the one that starts the research: in 144
        age-ups not one fell inside its research time. Reading it off the
        nominal time instead dates a Persian or Malay click too early, since
        they research faster."""
        names = {"FEUDAL_AGE": "feudal", "CASTLE_AGE": "castle", "IMPERIAL_AGE": "imperial"}
        landed: dict[str, float] = {}
        for u in self.r.match.uptimes:
            if u.player is self.log.player and u.age.name in names:
                landed.setdefault(names[u.age.name], u.timestamp.total_seconds())
        out = {}
        for age, landing in landed.items():
            clicks = [e.t for e in self.events
                      if e.kind == "research" and AGE_TECHS.get(e.what) == age and e.t <= landing]
            out[age] = (clicks[-1] if clicks else landing - AGE_SECONDS[age], landing)
        return out

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

    def _busy(self) -> list[tuple[float, float]]:
        spans = [(max(click, landing - AGE_SECONDS[age]), landing) for age, (click, landing) in self.ages.items()]
        loom = next((e.t for e in self.events
                     if e.kind == "research" and e.what == "Loom" and set(e.ids) & self.log.tcs), None)
        if loom is not None:
            spans.append((loom, loom + 25))
        return sorted(spans)

    @cached_property
    def spawns(self) -> list[tuple[float, int | None]]:
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
        busy = self._busy()
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

    def rally_at(self, t: float) -> Event | None:
        rally = None
        for e in self.events:
            if e.t > t:
                break
            if e.kind == "rally":
                rally = e
        return rally

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
        changes no job at all."""
        plans: dict = defaultdict(list)
        built: dict = defaultdict(list)
        for v in self.log.start_villagers:
            plans[v].append((0.0, "idle", None, None))
        for k, (t, i) in enumerate(self.spawns):
            rally = self.rally_at(t)
            raw, target = (rally.job, rally.target) if rally else (None, None)
            plans[i if i is not None else f"unseen{k}"].append((t, card_job(raw) or "idle", raw, target))
        for e in self.events:
            if e.t > self.end or e.kind not in ("assign", "build") or not e.job:
                continue
            site = (e.site if e.site and e.site[0] in DROPSITES and e.site[0] != "Farm"
                    and e.t - e.site[1] <= MERGE else None)
            for v in e.ids:
                if v in plans:
                    plans[v].append((e.t, card_job(e.job), e.job, e.target))
                    if site:
                        built[v].append((e.t, card_job(e.job), site))

        out = []
        for v, plan in plans.items():
            plan.sort(key=lambda p: p[0])
            kept = [p for k, p in enumerate(plan)
                    if k + 1 == len(plan) or k == 0 and p[1] == "idle" or plan[k + 1][0] - p[0] >= BRIEF]
            steps: list[tuple] = []
            for step in kept:
                if steps and steps[-1][1] == step[1]:
                    continue
                if len(steps) >= 2 and step[1] == steps[-2][1] and step[0] - steps[-1][0] <= ROUND_TRIP:
                    steps.pop()
                    continue
                steps.append(step)
            previous = None
            for k, (t, job, *_) in enumerate(steps):
                until = steps[k + 1][0] if k + 1 < len(steps) else float("inf")
                sites = {site for when, on, site in built[v] if on == job and t - FIRST_ORDER <= when < until}
                deer = {target or "?" for when, _, raw, target in kept
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

        def attach(t: float, item: dict, part: str) -> None:
            """Onto the row being worked when it happened, never across a phase
            band: a castle dropped on landing is Castle Age, whatever came last."""
            here = [row for row in rows
                    if self.section_of(row["t"]) == self.section_of(t) and not row["research"]]
            if not here:
                here = [_row(t, None, None)]
                rows.append(here[0])
            target = here[0]
            for row in here:
                if row["t"] <= t:
                    target = row
            target[part].append((t, item))

        walled, researched = set(), set()
        for e in self.events:
            if e.t > self.end:
                break
            # A camp no step claimed -- its builder's step was a misclick, or
            # an errand -- still went up, so it goes up on the way like a house.
            if e.kind == "build" and (e.building not in DROPSITES
                                      or e.building != "Farm" and e.site not in placed):
                if e.building.endswith("Wall"):
                    if (self.section_of(e.t), e.building) in walled:
                        continue
                    walled.add((self.section_of(e.t), e.building))
                key = building_icon(e.building)
                attach(e.t, icon(key) if key else text(e.building), "built")
            elif e.kind == "research" and e.what not in AGE_TECHS and e.what not in researched:
                researched.add(e.what)
                key = tech_icon(e.what)
                item = icon(key) if key else text(e.what)
                if e.what in TOWN_CENTRE_TECHS or set(e.ids) & self.log.tcs:
                    # The Town Centre's work for that while, so a step of its
                    # own like an age-up, not a mention on someone else's.
                    tech = _row(e.t, None, None)
                    tech["research"] = True
                    tech["extras"].append((e.t, item))
                    rows.append(tech)
                else:
                    attach(e.t, item, "extras")
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
        # The Town Centre is researching through a "Going" band, so no
        # villager is added there and its rows go unnumbered.
        sections = {label: {"id": _id(), "label": label, "tone": tone, "numbered": tone != "transition",
                            "steps": []}
                    for label, tone in PHASES}
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
            extras = _in_order(row["extras"])
            # A place takes icons and numbers only, so a building nothing can
            # draw is named among the extras instead.
            unnamed = [i for i in moved_via + new_via if i["kind"] != "icon"]
            moved_via = [i for i in moved_via if i["kind"] == "icon"]
            new_via = [i for i in new_via if i["kind"] == "icon"]
            line = lines[self.section_of(row["t"])]
            if row["to"] is None:
                line.append(_unit(row, _step(new_via + [i for i in extras if i["kind"] == "icon"],
                                              extras=unnamed + [i for i in extras if i["kind"] != "icon"])))
                continue
            if row["to"] == "hunt" and row["deer"]:
                herd = len(row["deer"])
                extras = ([count(herd)] if herd > 1 else []) + [icon("gaia-deer")] + extras
            step = _step([count(len(row["new"])), icon(JOB_ICON[row["to"]])] + new_via if row["new"] else [],
                         extras=unnamed + extras)
            if row["from"]:
                step |= {"moveTo": _place([count(len(row["who"])), icon(JOB_ICON[row["to"]])] + moved_via),
                         "from": _place([icon(JOB_ICON[row["from"]])])}
            line.append(_unit(row, step))

        for label, line in lines.items():
            sections[label]["steps"] = [unit["step"] for unit in _paired(line)]

        for age, going in (("feudal", "Going Feudal"), ("castle", "Going Castle")):
            if age in self.ages:
                click, landing = self.ages[age]
                # Counted when the research starts: the villagers queued
                # before the click come out first.
                started = max(click, landing - AGE_SECONDS[age])
                label = f"click {clock(click)} at {self.population_at(started)} vils, up {clock(landing)}"
                sections[going]["steps"].insert(0, _step([icon(AGE_ICON[age])], label=label))

        made: dict[str, list] = defaultdict(list)
        for e in self.events:
            if e.kind == "queue" and e.what != "Villager" and e.t <= self.end and not set(e.ids) & self.log.tcs:
                if e.what not in made[self.section_of(e.t)]:
                    made[self.section_of(e.t)].append(e.what)
        for label, units in made.items():
            drawable = [u for u in units if unit_icon(u)]
            other = [u for u in units if not unit_icon(u)]
            sections[label]["steps"].append(_step([icon(unit_icon(u)) for u in drawable],
                                                  extras=[text(", ".join(other))] if other else []))

        ages = ", ".join(f"{age.title()} {clock(landing)}" for age, (_, landing) in self.ages.items()
                         if age in ("feudal", "castle"))
        return {
            "id": _id(),
            "name": f"{name} {civ} {setting}",
            "title": f"{name} · {civ}",
            "subtitle": f"{setting} · {ages}" if ages else setting,
            "totals": True,
            "rowNumbers": "villagers",
            "sections": [s for s in sections.values() if s["steps"]],
            "updated": 0,
        }
