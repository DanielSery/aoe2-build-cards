"""The replay reader's offline checks: a link names its match, a strategy reads
in order, forward means at the enemy's door, a cancelled building is none, a
card names new villagers once, and a trip forward is no work.

    python tools/check.py

Reading a real game needs the network and a replay Microsoft still keeps, so
that is checked by hand (see README.md). The card editor's own test is
`cards/shot.mjs`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check_a_game_link_names_its_match(fail) -> None:
    """Every link a player pastes into *Analyze game…* finds the match, and a
    profile link is refused rather than read as one.

    A profile id is a number in a URL too, so "the number in the link" would
    fetch a match that does not exist and blame the replay server for it.
    """
    from replays.fetch import GameError, match_id
    for link in ("516330082", " 516330082 ",
                 "https://www.aoe2companion.com/match/516330082",
                 "https://www.aoe2insights.com/match/516330082/",
                 "https://aoe.ms/replay/?gameId=516330082&profileId=2463959",
                 "aoe2de://0/516330082"):
        try:
            if match_id(link) != 516330082:
                fail(f"{link!r} read as match {match_id(link)}")
        except GameError:
            fail(f"{link!r} was refused")
    for link in ("https://www.aoe2companion.com/profile/2463959", "not a link"):
        try:
            fail(f"{link!r} read as match {match_id(link)}")
        except GameError:
            pass


def check_a_strategy_reads_in_order(fail) -> None:
    """The plan line in *Analyze game…*: plans overlapping inside one age are
    a comma, the next one an arrow; a unit is named as the upgrade its line
    had; and militia are a drush only when Man-at-Arms never came."""
    from replays.game import UNIT_LINES
    from replays.strategy import Plan, _label, _sentence
    stages = [500.0, 900.0, 1190.0]

    def age(t: float) -> int:
        return sum(t >= s for s in stages)

    for plans, want in (
            ([Plan("men-at-arms", 540, 600), Plan("archers", 610, 800)], "men-at-arms → archers"),
            ([Plan("unique unit", 900, 1100), Plan("fast imp", 1000, 1190), Plan("hand cannoneers", 1200, 1300)],
             "unique unit, fast imp → hand cannoneers")):
        if _sentence(plans, age) != want:
            fail(f"read {_sentence(plans, age)!r}, wanted {want!r}")

    scouts = UNIT_LINES["Scout Cavalry"]
    upgrades = {"Scout Cavalry": [(800.0, "Light Cavalry"), (1300.0, "Hussar")]}
    for t, want in ((700, "scouts"), (900, "light cavalry"), (1400, "hussars")):
        got = _label(scouts, "Scout Cavalry", t, age(t), upgrades, False)
        if got != want:
            fail(f"a scout queued at {t}s read {got!r}, wanted {want!r}")
    for unit, researched, want in (
            ("Militia", ["Man-at-Arms", "Long Swordsman"], "long swordsmen"),
            ("Militia", ["Man-at-Arms", "Legionary"], "legionaries"),
            ("Archer", ["Crossbowman"], "crossbowmen"),
            ("Archer", ["Crossbowman", "Arbalester"], "arbalesters"),
            ("Knight", ["Cavalier", "Paladin"], "paladins"),
            ("Galley", ["War Galley"], "war galleys")):
        line = UNIT_LINES[unit]
        upgrades = {line["line"]: [(1000.0 + k, name) for k, name in enumerate(researched)]}
        got = _label(line, unit, 1500, age(1500), upgrades, True)
        if got != want:
            fail(f"{unit} after {', '.join(researched)} read {got!r}, wanted {want!r}")
    militia = UNIT_LINES["Militia"]
    for men_at_arms, want in ((True, "men-at-arms"), (False, "drush")):
        got = _label(militia, "Militia", 200, 0, {}, men_at_arms)
        if got != want:
            fail(f"Dark Age militia with Man-at-Arms {men_at_arms} read {got!r}, wanted {want!r}")


def check_forward_is_at_the_enemy(fail) -> None:
    """Towers, castles and a douche count only when built forward: near an
    enemy's starting Town Centre and clearly nearer it than one's own team.

    No cached game has a douche, so this is the only thing that has seen one:
    a stub replay, the starting Town Centre deleted, another one placed."""
    from datetime import timedelta
    from types import SimpleNamespace as Stub
    from replays.game import Node, Placed, Replay
    from replays.strategy import _aggression

    replay = Stub(nodes={1: Node(1, 109, "Town Center", 20, 20, 1), 2: Node(2, 109, "Town Center", 100, 100, 2)})
    delete = Stub(type=Stub(name="DELETE"), payload={"object_ids": [1]}, timestamp=timedelta(seconds=5))

    def read(placed, actions=()) -> set[str]:
        log = Stub(player=Stub(number=1), tcs={1}, placed=placed, actions=list(actions),
                   forward=Replay.forward(replay, {2}))
        plans, _ = _aggression(log, lambda t: 0, 3600.0)
        return {p.label for p in plans}

    for placed, actions, want in (
            ([Placed(60, "Town Center", 85, 85)], [delete], {"douche"}),
            ([Placed(60, "Town Center", 30, 30)], [delete], set()),
            ([Placed(60, "Town Center", 85, 85)], [], set()),
            ([Placed(300, "Watch Tower", 90, 90)], [], {"tower rush"}),
            ([Placed(900, "Castle", 60, 60)], [], set()),
            ([Placed(900, "Castle", 88, 88)], [], {"castle drop"})):
        got = read(placed, actions)
        if got != want:
            fail(f"{[(b.name, b.x, b.y) for b in placed]} with {len(actions)} deletes read {got}, wanted {want}")


def check_a_cancelled_building_is_not_built(fail) -> None:
    """A foundation deleted before one villager could have finished it is
    left out; one whose deleted id cannot be pinned to it stands."""
    from datetime import timedelta
    from types import SimpleNamespace as Stub
    from replays.game import PlayerLog

    player = Stub(number=1)

    def act(kind: str, t: float, **payload):
        return Stub(type=Stub(name=kind), player=player, payload=payload, timestamp=timedelta(seconds=t),
                    position=Stub(x=10.0, y=10.0) if kind == "BUILD" else None)

    bounds = {201: 61.0, 202: 300.0}
    replay = Stub(match=Stub(players=[player], actions=[
        act("BUILD", 60, building="Barracks", building_id=12, object_ids=[]),
        act("DELETE", 62, object_ids=[201]),
        act("BUILD", 100, building="House", building_id=70, object_ids=[]),
        act("DELETE", 400, object_ids=[202])]),
        nodes={}, last_starting_id=100, commanded=set(), created_by=bounds.__getitem__,
        forward=lambda enemies: lambda x, y: False)
    replay.match.actions.sort(key=lambda a: a.timestamp)
    standing = [b.name for b in PlayerLog(replay, 1).placed]
    if standing != ["House"]:
        fail(f"the buildings standing were {standing}, wanted only the House")


def check_a_card_names_new_villagers_once(fail) -> None:
    """New villagers to the same place in a run are one row, across a move
    elsewhere, and none is new in a Going band: the one first sent there is
    written before the click."""
    from types import SimpleNamespace as Stub
    from replays.card import JOB_ICON, Opening, building_icon

    opening = object.__new__(Opening)
    opening.ages = {"feudal": (300.0, 430.0)}
    opening.events, opening.end = [], 600.0
    opening.log = Stub(tcs=set(), start_villagers=[])
    opening.__dict__["spawns"] = []
    opening.transitions = lambda: [
        (5.0, 1, None, "sheep", set(), set()),
        (20.0, 2, None, "wood", {("Lumber Camp", 20.0)}, set()),
        (30.0, 1, "sheep", "hunt", set(), set()),
        (50.0, 3, None, "wood", set(), set()),
        (60.0, 4, None, "wood", set(), set()),
        (310.0, 5, None, "gold", set(), set()),
        (320.0, 2, "wood", "gold", set(), set())]
    card = {s["label"]: s["steps"] for s in opening.card("x", "", "")["sections"]}

    def new(step):
        to = step["to"]["items"]
        if to and to[0]["kind"] == "count":
            return to[0]["value"], to[1]["icon"], [i["icon"] for i in to[2:]]

    dark = [new(step) for step in card["Dark Age"] if new(step)]
    wanted = [("1", JOB_ICON["sheep"], []), ("3", JOB_ICON["wood"], [building_icon("Lumber Camp")]),
              ("1", JOB_ICON["gold"], [])]
    if dark != wanted:
        fail(f"the Dark Age's new villagers were {dark}, wanted {wanted}")
    going = [new(step) for step in card["Going Feudal"] if new(step)]
    if going:
        fail(f"villagers were new in the Going band: {going}")


def check_a_trip_forward_is_no_work(fail) -> None:
    """Villagers who walk to the enemy and put up a tower there are forward
    until they are given work again, and the tower goes with them; a walk
    forward that builds nothing is no trip at all."""
    from types import SimpleNamespace as Stub
    from replays.card import Opening, building_icon
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.ages, opening.end, opening.r = {}, 900.0, Stub(nodes={})
    opening.log = Stub(tcs=set(), start_villagers=[1, 2])
    opening.__dict__["spawns"] = []
    opening.events = [
        Event(10.0, "assign", [1, 2], job="wood"),
        Event(100.0, "forward", [1, 2], job="forward"),
        Event(130.0, "build", [1, 2], job="forward", building="Watch Tower", site=("Watch Tower", 130.0)),
        Event(300.0, "assign", [1, 2], job="gold"),
        Event(400.0, "forward", [2], job="forward"),
        Event(500.0, "assign", [2], job="wood")]
    steps = [(t, v, src, dst) for t, v, src, dst, *_ in opening.transitions()]
    wanted = [(10.0, 1, "idle", "wood"), (10.0, 2, "idle", "wood"), (100.0, 1, "wood", "forward"),
              (100.0, 2, "wood", "forward"), (300.0, 1, "forward", "gold"), (300.0, 2, "forward", "gold"),
              (500.0, 2, "gold", "wood")]
    if steps != wanted:
        fail(f"the steps were {steps}, wanted {wanted}")

    def read(place):
        return place and ([i.get("icon") or i.get("value") for i in place["items"]], place["label"])

    rows = [(read(step["moveTo"]), read(step["from"])) for step in opening.card("x", "", "")["sections"][0]["steps"]
            if step["from"]]
    trip = ((["2", "command-forward", building_icon("Watch Tower")], ""), (["resource-wood"], ""))
    back = ((["2", "resource-gold"], ""), (["command-forward"], ""))
    if rows[:2] != [trip, back]:
        fail(f"the moves read {rows}, wanted {[trip, back]} first")


def check_a_short_task_is_not_on_the_card(fail) -> None:
    """A villager put on one work and sent elsewhere inside half a minute is
    drawn going straight there -- unless it was gold, stone or a building
    site, which a build order asks for in short stints."""
    from types import SimpleNamespace as Stub
    from replays.card import Opening
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.ages, opening.end, opening.r = {}, 900.0, Stub(nodes={})
    opening.log = Stub(tcs=set(), start_villagers=[1, 2, 3, 4])
    opening.__dict__["spawns"] = []
    opening.events = [
        Event(10.0, "assign", [1], job="sheep"),
        Event(35.0, "assign", [1], job="boar"),
        Event(10.0, "assign", [2, 3, 4], job="wood"),
        Event(100.0, "assign", [2], job="stone"),
        Event(120.0, "assign", [2], job="wood"),
        Event(100.0, "build", [3], job="gold", building="Mining Camp", site=("Mining Camp", 100.0)),
        Event(118.0, "assign", [3], job="wood"),
        Event(100.0, "assign", [4], job="berries"),
        Event(120.0, "assign", [4], job="sheep")]
    opening.events.sort(key=lambda e: e.t)
    steps = [(t, v, src, dst) for t, v, src, dst, *_ in opening.transitions()]
    wanted = [(10.0, 2, "idle", "wood"), (10.0, 3, "idle", "wood"), (10.0, 4, "idle", "wood"),
              (35.0, 1, "idle", "hunt"), (100.0, 2, "wood", "stone"), (100.0, 3, "wood", "gold"),
              (118.0, 3, "gold", "wood"), (120.0, 2, "stone", "wood"), (120.0, 4, "wood", "sheep")]
    if steps != wanted:
        fail(f"the steps were {steps}, wanted {wanted}")


def check_loom_waits_for_the_villagers_ahead(fail) -> None:
    """Loom clicked behind villagers is done when the queue reaches it. With
    Feudal clicked next while the Town Centre was still busy, that is just in
    time for whatever was queued in between -- but only if each of those
    waited for its turn, or the Town Centre may have stood idle before it."""
    from types import SimpleNamespace as Stub
    from replays.card import Opening
    from replays.game import Event, town_centre_speed

    def done(between):
        opening = object.__new__(Opening)
        opening.ages, opening.clicked = {"feudal": (375.0, 505.0)}, {"feudal": 370.0}
        opening.log, opening.speed = Stub(tcs={100}), town_centre_speed(None)
        loom = Event(280.0, "research", [100], what="Loom", takes=25.0)
        opening.events = sorted([loom, Event(370.0, "research", [100], what="Feudal Age", takes=130.0)]
                                + [Event(t, "queue", [100], what="Villager", takes=25.0) for t in between],
                                key=lambda e: e.t)
        return round(opening._tc_done(loom), 3)

    for between, wanted, why in (([], 374.999, "nothing queued after it"),
                                 ([300.0], 350.0, "one villager queued after it"),
                                 ([349.5], 305.0, "a villager clicked as its turn came")):
        if done(between) != wanted:
            fail(f"with {why}, Loom was done at {done(between)}, wanted {wanted}")

    # The Town Centre idle at the Feudal click leaves nothing to count back
    # from; the villagers trained before it say how many were ahead of Loom.
    def ahead(trained):
        opening = object.__new__(Opening)
        opening.ages, opening.clicked = {"feudal": (375.0, 505.0)}, {"feudal": 375.0}
        opening.log, opening.speed = Stub(tcs={100}), town_centre_speed(None)
        loom = Event(210.0, "research", [100], what="Loom", takes=25.0)
        opening.events = sorted([loom, Event(375.0, "research", [100], what="Feudal Age", takes=130.0)]
                                + [Event(200.0, "queue", [100], what="Villager", takes=25.0) for _ in range(4)],
                                key=lambda e: e.t)
        opening.__dict__["spawns"] = [(t, None) for t in trained]
        return round(opening._tc_done(loom), 3)

    for trained, wanted, why in (([225.0, 250.0, 275.0, 300.0], 325.0, "four villagers queued ahead"),
                                 ([225.0, 250.0], 275.0, "two of the four clicks paid for")):
        if ahead(trained) != wanted:
            fail(f"with {why} and the Town Centre idle at the click, Loom was done at {ahead(trained)}, "
                 f"wanted {wanted}")


def check_a_move_joining_new_villagers_shares_their_place(fail) -> None:
    """Villagers moved to where new ones go are written with them, the number
    on the source saying how many moved: "3 hunt <- 2 sheep". A move to
    somewhere else at the same time takes the second column of that row."""
    from types import SimpleNamespace as Stub
    from replays.card import JOB_ICON, Opening

    opening = object.__new__(Opening)
    opening.ages, opening.events, opening.end = {}, [], 600.0
    opening.log = Stub(tcs=set(), start_villagers=[])
    opening.__dict__["spawns"] = []
    opening.transitions = lambda: [
        (5.0, 1, None, "sheep", set(), set()),
        (6.0, 2, None, "sheep", set(), set()),
        (7.0, 3, None, "sheep", set(), set()),
        (8.0, 6, None, "berries", set(), set()),
        (100.0, 1, "sheep", "hunt", set(), set()),
        (100.0, 2, "sheep", "hunt", set(), set()),
        (101.0, 4, None, "hunt", set(), set()),
        (110.0, 6, "berries", "wood", set(), set())]

    def read(place):
        return place and [i.get("icon") or i.get("value") for i in place["items"]]

    rows = [tuple(read(step[part]) for part in ("to", "toFrom", "moveTo", "from"))
            for step in opening.card("x", "", "")["sections"][0]["steps"]]
    wanted = [(["3", JOB_ICON["sheep"]], None, None, None),
              (["1", JOB_ICON["berries"]], None, None, None),
              (["3", JOB_ICON["hunt"]], ["2", JOB_ICON["sheep"]], ["1", JOB_ICON["wood"]], [JOB_ICON["berries"]])]
    if rows != wanted:
        fail(f"the rows were {rows}, wanted {wanted}")


def check_an_empty_selection_is_the_last_units_commanded(fail) -> None:
    """A command with no unit list goes to the units this player last gave
    any unit's command to -- the scout just moved, not the villager last
    right-clicked -- and never to a building the player last queued at."""
    from types import SimpleNamespace as Stub
    from replays.game import Replay

    def command(kind, ids):
        return Stub(player=Stub(number=1), type=Stub(name=kind), payload={"object_ids": list(ids)})

    actions = [command("ORDER", [10]), command("MOVE", [99]), command("ORDER", []),
               command("DE_QUEUE", [500]), command("MOVE", [])]
    Replay._resolve_selections(Stub(match=Stub(actions=actions)))
    got = [a.payload["object_ids"] for a in actions[2::2]]
    if got != [[99], [99]]:
        fail(f"the empty selections were read as {got}, wanted the scout both times")


def check_a_mill_goes_with_the_berries(fail) -> None:
    """A mill no step claimed -- put up a while after its builder reached
    the berries -- is drawn with the berries, not on whatever row came last."""
    from types import SimpleNamespace as Stub
    from replays.card import JOB_ICON, Opening, building_icon
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.ages, opening.end = {}, 600.0
    opening.events = [Event(120.0, "build", [1], job="berries", building="Mill", site=("Mill", 120.0))]
    opening.log = Stub(tcs=set(), start_villagers=[])
    opening.__dict__["spawns"] = []
    opening.transitions = lambda: [(5.0, 1, None, "berries", set(), set()), (100.0, 2, None, "hunt", set(), set())]
    rows = [[i.get("icon") or i.get("value") for i in step["to"]["items"]]
            for step in opening.card("x", "", "")["sections"][0]["steps"]]
    wanted = [["1", JOB_ICON["berries"], building_icon("Mill")], ["1", JOB_ICON["hunt"]]]
    if rows != wanted:
        fail(f"the rows were {rows}, wanted {wanted}")


def check_a_gather_point_moved_for_the_villager(fail) -> None:
    """A gather point moved a few seconds before a villager's estimated
    spawn was moved because that villager had come out, so it went where the
    gather point was before -- unless one Town Centre could not have trained
    it by the move. Moved well before, it is where the villager went."""
    from types import SimpleNamespace as Stub
    from replays.card import Opening
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.events = [Event(100.0, "rally", job="stone"), Event(147.0, "rally", job="gold"),
                      Event(148.0, "rally", job="gold")]
    got = [opening.rally_at(t, previous).job for t, previous in ((150.0, 120.0), (160.0, 120.0), (150.0, 140.0))]
    if got != ["stone", "gold", "gold"]:
        fail(f"the villagers went to {got}, wanted stone, gold, gold")


def check_villagers_let_out_go_to_the_gather_point(fail) -> None:
    """Villagers garrisoned in the Town Centre and let out again walk to its
    gather point: in, gather point on the stone, out, is three to the stone.
    Garrisoning carries its ids a byte out of place, one given another
    command since is out already, and one no other command ever names is
    let out like the rest."""
    from datetime import timedelta
    from types import SimpleNamespace as Stub
    from replays.game import PlayerLog

    def command(t, kind, ids, **rest):
        return Stub(timestamp=timedelta(seconds=t), type=Stub(name=kind), position=None,
                    payload={"object_ids": ids, **rest})

    log = object.__new__(PlayerLog)
    log.r = Stub(nodes={}, last_starting_id=100, commanded={201, 202, 203, 204})
    log.tcs, log.start_villagers, log.soldiers, log.sailors, log.cancelled = {50}, set(), set(), set(), set()
    log.forward = lambda x, y: False
    log.actions = [command(10.0, "SPECIAL", [201 << 8, 202 << 8, 203 << 8, 204 << 8, 205 << 8], target_id=50),
                   command(11.0, "MOVE", [204]),
                   command(12.0, "GATHER_POINT", [50], target_id=7, target_type=102),
                   command(13.0, "UNGARRISON", [(50 << 8) + 1])]
    out = [(e.t, e.ids, e.job) for e in log.events() if e.kind == "assign"]
    if out != [(13.0, [201, 202, 203, 205], "stone")]:
        fail(f"letting them out read as {out}, wanted four to the stone at 13s")


def check_neighbouring_rows_name_a_work_once(fail) -> None:
    """"3 sheep" beside "1 farm <- sheep", then "1 sheep", is one row, "4
    sheep" beside the move; two rows that each have a move stay two."""
    from replays.card import _merged, _step, _work

    def row(new, move=None):
        step = _step(_work("sheep", new)["items"])
        return step | {"moveTo": _work("farm", 1), "from": _work("sheep")} if move else step

    def read(steps):
        return [(s["to"]["items"][0]["value"], bool(s["moveTo"])) for s in steps]

    if read(_merged([row(3, True), row(1)])) != [("4", True)]:
        fail(f"the rows read {read(_merged([row(3, True), row(1)]))}, wanted one: 4 sheep beside the move")
    if read(_merged([row(3, True), row(1, True)])) != [("3", True), ("1", True)]:
        fail("two rows with a move each were merged")

