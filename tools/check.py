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
    trip = ((["2", building_icon("Watch Tower")], "forward"), (["resource-wood"], ""))
    back = ((["2", "resource-gold"], ""), ([], "forward"))
    if rows[:2] != [trip, back]:
        fail(f"the moves read {rows}, wanted {[trip, back]} first")


CHECKS = (check_a_game_link_names_its_match, check_a_strategy_reads_in_order,
          check_forward_is_at_the_enemy, check_a_cancelled_building_is_not_built,
          check_a_card_names_new_villagers_once,
          check_a_trip_forward_is_no_work)


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
