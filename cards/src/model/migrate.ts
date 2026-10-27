/**
 * Reading a card somebody else's version of the editor wrote.
 *
 * Everything that comes off local storage or out of a file goes through here
 * first, because one unreadable field renders as a blank page rather than as
 * an error: the card is drawn, not validated, so a missing `to` is a crash in
 * the middle of a render and the whole app goes with it.
 *
 * Three shapes so far, and all of them still open:
 *   1. a row was a flat line of items, with the arrows placed by hand;
 *   2. three places, each with a `count` string and an `icons` list;
 *   3. three places of items, with numbers as entities like anything else;
 *      arrows are drawn rather than placed, so that kind no longer exists.
 *   4. no number column: a row's number is simply the first thing in the
 *      place it is about.
 * Retired icon keys are carried across too -- see `RENAMED`.
 * The hand-placed arrows are what says where the places divide, so carrying
 * (1) forward is exact rather than a guess.
 */

import type { Card, CountItem, IconItem, Item, PlaceItem, Section, Slot, Step, Tone } from "./card";
import { TONES, count, newSlot, newStep } from "./card";

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
    case "box":
      return {
        kind: "box",
        id: id(value.id),
        items: (Array.isArray(value.items) ? value.items : [])
          .map(item)
          .filter((child): child is IconItem | { kind: "text"; id: string; text: string } =>
            child !== null && (child.kind === "icon" || child.kind === "text")),
      };
    default:
      return null;
  }
}

const items = (raw: unknown): Item[] =>
  (Array.isArray(raw) ? raw : []).map(item).filter((i): i is Item => i !== null);

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

/** Shape 1: a line of items whose arrows divide it into the places. */
function fromFlatList(value: Loose): Step {
  const raw = (Array.isArray(value.items) ? value.items : []) as Loose[];
  const places: Slot[] = [newSlot()];
  const spilt: Item[] = [];

  for (const entry of raw) {
    // Shape 1's hand-placed arrows are gone as an item kind, but they are
    // still what said where one place ended and the next began.
    if (entry.kind === "arrow") { places.push(newSlot()); continue; }
    const made = item(entry);
    if (!made) continue;
    const here = places[places.length - 1];
    if (made.kind === "icon" || made.kind === "count") here.items.push(made);
    else if (made.kind === "text") here.label = here.label ? `${here.label} ${made.text}` : made.text;
    else spilt.push(made);
  }

  const step = newStep(places[0]);
  step.id = id(value.id);
  // The row's own count box was drawn in front of the first place, in a
  // column of its own. There is no column now, so it goes into that place.
  const lead = leadCount(value);
  if (lead) step.to = { ...step.to, items: [lead, ...step.to.items] };
  step.via = places[1] ?? null;
  step.from = places[2] ?? null;
  // A row with more than three places, and anything a place cannot hold, goes
  // where the card already puts what it only mentions.
  // Extras hold pictures and words: a number that had drifted out there has
  // no resource to be about, so it does not come along.
  step.extras = [...places.slice(3).flatMap((place) => place.items), ...spilt, ...items(value.right)]
    .filter((entry) => entry.kind !== "count");
  return step;
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
    return fromFlatList(value);
  const lead = leadCount(value);
  const to = slot(value.to);
  return {
    id: id(value.id),
    to: lead ? { ...to, items: [lead, ...to.items] } : to,
    via: value.via ? slot(value.via) : null,
    from: value.from ? slot(value.from) : null,
    extras: items(value.extras).filter((entry) => entry.kind !== "count"),
  };
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
