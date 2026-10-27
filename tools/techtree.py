"""Reading SiegeEngineers' aoe2techtree and the Age of Empires wiki: where the
icons come from and which age each one unlocks in. ``fetch_card_icons.py`` is
what uses it.

aoe2techtree keys its images by the .dat's *icon* index rather than by unit id,
so everything has to be resolved through the per-civ tree files that carry
that index. Gaia -- the sheep, boar and deer a build order lures -- is in no
tech tree at all, so it comes from the wiki.

The art is Microsoft's, redistributed the way the fan wikis do it.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

TECHTREE = "https://raw.githubusercontent.com/SiegeEngineers/aoe2techtree/master"
TREE_INDEX = "https://api.github.com/repos/SiegeEngineers/aoe2techtree/contents/data/trees"
WIKI = "https://ageofempires.fandom.com/api.php"
AGENT = {"User-Agent": "aoe2-build-cards-icon-fetch"}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch_json(url: str) -> dict:
    return json.loads(fetch(url))



_TREES: list[dict] = []


def trees() -> list[dict]:
    """Every civ's tree, downloaded once per process.

    Both the icon index and the age a thing becomes available in come off
    these, and there are 56 of them, so they are fetched once and kept.
    """
    if _TREES:
        return _TREES
    names = [entry["name"] for entry in fetch_json(f"{TREE_INDEX}?per_page=200")
             if entry["name"].endswith(".json")]
    for i, name in enumerate(names, 1):
        print(f"  tree {i}/{len(names)} {name}", flush=True)
        _TREES.append(fetch_json(f"{TECHTREE}/data/trees/{urllib.parse.quote(name)}"))
    return _TREES


def _nodes():
    for tree in trees():
        for group in ("buildings", "units_techs"):
            yield from tree.get(group, [])


def picture_indices() -> dict[tuple[str, int], int]:
    """``(use_type, dat id) -> icon index``, merged over every civ's tree.

    Merged rather than read from one civ because a tech only appears in the
    trees of the civs that can research it.
    """
    return {(node["use_type"], node["node_id"]): node["picture_index"]
            for node in _nodes()}


def nodes_by_name() -> dict[tuple[str, str], tuple[int, int | None]]:
    """``(use_type, display name) -> (icon index, age)``.

    A second way to find a node, because the ids do not always agree. The .dat
    ids in ``civdata.json`` line up with the tech tree's for almost everything
    but the age-ups: the tree calls node 101 "Feudal Age" where civdata calls
    101 "Middle Age", which silently fetches the Castle banner for Feudal and
    the Feudal one for Castle. A name cannot be off by one.
    """
    out: dict[tuple[str, str], tuple[int, int | None]] = {}
    for node in _nodes():
        out[(node["use_type"], node["name"])] = (node["picture_index"], node.get("age_id"))
    return out


def node_ages() -> dict[tuple[str, int], int]:
    """``(use_type, dat id) -> the age it becomes available in``.

    1 dark, 2 feudal, 3 castle, 4 imperial -- the tech tree's own numbering,
    read off the same nodes as the icons rather than derived from the tech
    graph.

    The age *most* civs give it, not the earliest. Exactly one building differs
    across the 56 trees -- the Siege Workshop is Feudal for the Cumans and
    Castle for everyone else -- and one civ's bonus should not move it for
    everybody. A building only one civ has has only one answer either way.
    """
    seen: dict[tuple[str, int], Counter[int]] = defaultdict(Counter)
    for node in _nodes():
        if node.get("age_id"):
            seen[(node["use_type"], node["node_id"])][node["age_id"]] += 1
    return {key: ages.most_common(1)[0][0] for key, ages in seen.items()}


def wiki_thumbnails(titles: dict[str, str], width: int) -> dict[str, str]:
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "imageinfo",
        "iiprop": "url", "iiurlwidth": width,
        "titles": "|".join(f"File:{t}" for t in titles.values()),
    })
    pages = fetch_json(f"{WIKI}?{query}")["query"]["pages"].values()
    # Wikia re-encodes thumbnails as WebP unless asked for the source format.
    by_title = {p["title"]: (p["imageinfo"][0].get("thumburl")
                             or p["imageinfo"][0]["url"]) + "&format=original"
                for p in pages if p.get("imageinfo")}
    return {key: by_title[f"File:{title}"]
            for key, title in titles.items() if f"File:{title}" in by_title}

