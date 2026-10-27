"""
The cards app, and the one thing it cannot do in a browser: read a recorded
game.

    python -m uvicorn replays.server:app --port 8030

Serves `cards/dist` at / (build it first: `cd cards; npm run build`) and the
replay reader under /api, so the app's *Analyze game…* finds it on its own
origin. The app is still a static site without this; only that dialog needs it.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import game as game_rules, strategy as strategy_rules
from .card import Opening, clock
from .fetch import CACHE, GameError, keep_local, local_file, match_id, match_record, replay_file
from .game import Replay
from .history import find_players, played, recent_games
from .mgzfix import parse
from .strategy import strategy

CARDS_DIST = Path(__file__).resolve().parents[1] / "cards" / "dist"
KEPT = 6
PLANS = CACHE / "strategies.json"
# A saved plan is only as good as the rules that wrote it, so they sign it.
RULES = hashlib.sha1(b"".join(Path(m.__file__).read_bytes() for m in (game_rules, strategy_rules))
                     + Path(strategy_rules.__file__).with_name("units.json").read_bytes()).hexdigest()[:12]

app = FastAPI(title="AoE2 replay reader")


# A file's players have only the replay's colour names.
COLOURS = {"Blue": "#3f6fff", "Red": "#ff3030", "Green": "#30c030", "Yellow": "#ffe030",
           "Teal": "#30e0e0", "Aqua": "#30e0e0", "Cyan": "#30e0e0", "Purple": "#e050c0",
           "Grey": "#909090", "Gray": "#909090", "Orange": "#ff9a30"}


@dataclass
class Game:
    match: str  # a match id, or `local-…` for a file
    record: dict
    replay: Replay

    def profile(self, player) -> dict:
        """The record's entry for a player. A file's record names players by
        number too, because a game against the AI repeats a profile id."""
        return next((p for team in self.record.get("teams", []) for p in team.get("players", [])
                     if p.get("profileId") == player.profile_id
                     and p.get("number", player.number) == player.number), {})

    @property
    def setting(self) -> str:
        sizes = [len(team.get("players", [])) for team in self.record.get("teams", [])]
        shape = "v".join(map(str, sizes)) if len(sizes) > 1 else ""
        return " ".join(part for part in (self.map_name, shape) if part)

    @property
    def map_name(self) -> str:
        return self.record.get("mapName") or self.replay.match.map.name or "Unknown map"


_games: OrderedDict[str, Game] = OrderedDict()
_lock = threading.Lock()


def _read(what: str, path: Path) -> Replay:
    try:
        return Replay(parse(path))
    except Exception as exc:
        raise GameError(f"The replay of {what} could not be read: {exc}") from exc


def _file_record(replay: Replay) -> dict:
    """What aoe2companion would have said about a game, from the replay alone."""
    teams = replay.match.teams or [[p] for p in replay.match.players]
    return {"mapName": replay.match.map.name, "teams": [
        {"players": [{"number": p.number, "profileId": p.profile_id, "name": p.name,
                      "civName": p.civilization, "team": k, "won": p.winner,
                      "colorHex": COLOURS.get(p.color)} for p in team]}
        for k, team in enumerate(teams, 1)]}


def _game(key: str) -> Game:
    with _lock:
        if key in _games:
            _games.move_to_end(key)
            return _games[key]
        if key.startswith("local-"):
            replay = _read("this file", local_file(key))
            record = _file_record(replay)
        elif key.isdigit():
            record = match_record(int(key))
            replay = _read(f"match {key}", replay_file(int(key), record))
        else:
            raise GameError(f"{key!r} names no game.")
        _games[key] = Game(key, record, replay)
        while len(_games) > KEPT:
            _games.popitem(last=False)
        return _games[key]


def _enemies(game: Game, number: int) -> set[int]:
    """The other side's player numbers; everyone else, where the record has no teams."""
    team = {p.number: game.profile(p).get("team") for p in game.replay.match.players}
    return {n for n, t in team.items() if n != number and (team[number] is None or t != team[number])}


_plans: dict[str, str] | None = None
_plans_lock = threading.Lock()


