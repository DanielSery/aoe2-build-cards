/**
 * Where saved cards live: this browser, and nowhere else.
 *
 * There is no server in this app, so a card is only as durable as the profile
 * it was written in — which is why export and import are first-class rather
 * than a convenience.
 */

import type { Card } from "./card";
import { normaliseCard } from "./migrate";

const KEY = "aoe2-build-cards/v1";

export type Stored = { cards: Card[] };

/** Everything read back goes through `normaliseCard`: a card saved by an
 *  older version is drawn, not validated, so one missing field is a blank
 *  page rather than an error. */
export function load(): Card[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Stored;
    return Array.isArray(parsed.cards) ? read(parsed.cards) : [];
  } catch {
    return [];
  }
}

export const read = (values: unknown[]): Card[] =>
  values.map(normaliseCard).filter((card): card is Card => card !== null);

export function save(cards: Card[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ cards } satisfies Stored));
  } catch {
    // A full or blocked store must not take the editor down with it; the card
    // on screen is still whole, and export is still available.
  }
}

export function download(name: string, data: Blob): void {
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export const fileName = (name: string, extension: string) =>
  `${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "card"}.${extension}`;