def check_sheep_between_hunts_are_no_move(fail) -> None:
    """Sheep eaten between two hunts for under a minute and a half were what
    the crew ate while the next animal came in, so the card keeps it on the
    hunt; for longer, it was on the sheep."""
    from types import SimpleNamespace as Stub
    from replays.card import Opening
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.ages, opening.end, opening.r = {}, 900.0, Stub(nodes={})
    opening.log = Stub(tcs=set(), start_villagers=[1, 2])
    opening.__dict__["spawns"] = []
    opening.events = sorted([
        Event(10.0, "assign", [1, 2], job="sheep"),
        Event(100.0, "assign", [1, 2], job="boar"),
        Event(200.0, "assign", [1, 2], job="sheep"),
        Event(250.0, "assign", [1], job="deer"),
        Event(320.0, "assign", [2], job="boar"),
        Event(400.0, "assign", [1, 2], job="sheep")], key=lambda e: e.t)
    steps = [(t, v, src, dst) for t, v, src, dst, *_ in opening.transitions()]
    wanted = [(10.0, 1, "idle", "sheep"), (10.0, 2, "idle", "sheep"), (100.0, 1, "sheep", "hunt"),
              (100.0, 2, "sheep", "hunt"), (200.0, 2, "hunt", "sheep"), (320.0, 2, "sheep", "hunt"),
              (400.0, 1, "hunt", "sheep"), (400.0, 2, "hunt", "sheep")]
    if steps != wanted:
        fail(f"the steps were {steps}, wanted {wanted}")


