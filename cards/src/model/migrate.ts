/**
 * Reading a card somebody else's version of the editor wrote.
 *
 * Everything that comes off local storage or out of a file goes through here
 * first, because one unreadable field renders as a blank page rather than as
 * an error: the card is drawn, not validated, so a missing `to` is a crash in
 * the middle of a render and the whole app goes with it.
 *
 * Six shapes so far, and all of them still open:
 *   1. a row was a flat line of items, with the arrows placed by hand;
 *   2. three places, each with a `count` string and an `icons` list;
 *   3. three places of items, with numbers as entities like anything else;
 *      arrows are drawn rather than placed, so that kind no longer exists.
 *   4. no number column: a row's number is simply the first thing in the
 *      place it is about.
 *   5. two halves: new villagers on the left, the ones moved off other work
 *      on the right. A row of shapes 1-4 with a source was a move, so it
 *      becomes the right half whole.
 *   6. no "before" places: what is done on the way follows the work in the
 *      same place, drawn small, and a move's number is on where they went
 *      rather than on the source. A row of shapes 1-5 numbering both the
 *      source and where they went said "3 off the sheep, 4 to the hunt": that
 *      is 3 moved and 1 new to the hunt, so the 1 goes to the new villagers.
 * Retired icon keys are carried across too -- see `RENAMED`.
 * The hand-placed arrows are what says where the places divide, so carrying
 * (1) forward is exact rather than a guess.
 */

import type { Card, CountItem, Item, PlaceItem, Section, Slot, Step, Tone } from "./card";
import { TONES, count, newSlot } from "./card";

const TONE_KEYS = new Set(TONES.map(([tone]) => tone));

/** Icon keys the set has retired. The file goes when the key does, so a card
 *  still naming one would draw a broken tile rather than a picture. A mine or
 *  a wood line is the resource itself on a card now. */
const RENAMED: Record<string, string> = {
  "gaia-tree": "gaia-straggler",
  "gaia-woodline": "resource-wood",
  "gaia-gold_mine": "resource-gold",
  "gaia-stone_mine": "resource-stone",
};

const str = (value: unknown, fallback = "") =>
  typeof value === "string" ? value : typeof value === "number" ? String(value) : fallback;

const id = (value: unknown) => str(value) || crypto.randomUUID();

type Loose = Record<string, unknown>;

function item(raw: unknown): Item | null {
  const value = raw as Loose;
  if (!value || typeof value !== "object") return null;
  switch (value.kind) {
    case "icon": {
      const key = str(value.icon);
      return key
        ? { kind: "icon", id: id(value.id), icon: RENAMED[key] ?? key,
            caption: str(value.caption) }
        : null;
    }
    case "count":
      return { kind: "count", id: id(value.id), value: str(value.value), total: str(value.total) };
    case "text":
      return { kind: "text", id: id(value.id), text: str(value.text) };
    default:
      return null;
  }
}

/** One stored item, or what was in it: the hunt box is gone, so a box saved
 *  before is opened as its contents, in its place. */
function unboxed(raw: unknown): Item[] {
  const value = raw as Loose;
  if (value && typeof value === "object" && value.kind === "box")
    return (Array.isArray(value.items) ? value.items : []).flatMap(unboxed);
  const made = item(raw);
  return made ? [made] : [];
}

const items = (raw: unknown): Item[] => (Array.isArray(raw) ? raw : []).flatMap(unboxed);

const placeItems = (raw: unknown): PlaceItem[] =>
  items(raw).filter((i): i is PlaceItem => i.kind === "icon" || i.kind === "count");

function slot(raw: unknown): Slot {
  const value = (raw ?? {}) as Loose;
  // Shape 2 kept the number as a string beside the icons; it is an entity now,
  // and it was drawn in front of them.
  const lead = str(value.count);
  const rest = placeItems(value.items ?? value.icons);
  return {
    label: str(value.label),
    items: lead ? [count(lead), ...rest] : rest,
  };
}

/** A row of shapes 1-5, which still had a "before" place in each column. */
type Wide = Step & { via: Slot | null; moveVia: Slot | null };

