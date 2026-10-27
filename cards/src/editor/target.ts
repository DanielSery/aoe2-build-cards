import type { Card, Part, Where } from "../model/card";
import { SLOTS } from "../model/card";

const NAMES: Record<Part, string> = {
  extras: "Extras", to: "Goes to", toFrom: "Joined from", moveTo: "Moved to", from: "Source",
};

/** What the shelf says it is adding to. */
export const partName = (part: Part | undefined): string =>
  NAMES[part ?? "to"] ?? SLOTS[0][1];

/**
 * Where a newly added icon lands.
 *
 * Selection is the aim: a selected place on a row takes it, and with nothing
 * selected it goes where a row starts — the last row's "ends up on". That is what makes "click an icon" a usable way to
 * build a card from empty.
 */
export function appendTarget(card: Card, selected: Where | null): Where | null {
  const section = selected
    ? card.sections.find((s) => s.id === selected.section)
    : card.sections.at(-1);
  if (!section) return null;

  const step = selected?.step
    ? section.steps.find((s) => s.id === selected.step)
    : section.steps.at(-1);
  if (!step) return null;

  return { section: section.id, step: step.id, part: selected?.part ?? "to" };
}
