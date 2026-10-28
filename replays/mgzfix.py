"""
mgz 1.8.51, made fit to read a 2026 replay.

Four things stand between it and one, and all four are fixed here rather than
by installing an unmerged fork:

- Save 67.2 added a string to every player record and two words ahead of the
  metadata. aoc-mgz PR 147 reads them; until a release does, the same two reads
  are spliced into the installed module, and skipped once it has its own.
- `Inputs.add_action` fills an empty selection from a cache keyed by command
  type alone, so one player's command inherits another player's units -- 2179
  of 3162 moves in one 4v4. It is switched off; `game.py` resolves selections
  per player.
- A civilisation newer than aocref's dataset is a KeyError, and a built-in map
  newer than it (Arabian Desert, 216) a ValueError.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from pathlib import Path

import mgz.common.map as maps
import mgz.fast.header as header
import mgz.model as model

_SPLICES = (
    ("        if save >= 64.3:\n            data.read(4)\n",
     "        if save >= 64.3:\n            data.read(4)\n"
     "        if save >= 67.2:\n            de_string(data)\n"),
    ("    \"\"\"Parse recorded game metadata.\"\"\"\n    ai = unpack('<I', header)\n",
     "    \"\"\"Parse recorded game metadata.\"\"\"\n"
     "    if save >= 67.2:\n        header.read(8)\n    ai = unpack('<I', header)\n"),
)


def _read_save_67_2() -> None:
    source = inspect.getsource(header)
    if "67.2" in source:
        return
    for old, new in _SPLICES:
        if source.count(old) != 1:
            raise RuntimeError(f"{header.__file__} is not the mgz 1.8.51 this patches; "
                               "check whether the installed mgz reads save 67.2 itself")
        source = source.replace(old, new)
    exec(compile(source, header.__file__, "exec"), header.__dict__)


_dataset = model.get_dataset


def _any_civilisation(*args):
    dataset_id, dataset = _dataset(*args)
    named = dataset["civilizations"]
    dataset["civilizations"] = defaultdict(lambda: {"name": None}, named)
    return dataset_id, dataset


_lookup_map = maps.lookup_name


def _any_map(map_id, name, version, reference):
    try:
        return _lookup_map(map_id, name, version, reference)
    except ValueError:
        return name, False


_consts = model.get_consts


def _any_lobby_setting():
    """Save 68.9 misreads the lobby's settings -- a population of 17116, a
    reveal-map choice of 17105 -- and mgz looks two of them up by key. Nothing
    here reads them, so an unknown one is None rather than a game that cannot
    be opened."""
    consts = _consts()
    for key in ("game_types", "map_reveal_choices"):
        if not isinstance(consts[key], defaultdict):
            consts[key] = defaultdict(lambda: None, consts[key])
    return consts


_read_save_67_2()
model.get_dataset = _any_civilisation
model.get_consts = _any_lobby_setting
maps.lookup_name = _any_map
model.Inputs.add_action = lambda self, action: None


def parse(path: Path):
    with open(path, "rb") as handle:
        return model.parse_match(handle)
