/**
 * The document, and every edit that can be made to it.
 *
 * A row is three columns. The first says what the **new** villagers do, read
 * right to left: where they end up (`to`) and what they do on the way (`via`).
 * The second, the ones **moved** off other work: where they go (`moveTo`), what
 * they do on the way (`moveVia`) and the work they were taken off (`from`) —
 * the number is on the source, since everyone taken off it goes to the same
 * place. The third, `extras`, is what the row merely mentions: the deer pushed
 * in, a tech, a note. Only `to` is always there, and the arrows between places
 * are drawn rather than placed.
 *
 * Everything on a row is an entity with an id: icons, numbers, notes. That is
 * what lets one thing be selected, dragged anywhere and deleted, rather than
 * some of them being fields on their container.
 *
 * Nothing here renders and nothing here touches storage, so the shape of a
 * card can be changed without reading anything else.
 */

import type { Job } from "./jobs";
import { jobOf } from "./jobs";

export type Tone = "dark" | "feudal" | "castle" | "imperial" | "transition" | "neutral";

export type IconItem = { kind: "icon"; id: string; icon: string; caption: string };
/**
 * A number, and under it the villagers on the work its place names.
 *
 * `total` is that figure stated outright. Left empty it is counted up — every
 * number adds its own value to its work — and typed in it *sets* the running
 * figure from there on, because an absolute is a statement about the build
 * that arithmetic over the card cannot know: "All" off the sheep is no number,
 * but it does say nobody is left on them.
 */
export type CountItem = { kind: "count"; id: string; value: string; total: string };
export type TextItem = { kind: "text"; id: string; text: string };

export type Item = IconItem | CountItem | TextItem;
/** What one of the three places can hold. A note belongs to the place as its
 *  words, and the arrows between places are drawn rather than placed. */
export type PlaceItem = IconItem | CountItem;

export type Slot = { items: PlaceItem[]; label: string };

/** The named parts of a row. */
export type Part = "to" | "via" | "moveTo" | "moveVia" | "from" | "extras";

export type Step = {
  id: string;
  to: Slot;
  via: Slot | null;
  moveTo: Slot | null;
  moveVia: Slot | null;
  from: Slot | null;
  extras: Item[];
};

export type Section = { id: string; label: string; tone: Tone; numbered: boolean; steps: Step[] };

/** What the circle on a row counts: the rows themselves, or the villagers the
 *  card has put to work once the row is done. */
export type RowNumbers = "steps" | "villagers";

export type Card = {
  id: string;
  name: string;
  title: string;
  subtitle: string;
  /** Draw the running villager total under each number. */
  totals: boolean;
  rowNumbers: RowNumbers;
  sections: Section[];
  updated: number;
};

/** `side` is which edge of `item` a drop landed on — the caret the card draws
 *  while dragging. Absent it means "before", which is where something arriving
 *  from outside goes. */
export type Where = {
  section: string; step?: string; part?: Part; item?: string;
  side?: "before" | "after";
};

export const TONES: [Tone, string][] = [
  ["dark", "Dark Age"],
  ["transition", "Transition"],
  ["feudal", "Feudal Age"],
  ["castle", "Castle Age"],
  ["imperial", "Imperial Age"],
  ["neutral", "Neutral"],
];

export const SLOTS: [Exclude<Part, "extras">, string, string][] = [
  ["to", "End", "where new villagers end up"],
  ["via", "Before", "what they do on the way"],
  ["moveTo", "Moved to", "where villagers taken off other work go"],
  ["moveVia", "Moved via", "what they do on the way"],
  ["from", "Source", "the work they were taken off"],
];

/** The places of the moved villagers, the right-hand half of a row. */
export const MOVE_PARTS = ["moveTo", "moveVia", "from"] as const;

const id = () => crypto.randomUUID();

export const icon = (key: string): IconItem => ({ kind: "icon", id: id(), icon: key, caption: "" });
export const count = (value = "1", total = ""): CountItem =>
  ({ kind: "count", id: id(), value, total });
