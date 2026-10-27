"""
Finding a game: a player by name or id, and their recent games with what the
finder filters on -- format, seat, civ and map.

The filtering happens in the browser over one fetched list, so changing a
filter costs nothing; only the last `DAYS` are fetched, because older games
have no replay left to read.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .fetch import GameError, download

SEARCH_URL = "https://data.aoe2companion.com/api/profiles?search={query}"
PROFILE_URL = "https://data.aoe2companion.com/api/profiles/{profile_id}"
MATCHES_URL = "https://data.aoe2companion.com/api/matches?profile_ids={profile_id}&page={page}&per_page={per_page}"
PER_PAGE = 300
PAGES = 3
DAYS = 120
FRESH_SECONDS = 600

RANKED = {"rm_1v1", "rm_team"}
# A nomad start has no Town Centre, so the seat says nothing about where anyone
# settles. MegaRandom rolls its type per game and keeps its seats.
NO_SEATS = {"Nomad", "Land Nomad"}


def _json(url: str):
    try:
        return json.loads(download(url))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise GameError(f"aoe2companion answered {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise GameError(f"Could not reach aoe2companion: {exc.reason}") from exc


def _profile(raw: dict) -> dict:
    return {"profileId": raw["profileId"], "name": raw.get("name") or str(raw["profileId"]),
            "clan": raw.get("clan") or "", "country": raw.get("country") or "",
            "games": int(raw.get("games") or 0), "verified": bool(raw.get("verified"))}


def find_players(query: str) -> list[dict]:
    """By name, or by id: a bare number or a link with /profile/<id> in it."""
    query = query.strip()
    if not query:
        raise GameError("Type a player name or profile id.")
    named = re.search(r"/profile/(\d+)", query)
    if named or query.isdigit():
        raw = _json(PROFILE_URL.format(profile_id=named.group(1) if named else query))
        if raw is None or "profileId" not in raw:
            raise GameError(f"aoe2companion has no profile {query}.")
        return [_profile(raw)]
    raw = _json(SEARCH_URL.format(query=quote(query))) or {}
    found = [_profile(p) for p in raw.get("profiles", [])]
    if not found:
        raise GameError(f"No player called {query!r} on aoe2companion.")
    return sorted(found, key=lambda p: (not p["verified"], -p["games"]))


def seat(match: dict, me: int) -> str | None:
    """Flank or pocket, or None where the game cannot say. The colour is the
    seat in ranked and the slot in a lobby, ordered round the team's arc; the
    two ends border an opponent."""
    teams = match.get("teams") or []
    if not match.get("teamPositions") or not match.get("teamTogether") or len(teams) != 2:
        return None
    if match.get("mapName") in NO_SEATS:
        return None
    mine = next((t["players"] for t in teams if any(p.get("profileId") == me for p in t["players"])), None)
    if not mine or len(mine) < 3:
        return None
    key = "color" if match.get("leaderboardId") in RANKED else "slot"
    ranks = [p.get(key) for p in mine]
    if None in ranks or len(set(ranks)) != len(ranks):
        return None
    order = sorted(mine, key=lambda p: p[key])
    i = next(i for i, p in enumerate(order) if p.get("profileId") == me)
    return "flank" if i in (0, len(order) - 1) else "pocket"


def shape(match: dict) -> str:
    sizes = [len(t.get("players", [])) for t in match.get("teams") or []]
    if len(sizes) > 2:
        return "FFA"
    return "v".join(map(str, sizes)) if sizes else "?"


def _summary(match: dict, me: int) -> dict | None:
    teams = match.get("teams") or []
    mine = next((t for t in teams if any(p.get("profileId") == me for p in t["players"])), None)
    if mine is None:
        return None
    player = next(p for p in mine["players"] if p.get("profileId") == me)
    return {
        "matchId": match["matchId"],
        "started": match.get("started"),
        "map": match.get("mapName") or "Unknown map",
        "leaderboard": match.get("leaderboardName") or match.get("leaderboardId") or "",
        "format": shape(match),
        "civ": player.get("civName") or "",
        "seat": seat(match, me),
        "won": player.get("won"),
        "rating": player.get("rating"),
        "allies": [p.get("name") for p in mine["players"] if p.get("profileId") != me],
        "opponents": [p.get("name") for t in teams if t is not mine for p in t["players"]],
    }


_recent: dict[int, tuple[float, list]] = {}
_played: dict[int, dict] = {}


def played(match: int) -> dict | None:
    """A match some listed history held, so asking about one of them costs
    aoe2companion no second request: it is the same record `match_record`
    would fetch."""
    return _played.get(match)


def recent_games(profile_id: int) -> list[dict]:
    cached = _recent.get(profile_id)
    if cached and time.monotonic() - cached[0] < FRESH_SECONDS:
        return cached[1]
    since = datetime.now(timezone.utc) - timedelta(days=DAYS)

    def fresh(match: dict) -> bool:
        started = match.get("started")
        return not started or datetime.fromisoformat(started.replace("Z", "+00:00")) >= since

    games: list[dict] = []
    for page in range(1, PAGES + 1):
        matches = (_json(MATCHES_URL.format(profile_id=profile_id, page=page, per_page=PER_PAGE))
                   or {}).get("matches", [])
        kept = [m for m in matches if fresh(m)]
        _played.update((m["matchId"], m) for m in kept)
        games += [s for s in (_summary(m, profile_id) for m in kept) if s]
        if len(kept) < len(matches) or len(matches) < PER_PAGE:
            break
    _recent[profile_id] = (time.monotonic(), games)
    return games
