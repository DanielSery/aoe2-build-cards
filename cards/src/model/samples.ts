/**
 * The card the editor opens with, so the format explains itself.
 *
 * A transcription of a well-known men-at-arms opening rather than advice: it
 * is here because it uses all three columns of a row — new villagers and who
 * joined them, villagers moved off other work, extras — something done on the
 * way, a caption, a labelled row, numbers that are counted up, and All.
 */

import type { Card, Step } from "./card";
import { ALL, count, icon, newSlot, newStep } from "./card";

const row = (step: Step, rest: Partial<Step>): Step => ({ ...step, ...rest });

export function sampleCard(): Card {
  return {
    id: crypto.randomUUID(),
    name: "MAA + Tower",
    title: "MAA + Tower",
    subtitle: "18 pop + loom",
    totals: true,
    updated: Date.now(),
    sections: [
      {
        id: crypto.randomUUID(),
        label: "Dark Age",
        tone: "dark",
        steps: [
          row(newStep(newSlot([count("6"), icon("gaia-sheep")])), {
            extras: [icon("building-house"), icon("building-house")],
          }),
          row(newStep(newSlot([count("4"), icon("resource-wood"), icon("tech-double-bit-axe")])), {
            extras: [icon("gaia-deer"), icon("gaia-deer"), icon("gaia-boar")],
          }),
          // Twelve to the hunt: six new, and all six off the sheep with them.
          row(newStep(newSlot([count("12"), icon("gaia-boar")])), {
            toFrom: newSlot([count(ALL), icon("gaia-sheep")]),
          }),
          row(newStep(newSlot([icon("building-barracks")])), {
            moveTo: newSlot([icon("resource-wood")]),
            from: newSlot([icon("building-house")]),
          }),
        ],
      },
      {
        id: crypto.randomUUID(),
        label: "Going Feudal",
        tone: "transition",
        steps: [
          row(newStep(), {
            moveTo: newSlot([count("3"), icon("resource-stone"), { ...icon("resource-gold"), caption: "50" }]),
            from: newSlot([icon("gaia-boar")]),
          }),
          // A tower names no work: the five come off the hunt and into no figure.
          row(newStep(), {
            moveTo: newSlot([count("5"), icon("building-watch_tower")]),
            from: newSlot([icon("gaia-boar")]),
          }),
          newStep(newSlot([count("3"), icon("unit-militia")])),
        ],
      },
      {
        id: crypto.randomUUID(),
        label: "Feudal Age",
        tone: "feudal",
        steps: [
          newStep(newSlot([icon("unit-man_at_arms")], "Make MAA")),
          newStep(newSlot([icon("tech-loom")], "Research Loom")),
        ],
      },
    ],
  };
}