export const text = (value = "text"): TextItem => ({ kind: "text", id: id(), text: value });

export const newSlot = (items: PlaceItem[] = [], label = ""): Slot => ({ items, label });

export const newStep = (to: Slot = newSlot()): Step =>
  ({ id: id(), to, via: null, moveTo: null, moveVia: null, from: null, extras: [] });

export const movesAnyone = (step: Step): boolean =>
  MOVE_PARTS.some((part) => !slotIsEmpty(step[part]));

/** A phase starts empty. A card is allowed to have no rows at all — a set of
 *  named bands waiting to be filled is a real thing to want, and a blank row
 *  you did not ask for is one you have to delete. */
export const newSection = (label = "New phase", tone: Tone = "neutral"): Section =>
  ({ id: id(), label, tone, numbered: true, steps: [] });

/** The phases every build order has, in order. A card can be given more or
 *  have them deleted, but this is what one starts as — the ages, and the
 *  stretch between each pair of them where the work actually differs. Both
 *  transitions wear the same neutral band, which is what says they are the
 *  in-between rather than an age. */
export const PHASES: [string, Tone][] = [
  ["Dark Age", "dark"],
  ["Going Feudal", "transition"],
  ["Feudal Age", "feudal"],
  ["Going Castle", "transition"],
  ["Castle Age", "castle"],
];

export const newCard = (name = "Untitled build"): Card => ({
  id: id(),
  name,
  title: name,
  subtitle: "",
  totals: true,
  rowNumbers: "steps",
  sections: PHASES.map(([label, tone]) => newSection(label, tone)),
  updated: Date.now(),
});

const cloneItem = <T extends Item>(item: T): T => ({ ...item, id: id() });

const cloneSlot = (slot: Slot | null): Slot | null =>
  slot && { ...slot, items: slot.items.map(cloneItem) };

const cloneStep = (step: Step): Step => ({
  ...step,
  id: id(),
  to: cloneSlot(step.to)!,
  via: cloneSlot(step.via),
  moveTo: cloneSlot(step.moveTo),
  moveVia: cloneSlot(step.moveVia),
  from: cloneSlot(step.from),
  extras: step.extras.map(cloneItem),
});

/** A copy under a fresh identity, so duplicating never aliases an item id. */
export const reborn = (card: Card, name: string): Card => ({
  ...card,
  id: id(),
  name,
  updated: Date.now(),
  sections: card.sections.map((s) => ({ ...s, id: id(), steps: s.steps.map(cloneStep) })),
});

const swap = <T,>(list: T[], from: number, to: number): T[] => {
  if (to < 0 || to >= list.length) return list;
  const out = list.slice();
  const [moved] = out.splice(from, 1);
  out.splice(to, 0, moved);
  return out;
};

export function mapSection(card: Card, sectionId: string, f: (s: Section) => Section): Card {
  return { ...card, sections: card.sections.map((s) => (s.id === sectionId ? f(s) : s)) };
}

export function mapStep(card: Card, at: Where, f: (s: Step) => Step): Card {
  return mapSection(card, at.section, (section) => ({
    ...section,
    steps: section.steps.map((step) => (step.id === at.step ? f(step) : step)),
  }));
}

export function addSection(card: Card, after: string | null): Card {
  const index = card.sections.findIndex((s) => s.id === after);
  const sections = card.sections.slice();
  sections.splice(index < 0 ? sections.length : index + 1, 0, newSection());
  return { ...card, sections };
}

export function moveSection(card: Card, sectionId: string, by: number): Card {
  const at = card.sections.findIndex((s) => s.id === sectionId);
  return { ...card, sections: swap(card.sections, at, at + by) };
}

export const dropSection = (card: Card, sectionId: string): Card =>
  card.sections.length === 1
    ? { ...card, sections: [newSection()] }
    : { ...card, sections: card.sections.filter((s) => s.id !== sectionId) };

/** Add a row after `at.step`, or at the end of the phase when none is named.
 *  The row is passed in rather than made here so the caller can select it: a
 *  row you have to go and click before using is half an "add". */