def check_a_building_goes_with_its_builders(fail) -> None:
    """A house or a barracks no step claimed is drawn on the row of its
    builders' work, not on whatever row came last; with no such row in the
    phase it is only mentioned."""
    from types import SimpleNamespace as Stub
    from replays.card import JOB_ICON, Opening, building_icon
    from replays.game import Event

    opening = object.__new__(Opening)
    opening.ages, opening.end = {"feudal": (200.0, 330.0)}, 600.0
    opening.events = [Event(150.0, "build", [2], building="Barracks", site=("Barracks", 150.0)),
                      Event(160.0, "build", [1], building="House", site=("House", 160.0)),
                      Event(250.0, "build", [2], building="House", site=("House", 250.0))]
    opening.log = Stub(tcs=set(), start_villagers=[])
    opening.__dict__["spawns"] = []
    opening.transitions = lambda: [(5.0, 1, None, "sheep", set(), set()), (20.0, 2, None, "wood", set(), set()),
                                   (100.0, 3, None, "hunt", set(), set()), (240.0, 3, "hunt", "gold", set(), set())]
    card = opening.card("x", "", "")
    dark = [[i.get("icon") or i.get("value") for i in step["to"]["items"]] for step in card["sections"][0]["steps"]]
    going = card["sections"][1]["steps"][-1]
    wanted = [["1", JOB_ICON["sheep"], building_icon("House")], ["1", JOB_ICON["wood"], building_icon("Barracks")],
              ["1", JOB_ICON["hunt"]]]
    if dark != wanted:
        fail(f"the Dark Age rows were {dark}, wanted {wanted}")
    if [i.get("icon") for i in going["extras"]] != [building_icon("House")] or len(going["moveTo"]["items"]) != 2:
        fail(f"a house with no row of its builders' was {going}, wanted it only mentioned")

