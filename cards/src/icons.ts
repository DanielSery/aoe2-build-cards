/**
 * The icon set, and the one place that knows where the files are.
 *
 * `icons.generated.ts` is written by tools/fetch_card_icons.py and lists only
 * the keys that actually downloaded, so a missing image is a missing entry
 * rather than a broken tile.
 */

import { ICONS, ICON_CATEGORIES } from "./icons.generated";
import type { IconEntry } from "./icons.generated";

export type { IconEntry };
export { ICONS, ICON_CATEGORIES };

const DIR = "./icons/aoe2";

export const iconUrl = (key: string) => `${DIR}/${key}.png`;

const BY_KEY = new Map(ICONS.map((entry) => [entry.key, entry]));

export const iconLabel = (key: string) => BY_KEY.get(key)?.label ?? key;

/** The label plus the age it is available in, for the shelf. The card's own
 *  tiles use `iconLabel`: what age a building unlocks in is a thing you want
 *  while picking it, not a thing the finished picture says. */
export function iconTitle(key: string): string {
  const entry = BY_KEY.get(key);
  if (!entry) return key;
  return entry.age ? `${entry.label} — ${entry.age}` : entry.label;
}

/** Every word of the query has to appear somewhere in the label or the key,
 *  so "gold camp" finds the mining camp without ordering the words. */
export function searchIcons(query: string, category: string | null): IconEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return ICONS.filter((entry) => {
    if (category && entry.category !== category) return false;
    const haystack = `${entry.label} ${entry.key}`.toLowerCase().replace(/[-_]/g, " ");
    return words.every((word) => haystack.includes(word));
  });
}
