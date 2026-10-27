"""
Where a game comes from: a link, aoe2companion's record of the match, and the
replay Microsoft keeps of it -- or a replay file someone opened from their own
disk.

Neither source is a documented API. Microsoft's replay endpoint wants the id of
any one player in the game besides the match id, which is why the match record
is fetched first, and it keeps replays for months rather than years.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CACHE = Path(__file__).resolve().parents[1] / ".data" / "replays"
MATCH_URL = "https://data.aoe2companion.com/api/matches/{match_id}"
REPLAY_URL = "https://aoe.ms/replay/?gameId={match_id}&profileId={profile_id}"
AGENT = "aoe2-build-cards (local replay reader)"
LARGEST_REPLAY = 64 * 1024 * 1024
LOCAL = CACHE / "local"
LOCAL_KEY = re.compile(r"local-[0-9a-f]{16}")


class GameError(Exception):
    """Something the person who pasted the link can act on."""


def match_id(link: str) -> int:
    """The match a link names. Profile ids run to eight digits and match ids
    are nine and up, so a long number on its own is taken as the match."""
    link = link.strip()
    if link.isdigit():
        return int(link)
    query = parse_qs(urlparse(link).query)
    for key in ("gameId", "matchId", "match_id", "game_id"):
        if query.get(key, [""])[0].isdigit():
            return int(query[key][0])
    found = re.search(r"/matche?s?/(\d+)", link)
    if found:
        return int(found.group(1))
    runs = [run for run in re.findall(r"\d+", link) if len(run) >= 9]
    if runs:
        return int(max(runs, key=len))
    raise GameError("That link names no game. Paste a match link from aoe2companion or "
                    "aoe2insights, the aoe.ms replay link, or the match id itself.")


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(LARGEST_REPLAY + 1)
    if len(data) > LARGEST_REPLAY:
        raise GameError("The download is larger than any replay should be.")
    return data


def match_record(match: int) -> dict:
    cached = CACHE / f"{match}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    try:
        record = json.loads(download(MATCH_URL.format(match_id=match)))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GameError(f"aoe2companion has no match {match}.") from exc
        raise GameError(f"aoe2companion answered {exc.code} for match {match}.") from exc
    except urllib.error.URLError as exc:
        raise GameError(f"Could not reach aoe2companion: {exc.reason}") from exc
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(record), encoding="utf-8")
    return record


def replay_file(match: int, record: dict) -> Path:
    cached = CACHE / f"{match}.aoe2record"
    if cached.exists():
        return cached
    profiles = [p["profileId"] for team in record.get("teams", []) for p in team.get("players", [])
                if p.get("profileId")]
    for profile in profiles:
        try:
            data = download(REPLAY_URL.format(match_id=match, profile_id=profile))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise GameError(f"Microsoft's replay server answered {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise GameError(f"Could not reach Microsoft's replay server: {exc.reason}") from exc
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(recorded(data))
        return cached
    raise GameError(f"Microsoft has no replay of match {match}. They keep them for a few months, "
                    "and some games never get one.")


def recorded(data: bytes) -> bytes:
    """The .aoe2record in the zip aoe.ms serves, or the bytes themselves when
    they already are one."""
    if len(data) > LARGEST_REPLAY:
        raise GameError("That is larger than any replay should be.")
    if not data.startswith(b"PK\x03\x04"):
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            inner = next(n for n in archive.namelist() if n.endswith(".aoe2record"))
            if archive.getinfo(inner).file_size > LARGEST_REPLAY:
                raise GameError("The replay is larger than any replay should be.")
            return archive.read(inner)
    except (zipfile.BadZipFile, StopIteration) as exc:
        raise GameError("That zip holds no replay.") from exc


def keep_local(data: bytes) -> str:
    """A replay opened from someone's own disk, kept under a name made of its
    content: opening it twice is one file, and its card can still be read
    after the server has let the game go."""
    replay = recorded(data)
    key = "local-" + hashlib.sha1(replay).hexdigest()[:16]
    path = LOCAL / f"{key[6:]}.aoe2record"
    if not path.exists():
        LOCAL.mkdir(parents=True, exist_ok=True)
        path.write_bytes(replay)
    return key


def local_file(key: str) -> Path:
    if not LOCAL_KEY.fullmatch(key):
        raise GameError(f"{key!r} names no game.")
    path = LOCAL / f"{key[6:]}.aoe2record"
    if not path.exists():
        raise GameError("That replay file is no longer here. Open it again.")
    return path