def _saved_plans() -> dict[str, str]:
    global _plans
    if _plans is None:
        try:
            saved = json.loads(PLANS.read_text(encoding="utf-8"))
            _plans = saved["plans"] if saved.get("rules") == RULES else {}
        except (OSError, ValueError, KeyError):
            _plans = {}
    return _plans


@app.exception_handler(GameError)
def _explain(_request, exc: GameError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/games")
def look_up(link: str) -> dict:
    return _describe(_game(str(match_id(link))))


@app.post("/api/games/file")
async def open_file(request: Request) -> dict:
    """A replay file, sent as the request body: the .aoe2record a game saves,
    or the zip aoe.ms serves."""
    data = await request.body()

    def read() -> dict:
        key = keep_local(data)
        try:
            return _describe(_game(key))
        except GameError:
            local_file(key).unlink(missing_ok=True)
            raise

    return await run_in_threadpool(read)


def _describe(game: Game) -> dict:
    names = {"FEUDAL_AGE": "feudal", "CASTLE_AGE": "castle"}
    players = []
    for player in game.replay.match.players:
        profile = game.profile(player)
        enemies = _enemies(game, player.number)
        ages = {names[u.age.name]: clock(u.timestamp.total_seconds()) for u in game.replay.match.uptimes
                if u.player is player and u.age.name in names}
        players.append({
            "number": player.number,
            "profileId": player.profile_id,
            "name": profile.get("name") or player.name,
            "civ": profile.get("civName") or player.civilization or "Unknown civ",
            "team": profile.get("team") or 0,
            "won": profile.get("won"),
            "color": profile.get("colorHex") or "#888888",
            "feudal": ages.get("feudal"),
            "castle": ages.get("castle"),
            "strategy": strategy(game.replay, player.number, enemies),
        })
    players.sort(key=lambda p: (p["team"], p["number"]))
    return {
        "matchId": game.match,
        "map": game.map_name,
        "setting": game.setting,
        "started": game.record.get("started"),
        "duration": clock(game.replay.match.duration.total_seconds()),
        "players": players,
    }


@app.get("/api/games/{match}/strategy/{profile_id}")
def plan_of(match: int, profile_id: int) -> dict:
    """One player's plan in one game, for the finder's list. Kept on disk, and
    read without joining the games kept in memory: the finder asks about many
    games, and must not push out the one being turned into a card."""
    key = f"{match}:{profile_id}"
    with _plans_lock:
        known = _saved_plans().get(key)
    if known is not None:
        return {"strategy": known}
    with _lock:
        kept = _games.get(str(match))
    if kept is None:
        record = played(match) or match_record(match)
        kept = Game(str(match), record, _read(f"match {match}", replay_file(match, record)))
    player = next((p for p in kept.replay.match.players if p.profile_id == profile_id), None)
    if player is None:
        raise GameError(f"Profile {profile_id} did not play match {match}.")
    plan = strategy(kept.replay, player.number, _enemies(kept, player.number))
    with _plans_lock:
        _saved_plans()[key] = plan
        PLANS.parent.mkdir(parents=True, exist_ok=True)
        PLANS.write_text(json.dumps({"rules": RULES, "plans": _plans}), encoding="utf-8")
    return {"strategy": plan}


@app.get("/api/players")
def players(search: str) -> list[dict]:
    return find_players(search)


@app.get("/api/players/{profile_id}/games")
def games_of(profile_id: int) -> list[dict]:
    return recent_games(profile_id)


@app.get("/api/games/{match}/cards/{number}")
def card(match: str, number: int) -> dict:
    game = _game(match)
    player = next((p for p in game.replay.match.players if p.number == number), None)
    if player is None:
        raise GameError(f"Match {match} has no player {number}.")
    profile = game.profile(player)
    return Opening(game.replay, number).card(profile.get("name") or player.name,
                                             profile.get("civName") or player.civilization or "Unknown civ",
                                             game.setting)


if CARDS_DIST.exists():
    app.mount("/", StaticFiles(directory=CARDS_DIST, html=True), name="cards")
else:
    @app.get("/")
    def _unbuilt() -> PlainTextResponse:
        return PlainTextResponse("The cards app is not built yet: run `npm run build` in cards/, then reload.")
