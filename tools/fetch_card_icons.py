"""Download the icon set the card editor draws into cards/public/icons/aoe2/.

Run once: ``python tools/fetch_card_icons.py``. The card app is a static site
with no backend, so every image it can draw has to be on disk beside it.

It also writes ``replays/units.json``, every unit to its upgrade line, which
the replay reader names units by.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from techtree import (TECHTREE, fetch, node_ages, nodes_by_name,  # noqa: E402
                      picture_indices, trees, wiki_thumbnails)

OUT = ROOT / "cards" / "public" / "icons" / "aoe2"
CIVDATA = ROOT / "aoe2planner" / "gamedata" / "civdata.json"
CATALOGUE = ROOT / "cards" / "src" / "icons.generated.ts"
LINES = ROOT / "replays" / "units.json"

BUILDINGS = {
    "town_center": 109, "house": 70, "mill": 68, "lumber_camp": 562,
    "mining_camp": 584, "farm": 50, "barracks": 12, "archery_range": 87,
    "stable": 101, "blacksmith": 103, "market": 84, "monastery": 104,
    "university": 209, "siege_workshop": 49, "dock": 45, "castle": 82,
    "watch_tower": 79, "guard_tower": 234, "keep": 235, "bombard_tower": 236,
    "outpost": 598, "palisade_wall": 72, "stone_wall": 117, "gate": 487,
    "wonder": 276, "folwark": 1734, "mule_cart": 1808, "donjon": 1665,
    "krepost": 1251, "feitoria": 1021, "caravanserai": 1754, "settlement": 2556,
    "pasture": 1889,
}

UNITS = {
    "villager": 83, "scout": 448, "militia": 74, "man_at_arms": 75,
    "long_swordsman": 77, "spearman": 93, "pikeman": 358, "archer": 4,
    "skirmisher": 7, "crossbowman": 24, "cavalry_archer": 39, "knight": 38,
    "light_cavalry": 546, "camel": 329, "monk": 125, "trade_cart": 128,
    "battering_ram": 35, "mangonel": 280, "scorpion": 279, "eagle_scout": 751,
    "fishing_ship": 13, "transport_ship": 545, "trade_cog": 17, "galley": 21,
}

UNIT_NODES = {"Unit", "UniqueUnit", "RegionalUnit", None}
LINKED = {"Unit", "UniqueUnit", "RegionalUnit", "UnitUpgrade"}
# Every tech these ages offer, on top of TECHS: what a build order researches
# on the way to Castle Age and in it.
TECH_AGES = {2, 3}

# Internal names rather than ids: a tech's id is meaningless at a glance, and
# the .dat's own spelling is close enough to a label to be worth reading.
TECHS = [
    "Loom", "Feudal Age", "Middle Age", "Imperial Age", "Wheel Barrow",
    "Hand Cart", "Double Bit Axe", "Bow Saw", "Two Man Saw", "Horse collar",
    "Heavy plow", "Crop rotation", "Gold Mining", "Gold Shaft Mining",
    "Stone Mining", "Stone Shaft Mining", "Town Watch", "Town Patrol",
    "Man-At-Arms", "Forging", "Scale Mail Armor", "Squires", "Fletching",
    "Padded Archer Armor", "Ballistics", "Bloodlines", "Husbandry", "Chemistry",
    "Bodkin Arrow",
]

LABELS = {
    "Middle Age": "Castle Age", "Wheel Barrow": "Wheelbarrow",
    "Horse collar": "Horse Collar", "Heavy plow": "Heavy Plow",
    "Crop rotation": "Crop Rotation", "Double Bit Axe": "Double-Bit Axe",
    "Two Man Saw": "Two-Man Saw", "Man-At-Arms": "Man-at-Arms",
    "town_center": "Town Centre", "man_at_arms": "Man-at-Arms",
    "eagle_scout": "Eagle Scout", "light_cavalry": "Light Cavalry",
}

# The tech tree's own resource art is the 20px sprite off the resource bar,
# which is mush at a card's tile size; the wiki has the same four at 66px.
RESOURCES = {"food": ["Aoe2de food.png"], "wood": ["Aoe2de wood.png"],
             "gold": ["Aoe2de gold.png"], "stone": ["Aoe2de stone.png"]}

# Gaia no tech tree draws. Several titles per key because the wiki is not
# consistent about capitalising "DE", and a miss is silent otherwise. No gold
# mine, stone mine or wood line: on a card those are the resource itself.
GAIA = {
    "sheep": ["Sheep aoe2DE.png"],
    "boar": ["Boar aoe2DE.png"],
    "deer": ["Deer aoe2de.png"],
    "berries": ["Berrybush portrait de.png", "BerryBushDE.png",
                "Berrybush icon aoe2.png"],
    "fish": ["Fishicon aoe2de.png", "Fish icon AoEDE.png"],
    "relic": ["Relic aoe2DE.png"],
    "chicken": ["Chicken icon AoE2DE.png", "Chicken aoe2de.png"],
    "llama": ["Llama AoE2DE.png"],
    "turkey": ["Turkey AoE2DE.png"],
}

# Icons cut out of a bigger picture. The box is a *fraction* of the source,
# because the wiki serves whatever size it has rather than the one asked for;
# whatever is transparent around the result is trimmed off after. The
# straggler is Age of Mythology Retold's bamboo: the wiki has no AoE2 tree that
# is not a clump, and one plant on its own is what tells it from wood.
CROPPED = {
    "gaia-straggler": ("AoMR Tree Bamboo.png", (0.0, 0.0, 1.0, 1.0), "Straggler Tree"),
}

CATEGORIES = [("resource", "Resources"), ("building", "Buildings"),
              ("unit", "Units"), ("tech", "Technologies")]

# Which shelf a key's prefix sits on. Gaia shares the resources' shelf, but
# keeps its own prefix: the prefix is in every saved card's icon keys.
SHELF = {"gaia": "resource"}

AGES = {1: "Dark Age", 2: "Feudal Age", 3: "Castle Age", 4: "Imperial Age"}

# Categories listed in the order a player unlocks them rather than by name:
# when you can have the thing is what a build order is about, and alphabetical
# says nothing. Units are left alphabetical -- you look those up by name.
BY_AGE = {"building", "tech"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def label_for(key: str, name: str) -> str:
    if key in LABELS:
        return LABELS[key]
    if name in LABELS:
        return LABELS[name]
    return name.replace("_", " ").title() if name == key else name


Row = tuple[str, str, str, "int | None"]


def plan() -> tuple[dict[str, str], list[Row]]:
    """``icon key -> url``, and the catalogue rows the app searches."""
    civdata = json.loads(CIVDATA.read_text(encoding="utf-8"))
    techs = {t["internal_name"]: t["id"] for t in civdata["techs"].values()}

    print("resolving icon indices across civ trees…", flush=True)
    index = picture_indices()
    ages = node_ages()
    named = nodes_by_name()

    urls: dict[str, str] = {}
    rows: list[Row] = []
    missing: list[str] = []

    def add(category: str, key: str, label: str, kind: str, dat_id: int) -> None:
        picture = index.get((kind, dat_id))
        if picture is None:
            missing.append(f"{category}-{key}")
            return
        urls[f"{category}-{key}"] = f"{TECHTREE}/img/{kind}/{picture}.png"
        rows.append((category, key, label, ages.get((kind, dat_id))))

    for key, dat_id in BUILDINGS.items():
        add("building", key, label_for(key, key), "Building", dat_id)
    for key, dat_id in UNITS.items():
        add("unit", key, label_for(key, key), "Unit", dat_id)
    # Every unit any civ can make, but only the first of each line: an upgrade
    # wears its line's icon (`replays/units.json` says which), so the shelf has
    # one Archer rather than three.
    have = set(UNITS.values())
    for node in unit_nodes().values():
        if node["node_id"] in have or node is not line_start(node):
            continue
        key = unit_key(node["name"])
        if f"unit-{key}" not in urls:
            urls[f"unit-{key}"] = f"{TECHTREE}/img/Unit/{node['picture_index']}.png"
            rows.append(("unit", key, node["name"], node.get("age_id")))
    # Techs go by *name*, falling back to the id. The tech tree and the .dat
    # disagree about which id the age-ups wear, and picking the wrong one is
    # silent: you get a real icon, just the neighbouring age's.
    for name in TECHS:
        key, label = slug(name), label_for(slug(name), name)
        found = named.get(("Tech", label))
        if found:
            urls[f"tech-{key}"] = f"{TECHTREE}/img/Tech/{found[0]}.png"
            rows.append(("tech", key, label, found[1]))
        elif name in techs:
            add("tech", key, label, "Tech", techs[name])
        else:
            missing.append(f"tech-{key}")
    named_techs = {row[2] for row in rows if row[0] == "tech"}
    for (kind, label), (picture, age) in sorted(named.items(), key=lambda kv: kv[0][1]):
        if kind == "Tech" and age in TECH_AGES and label not in named_techs:
            named_techs.add(label)
            urls[f"tech-{slug(label)}"] = f"{TECHTREE}/img/Tech/{picture}.png"
            rows.append(("tech", slug(label), label, age))

    print("resolving wiki art…", flush=True)
    for category, wanted in (("resource", RESOURCES), ("gaia", GAIA)):
        for key, titles in wanted.items():
            found = wiki_thumbnails({t: t for t in titles}, 256)
            hit = next((found[t] for t in titles if t in found), None)
            if hit is None:
                missing.append(f"{category}-{key}")
                continue
            urls[f"{category}-{key}"] = hit
            rows.append((category, key, label_for(key, key), None))

    if missing:
        print(f"no icon found for {len(missing)}: {', '.join(sorted(missing))}")
    return urls, rows


def unit_key(name: str) -> str:
    return slug(name).replace("-", "_")


_UNITS: dict[int, dict] = {}


def unit_nodes() -> dict[int, dict]:
    """Every unit in any civ's tree, by id: a unit only some civs have is in
    only their trees."""
    if not _UNITS:
        for tree in trees():
            for node in tree.get("units_techs", []):
                if node.get("use_type") == "Unit" and node.get("node_type") in UNIT_NODES | {"UnitUpgrade"}:
                    _UNITS.setdefault(node["node_id"], node)
    return _UNITS


def line_start(node: dict) -> dict:
    """The unit an upgrade line begins with: Crossbowman -> Archer."""
    units, seen = unit_nodes(), set()
    while node.get("link_node_type") in LINKED and node.get("link_id") in units and node["node_id"] not in seen:
        seen.add(node["node_id"])
        node = units[node["link_id"]]
    return node


def write_lines(kept: set[str]) -> None:
    """``replays/units.json``: every unit name to the line it belongs to, so a
    card can draw an Elite Skirmisher as the Skirmisher it was trained as, and
    a game's plan can count Man-at-Arms and Long Swordsmen as one line."""
    keys = {dat_id: f"unit-{key}" for key, dat_id in UNITS.items()}
    lines = {}
    for node in unit_nodes().values():
        start = line_start(node)
        key = keys.get(start["node_id"], f"unit-{unit_key(start['name'])}")
        lines[node["name"]] = {
            "line": start["name"],
            "icon": key if key in kept else None,
            "unique": start.get("node_type") == "UniqueUnit",
            "building": start.get("building_id"),
        }
    # The tree names the trebuchet as it stands packed; a replay names it plainly.
    lines.setdefault("Trebuchet", lines.get("Trebuchet (Packed)"))
    LINES.write_text(json.dumps(dict(sorted(lines.items())), indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {LINES.relative_to(ROOT)} with {len(lines)} units")


def write_catalogue(rows: list[Row], kept: set[str]) -> None:
    """The picker's list, generated so a fetch and the app cannot disagree."""
    order = {name: i for i, (name, _) in enumerate(CATEGORIES)}
    # An age-sorted category leads on the age; everything else ignores it, so
    # one key serves both. A thing no tree places sorts last rather than first.
    # On a shared shelf the shelf's own rows come first: the four resources
    # ahead of the animals.
    rows = sorted((r for r in rows if f"{r[0]}-{r[1]}" in kept),
                  key=lambda r: (order[SHELF.get(r[0], r[0])],
                                 (r[3] or 9) if r[0] in BY_AGE else 0,
                                 r[0] in SHELF,
                                 r[2]))

    def entry(category: str, key: str, label: str, age: int | None) -> str:
        at = f', age: "{AGES[age]}"' if age in AGES else ""
        shelf = SHELF.get(category, category)
        return f'  {{ key: "{category}-{key}", label: "{label}", category: "{shelf}"{at} }},'

    lines = [
        "// Generated by tools/fetch_card_icons.py -- do not hand-edit.",
        "export type IconEntry =",
        "  { key: string; label: string; category: string; age?: string };",
        "",
        "export const ICON_CATEGORIES: [string, string][] = [",
        *[f'  ["{key}", "{label}"],' for key, label in CATEGORIES],
        "];",
        "",
        "export const ICONS: IconEntry[] = [",
        *[entry(*row) for row in rows],
        "];",
        "",
    ]
    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {CATALOGUE.relative_to(ROOT)} with {len(rows)} icons")


def cut_out() -> list[Row]:
    """Crop the icons that have to be cut out of a larger picture."""
    from PIL import Image

    rows: list[Row] = []
    for key, (title, box, label) in CROPPED.items():
        found = wiki_thumbnails({title: title}, 512)
        if title not in found:
            print(f"cannot cut {key}: no {title}")
            continue
        art = Image.open(io.BytesIO(fetch(found[title]))).convert("RGBA")
        art = art.crop((round(box[0] * art.width), round(box[1] * art.height),
                        round(box[2] * art.width), round(box[3] * art.height)))
        bounds = art.split()[-1].getbbox()
        if bounds:
            art = art.crop(bounds)
        art.save(OUT / f"{key}.png")
        category, name = key.split("-", 1)
        rows.append((category, name, label, None))
        print(f"  cut {key} out of {title} {art.size}", flush=True)
    return rows


def main() -> int:
    urls, rows = plan()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"downloading {len(urls)} icons to {OUT}", flush=True)
    kept, failed = set(), []
    for i, (key, url) in enumerate(sorted(urls.items()), 1):
        try:
            image = fetch(url)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            failed.append(f"{key} ({exc})")
            continue
        if not image.startswith(b"\x89PNG"):
            failed.append(f"{key} (not a PNG)")
            continue
        (OUT / f"{key}.png").write_bytes(image)
        kept.add(key)
        print(f"  {i}/{len(urls)} {key}", flush=True)
    if failed:
        print(f"failed: {', '.join(failed)}")
    for row in cut_out():
        rows.append(row)
        kept.add(f"{row[0]}-{row[1]}")
    write_catalogue(rows, kept)
    write_lines(kept)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
