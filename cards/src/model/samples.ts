/**
 * The card the editor opens with, so the format explains itself.
 *
 * A transcription of a well-known men-at-arms opening rather than advice: it
 * is here because it uses both halves of a row — new villagers, and villagers
 * moved off other work — a caption, a labelled row, numbers that
 * are counted up, and All.
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
    rowNumbers: "steps",
    updated: Date.now(),
    sections: [
      {
        id: crypto.randomUUID(),
        label: "Dark Age",
        tone: "dark",
        numbered: true,
        steps: [
          row(newStep(newSlot([count("6"), icon("gaia-sheep")])), {
            extras: [icon("building-house"), icon("building-house")],
          }),
          row(newStep(newSlot([count("4"), icon("resource-wood"), icon("tech-double-bit-axe")])), {
            extras: [icon("gaia-deer"), icon("gaia-deer"), icon("gaia-boar")],
          }),
          // Twelve on the hunt: all six off the sheep, and six new.
          row(newStep(newSlot([count("6"), icon("gaia-boar")])), {
            moveTo: newSlot([icon("gaia-boar")]),
            from: newSlot([count(ALL), icon("gaia-sheep")]),
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
        numbered: true,
        steps: [
          row(newStep(), {
            moveTo: newSlot([icon("resource-stone")]),
            moveVia: newSlot([{ ...icon("resource-gold"), caption: "50" }]),
            from: newSlot([count("3"), icon("gaia-boar")]),
          }),
          // A tower names no work: the five come off the hunt and into no figure.
          row(newStep(), {
            moveTo: newSlot([icon("building-watch_tower")]),
            from: newSlot([count("5"), icon("gaia-boar")]),
          }),
          newStep(newSlot([count("3"), icon("unit-militia")])),
        ],
      },
      {
        id: crypto.randomUUID(),
        label: "Feudal Age",
        tone: "feudal",
        numbered: false,
        steps: [
          newStep(newSlot([icon("unit-man_at_arms")], "Make MAA")),
          newStep(newSlot([icon("tech-loom")], "Research Loom")),
        ],
      },
    ],
  };
}