export function addStep(card: Card, at: Where, made: Step = newStep()): Card {
  return mapSection(card, at.section, (section) => {
    const index = section.steps.findIndex((s) => s.id === at.step);
    const steps = section.steps.slice();
    steps.splice(index < 0 ? steps.length : index + 1, 0, made);
    return { ...section, steps };
  });
}

export function moveStep(card: Card, at: Where, by: number): Card {
  return mapSection(card, at.section, (section) => {
    const index = section.steps.findIndex((s) => s.id === at.step);
    return { ...section, steps: swap(section.steps, index, index + by) };
  });
}

export function duplicateStep(card: Card, at: Where): Card {
  return mapSection(card, at.section, (section) => {
    const index = section.steps.findIndex((s) => s.id === at.step);
    if (index < 0) return section;
    const steps = section.steps.slice();
    steps.splice(index + 1, 0, cloneStep(section.steps[index]));
    return { ...section, steps };
  });
}

export const dropStep = (card: Card, at: Where): Card =>
  mapSection(card, at.section, (section) =>
    ({ ...section, steps: section.steps.filter((s) => s.id !== at.step) }));

/**
 * Move a whole row, so that it takes the position of the row it was dropped
 * on — or the end of the phase, if it was dropped on no row in particular. A
 * row may cross phases, which is why this is not `moveStep` with a number.
 *
 * The landing index is read off the card *before* the row is lifted out. The
 * removal shifts everything after it left by one, so that one index means
 * "after the target" when the row moved down and "before it" when it moved
 * up, which is what taking the target's place looks like either way.
 */
export function relocateStep(card: Card, from: Where, to: Where): Card {
  if (from.step === to.step) return card;
  const source = findStep(card, from);
  if (!source) return card;
  const target = card.sections.find((s) => s.id === to.section);
  const index = target ? target.steps.findIndex((s) => s.id === to.step) : -1;

  const lifted = mapSection(card, from.section, (section) => ({
    ...section,
    steps: section.steps.filter((s) => s.id !== from.step),
  }));
  return mapSection(lifted, to.section, (section) => {
    const steps = section.steps.slice();
    steps.splice(index < 0 ? steps.length : Math.min(index, steps.length), 0, source);
    return { ...section, steps };
  });
}

// ------------------------------------------------------------------- places

export function mapSlot(card: Card, at: Where, f: (slot: Slot) => Slot): Card {
  const part = at.part;
  if (!part || part === "extras") return card;
  return mapStep(card, at, (step) => (step[part] ? { ...step, [part]: f(step[part]) } : step));
}

/** Turning a place on gives it an empty one; turning it off removes it, and
 *  with it the arrow the card was drawing into it. `to` is the row itself and
 *  is only ever emptied. */
export function toggleSlot(card: Card, at: Where, part: Exclude<Part, "extras">, on: boolean): Card {
  return mapStep(card, at, (step) =>
    part === "to"
      ? (on ? step : { ...step, to: newSlot() })
      : { ...step, [part]: on ? (step[part] ?? newSlot()) : null });
}

// -------------------------------------------------------------------- items

const isIcon = (item: Item): item is IconItem => item.kind === "icon";
const isCount = (item: Item): item is CountItem => item.kind === "count";
const isPlaceItem = (item: Item): item is PlaceItem => isIcon(item) || isCount(item);

type Bucket = { read: (step: Step) => Item[]; write: (step: Step, items: Item[]) => Step };

function bucketFor(part: Part): Bucket {
  if (part === "extras")
    return { read: (s) => s.extras, write: (s, items) => ({ ...s, extras: items }) };
  return {
    read: (s) => s[part]?.items ?? [],
    write: (s, items) => (s[part]
      ? { ...s, [part]: { ...s[part], items: items.filter(isPlaceItem) } }
      : { ...s, [part]: newSlot(items.filter(isPlaceItem)) }),
  };
}

/**
 * What a part will take. Dropping anything else on it is a no-op rather than
 * a silent conversion.
 *
 * Extras take anything — what the row *mentions*, "2 deer" included. A
 * number there counts what it stands beside, never villagers, so it carries
 * no figure.
 */
