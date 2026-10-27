/**
 * Which kind of work an icon is about.
 *
 * The only game knowledge in the app, and it exists for one reason: the small
 * figure under a number is the villagers on *that work* — sheep, hunt,
 * berries, farms, the wood line, stragglers — so a number has to know which
 * one its place is naming. An icon that is not about gathering — a militia, a
 * tower, a tech — maps to nothing, and its number is drawn without a figure
 * rather than with a meaningless one.
 *
 * The mill and the camps that serve two kinds of work are deliberately absent:
 * a mill feeds berries and farms both, a mining camp gold and stone, so
 * neither can answer the question.
 */

import type { IconItem, PlaceItem } from "./card";

export type Job = "sheep" | "hunt" | "berries" | "farm" | "fish" | "food"
  | "wood" | "straggler" | "gold" | "stone";

const OF: Record<string, Job> = {
  "gaia-sheep": "sheep", "gaia-turkey": "sheep", "gaia-chicken": "sheep", "gaia-llama": "sheep",
  "gaia-boar": "hunt", "gaia-deer": "hunt",
  "gaia-berries": "berries",
  "building-farm": "farm",
  "gaia-fish": "fish", "unit-fishing_ship": "fish",
  "resource-food": "food",

  "resource-wood": "wood", "building-lumber_camp": "wood",
  "gaia-straggler": "straggler",

  "resource-gold": "gold",

  "resource-stone": "stone",
};

export const jobOfIcon = (item: IconItem): Job | null => OF[item.icon] ?? null;

/** The first icon in a place that names a job. A place holding a wood pile
 *  and a double-bit axe is about the wood line; the axe has no opinion. */
export function jobOf(items: PlaceItem[]): Job | null {
  for (const item of items)
    if (item.kind === "icon") {
      const found = jobOfIcon(item);
      if (found) return found;
    }
  return null;
}