/** Shape 1: a line of items whose arrows divide it into the places. */
function fromFlatList(value: Loose): Wide {
  const raw = (Array.isArray(value.items) ? value.items : []) as Loose[];
  const places: Slot[] = [newSlot()];
  const spilt: Item[] = [];

  for (const entry of raw) {
    // Shape 1's hand-placed arrows are gone as an item kind, but they are
    // still what said where one place ended and the next began.
    if (entry.kind === "arrow") { places.push(newSlot()); continue; }
    // A box was a group of things the row mentioned: its contents go there.
    if (entry.kind === "box") { spilt.push(...unboxed(entry)); continue; }
    const made = item(entry);
    if (!made) continue;
    const here = places[places.length - 1];
    if (made.kind === "icon" || made.kind === "count") here.items.push(made);
    else here.label = here.label ? `${here.label} ${made.text}` : made.text;
  }

  // The row's own count box was drawn in front of the first place, in a
  // column of its own. There is no column now, so it goes into that place.
  const lead = leadCount(value);
  return {
    id: id(value.id),
    to: lead ? { ...places[0], items: [lead, ...places[0].items] } : places[0],
    via: places[1] ?? null,
    moveTo: null,
    moveVia: null,
    from: places[2] ?? null,
    // A row with more than three places, and anything a place cannot hold,
    // goes where the card already puts what it only mentions. A number that
    // had drifted out there had no resource to be about, so it stays behind.
    extras: [...places.slice(3).flatMap((place) => place.items), ...spilt, ...items(value.right)]
      .filter((entry) => entry.kind !== "count"),
  };
}

function leadCount(value: Loose): CountItem | null {
  const raw = value.count;
  if (raw && typeof raw === "object") {
    const made = item(raw);
    return made?.kind === "count" ? made : null;
  }
  return str(raw) ? count(str(raw)) : null;
}

function step(raw: unknown): Step {
  const value = (raw ?? {}) as Loose;
  if (value.to === undefined && (value.items !== undefined || value.right !== undefined))
    return narrowed(moved(fromFlatList(value)));
  const lead = leadCount(value);
  const to = slot(value.to);
  const made: Wide = {
    id: id(value.id),
    to: lead ? { ...to, items: [lead, ...to.items] } : to,
    via: value.via ? slot(value.via) : null,
    moveTo: value.moveTo ? slot(value.moveTo) : null,
    moveVia: value.moveVia ? slot(value.moveVia) : null,
    from: value.from ? slot(value.from) : null,
    extras: items(value.extras),
  };
  return narrowed("moveTo" in value ? made : moved(made));
}

/** Shapes 1-4: a row with a source moved villagers, so all of it is the moved half. */
function moved(row: Wide): Wide {
  if (!row.from) return row;
  return { ...row, moveTo: row.to, moveVia: row.via, to: newSlot(), via: null };
}

const joined = (place: Slot | null, after: Slot | null): Slot | null =>
  place && after
    ? { items: [...place.items, ...after.items], label: [place.label, after.label].filter(Boolean).join(" ") }
    : place ?? after;

const isCount = (entry: PlaceItem): entry is CountItem => entry.kind === "count";

/** Shapes 1-5: each "before" place follows its work, and the source's number
 *  goes to where the villagers went. */
function narrowed(row: Wide): Step {
  let to = joined(row.to, row.via)!;
  const leaving = row.from?.items.filter(isCount) ?? [];
  let moveTo = joined(row.moveTo, row.moveVia) ?? (leaving.length ? newSlot() : null);
  const from = row.from && { ...row.from, items: row.from.items.filter((entry) => !isCount(entry)) };
  if (leaving.length && moveTo) {
    const arriving = moveTo.items.filter(isCount);
    const [off, on] = [Number(leaving[0].value), Number(arriving[0]?.value)];
    const work = moveTo.items.find((entry) => entry.kind === "icon");
    if (!arriving.length) {
      moveTo = { ...moveTo, items: [...leaving, ...moveTo.items] };
    } else if (leaving.length === 1 && arriving.length === 1 && Number.isInteger(off) && Number.isInteger(on)
               && off < on && work && !to.items.length) {
      moveTo = { ...moveTo, items: moveTo.items.map((entry) =>
        entry === arriving[0] ? { ...entry, value: String(off) } : entry) };
      to = { ...to, items: [count(String(on - off)), { ...work, id: crypto.randomUUID() }] };
    }
  }
  return { id: row.id, to, moveTo, from, extras: row.extras };
}

function section(raw: unknown): Section {
  const value = (raw ?? {}) as Loose;
  return {
    id: id(value.id),
    label: str(value.label, "Phase"),
    tone: TONE_KEYS.has(value.tone as Tone) ? (value.tone as Tone) : "neutral",
    numbered: value.numbered !== false,
    // An empty phase is allowed, so an empty list is read as one rather than
    // quietly given a row back.
    steps: (Array.isArray(value.steps) ? value.steps : []).map(step),
  };
}

export function normaliseCard(raw: unknown): Card | null {
  const value = raw as Loose;
  if (!value || typeof value !== "object" || !Array.isArray(value.sections)) return null;
  return {
    id: id(value.id),
    name: str(value.name, "Untitled build"),
    title: str(value.title),
    subtitle: str(value.subtitle),
    totals: value.totals !== false,
    rowNumbers: value.rowNumbers === "villagers" ? "villagers" : "steps",
    updated: typeof value.updated === "number" ? value.updated : Date.now(),
    sections: value.sections.map(section),
  };
}