def check_shore_fish_is_its_own_work(fail) -> None:
    """A villager on the shore fish is on the fish, a work of its own. A unit
    that only ever fished, or put up a fish trap, is a fishing ship and no
    villager at all."""
    from datetime import timedelta
    from types import SimpleNamespace as Stub
    from replays.game import SHORE_FISH, Node, PlayerLog, job_of_type

    def command(t, kind, ids, **rest):
        return Stub(timestamp=timedelta(seconds=t), type=Stub(name=kind), position=None,
                    payload={"object_ids": ids, **rest})

    log = object.__new__(PlayerLog)
    log.r = Stub(last_starting_id=100, nodes={7: Node(7, SHORE_FISH, "Shore Fish", 0, 0, 0),
                                              8: Node(8, 53, "Fish (Perch)", 0, 0, 0),
                                              9: Node(9, 1248, "Tree (Oak Autumn)", 0, 0, 0)})
    log.start_villagers, log.soldiers = [1], set()
    log.actions = [command(10.0, "ORDER", [1, 201], target_id=7),
                   command(10.0, "ORDER", [202], target_id=8),
                   command(10.0, "BUILD", [203], building="Fish Trap"),
                   command(10.0, "ORDER", [204], target_id=7),
                   command(40.0, "ORDER", [204], target_id=9)]
    log.sailors = log._sailors()
    if job_of_type(SHORE_FISH) != "fish":
        fail(f"the shore fish read as {job_of_type(SHORE_FISH)}, wanted fish")
    if log.villagers([1, 201, 202, 203, 204]) != [1, 204]:
        fail(f"the villagers were {log.villagers([1, 201, 202, 203, 204])}, wanted the one who started "
             "a villager and the one who also cut wood")