export function accepts(part: Part, item: Item): boolean {
  return part === "extras" || isPlaceItem(item);
}

const PARTS: Part[] = ["to", "via", "moveTo", "moveVia", "from", "extras"];

const spliced = (items: Item[], index: number, item: Item): Item[] => {
  const out = items.slice();
  out.splice(index < 0 ? out.length : Math.min(index, out.length), 0, item);
  return out;
};

/** Put `item` at a known position in a part; a negative index appends. */
function insertAt(card: Card, at: Where, item: Item, index: number): Card {
  const part = at.part ?? "to";
  if (!accepts(part, item)) return card;
  return mapStep(card, at, (step) => {
    const bucket = bucketFor(part);
    return bucket.write(step, spliced(bucket.read(step), index, item));
  });
}

/** Where `at.item` sits in its part. -1 when the part was named without an item. */
function indexOfItem(card: Card, at: Where): number {
  const step = findStep(card, at);
  if (!step || !at.item) return -1;
  for (const part of PARTS) {
    const items = bucketFor(part).read(step);
    const here = items.findIndex((i) => i.id === at.item);
    if (here >= 0) return here;
  }
  return -1;
}

/** The slot `at` points at: beside `at.item` on the side named, or the end of
 *  the part when no item was named. */
function landingIndex(card: Card, at: Where): number {
  const found = indexOfItem(card, at);
  return found < 0 ? -1 : found + (at.side === "after" ? 1 : 0);
}

/** Put `item` where `at` points. Right for something arriving from outside the
 *  card: nothing has moved, so the caret and the list still agree. */
export const addItem = (card: Card, at: Where, item: Item): Card =>
  insertAt(card, at, item, landingIndex(card, at));

const sameList = (a: Where, b: Where) =>
  a.step === b.step && (a.part ?? "to") === (b.part ?? "to");

function overItems(step: Step, itemId: string, f: (items: Item[], index: number) => Item[]): Step {
  for (const part of PARTS) {
    const bucket = bucketFor(part);
    const items = bucket.read(step);
    const index = items.findIndex((i) => i.id === itemId);
    if (index >= 0) return bucket.write(step, f(items, index));
  }
  return step;
}

export const updateItem = (card: Card, at: Where, patch: Partial<Item>): Card =>
  mapStep(card, at, (step) => overItems(step, at.item!, (items, index) => {
    const next = items.slice();
    next[index] = { ...items[index], ...patch } as Item;
    return next;
  }));

export const moveItem = (card: Card, at: Where, by: number): Card =>
  mapStep(card, at, (step) => overItems(step, at.item!, (items, index) => swap(items, index, index + by)));

export const dropItem = (card: Card, at: Where): Card =>
  mapStep(card, at, (step) => overItems(step, at.item!, (items, index) =>
    items.filter((_, i) => i !== index)));

/**
 * Move an item to where the caret said, within one place or across places,
 * rows.
 *
 * The landing slot is read off the card *before* the item is lifted out,
 * because that is the card the caret was drawn against. Lifting it out then
 * shifts everything after it left by one, so a landing slot beyond the item's
 * own position has to come back by one — without that, dragging something
 * rightwards along a place puts it down exactly where it started.
 */
export function relocate(card: Card, from: Where, to: Where): Card {
  if (from.item === to.item) return card;
  const found = findItem(card, from);
  if (!found || !accepts(to.part ?? "to", found)) return card;
  let index = landingIndex(card, to);
  const source = indexOfItem(card, from);
  if (index > 0 && source >= 0 && sameList(from, to) && source < index) index -= 1;
  return insertAt(dropItem(card, from), to, cloneItem(found), index);
}

export function findItem(card: Card, at: Where): Item | null {
  const step = findStep(card, at);
  if (!step) return null;
  for (const part of PARTS)
    for (const item of bucketFor(part).read(step))
      if (item.id === at.item) return item;
  return null;
}

export const findStep = (card: Card, at: Where): Step | null =>
  card.sections.find((s) => s.id === at.section)?.steps.find((s) => s.id === at.step) ?? null;

export const findSection = (card: Card, at: Where): Section | null =>
  card.sections.find((s) => s.id === at.section) ?? null;

export const slotIsEmpty = (slot: Slot | null): boolean =>
  !slot || (!slot.label && slot.items.length === 0);

/** The number a step wears. Sections that are not numbered have none, and a
 *  row count runs over the whole card rather than restarting per phase, the
 *  way the printed cards number them. Counting villagers, a row wears the sum
 *  of every work's figure once it is done — so a row that only moves
 *  villagers repeats the number above it, and one the card never put to work
 *  is not in it. */
export function numbering(card: Card): Record<string, number> {
  const out: Record<string, number> = {};
  const numbered = new Set(card.sections.filter((s) => s.numbered).flatMap((s) => s.steps.map((st) => st.id)));
  if (card.rowNumbers === "villagers") {
    tally(card, (step, villagers) => { if (numbered.has(step.id)) out[step.id] = villagers; });
    return out;
  }
  let n = 0;
  for (const section of card.sections)
    for (const step of section.steps)
      if (numbered.has(step.id)) out[step.id] = ++n;
  return out;
}

/** "All" in a source: everyone on that work leaves, however many it was. */
export const ALL = "All";

/**
 * The figure under each number: the villagers on **that number's work** —
 * sheep, hunt, berries, farms, the wood line, stragglers — in reading order.
 * Not one total over the card, and not one per resource either: "5" under
 * berries and "6" under sheep are both food, and the card is about who is on
 * which.
 *
 * A number in *source* is villagers **leaving**, so it comes off that work —
 * **All** empties it — and the same villagers arrive wherever they were moved
 * to, which therefore needs no number of its own. A number there anyway is
 * read as the arrivals, as a card written before the two halves did. Numbers
 * anywhere else are new villagers arriving. The moved half is counted first,
 * so a number on the left shows its work once the whole row is done.
 *
 * Counted up by default, and *set* wherever a number states its total
 * outright. A number whose place names no work — a tower, a militia, a tech —
 * gets nothing, which is better than a figure that means nothing.
 */
export function totals(card: Card): Record<string, string> {
  return tally(card);
}

function tally(card: Card, after?: (step: Step, villagers: number) => void): Record<string, string> {
  const out: Record<string, string> = {};
  const running: Partial<Record<Job, number>> = {};

  /** Notes one number and says how many villagers it moved. */
  const note = (item: CountItem, job: Job | null, leaving: boolean): number => {
    if (!job) return 0;
    const before = running[job] ?? 0;
    const stated = Number.parseInt(item.total, 10);
    const value = Number.parseInt(item.value, 10);
    const all = leaving && item.value.trim().toLowerCase() === ALL.toLowerCase();
    const moved = all ? before : Number.isFinite(value) ? value : 0;
    running[job] = Number.isFinite(stated) ? stated : before + (leaving ? -moved : moved);
    out[item.id] = String(running[job]);
    return moved;
  };
  const counts = (slot: Slot | null) => (slot ? slot.items.filter(isCount) : []);

  for (const section of card.sections)
    for (const step of section.steps) {
      const source = jobOf(step.from?.items ?? []);
      const moved = counts(step.from).reduce((sum, item) => sum + note(item, source, true), 0);
      for (const item of counts(step.moveVia)) note(item, jobOf(step.moveVia!.items), false);
      const landing = jobOf(step.moveTo?.items ?? []);
      if (counts(step.moveTo).length)
        for (const item of counts(step.moveTo)) note(item, landing, false);
      else if (landing && moved) running[landing] = (running[landing] ?? 0) + moved;
      for (const part of ["via", "to"] as const)
        for (const item of counts(step[part])) note(item, jobOf(step[part]!.items), false);
      after?.(step, Object.values(running).reduce((sum, n) => sum + (n ?? 0), 0));
    }
  return out;
}