def check_a_persian_town_centre_trains_faster(fail) -> None:
    """The Persians' Town Centre works faster with every age, so their
    villagers come out closer together; nobody else's Town Centre does."""
    from replays.game import town_centre_speed

    persian, magyar = town_centre_speed("Persians"), town_centre_speed("Magyars")
    ages = ("dark", "feudal", "castle", "imperial")
    if not (1 < persian["dark"] < persian["feudal"] < persian["castle"] < persian["imperial"]):
        fail(f"the Persian Town Centre's speed was {persian}, wanted faster and faster from the Dark Age")
    if any(magyar[age] != 1 for age in ages):
        fail(f"the Magyar Town Centre's speed was {magyar}, wanted the game data's own")





CHECKS = (check_a_game_link_names_its_match, check_a_strategy_reads_in_order,
          check_forward_is_at_the_enemy, check_a_cancelled_building_is_not_built,
          check_a_card_names_new_villagers_once,
          check_a_trip_forward_is_no_work,
          check_a_short_task_is_not_on_the_card,
          check_loom_waits_for_the_villagers_ahead,
          check_a_move_joining_new_villagers_shares_their_place,
          check_an_empty_selection_is_the_last_units_commanded,
          check_a_mill_goes_with_the_berries,
          check_a_gather_point_moved_for_the_villager,
          check_villagers_let_out_go_to_the_gather_point,
          check_neighbouring_rows_name_a_work_once,
          check_sheep_between_hunts_are_no_move,
          check_a_building_goes_with_its_builders,
          check_shore_fish_is_its_own_work,
          check_a_persian_town_centre_trains_faster)


def main() -> int:
    failed = 0
    for check in CHECKS:
        problems: list[str] = []
        check(problems.append)
        print(f"{'FAIL' if problems else 'ok  '} {check.__name__}")
        for problem in problems:
            print(f"     {problem}")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
