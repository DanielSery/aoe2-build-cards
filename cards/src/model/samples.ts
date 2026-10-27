/**
 * The card the editor opens with, so the format explains itself.
 *
 * A transcription of a well-known men-at-arms opening rather than advice: it
 * is here because it uses all three places on a row, a caption, a hunt box, a
 * labelled row, numbers that are counted up and one that states its total
 * outright.
 */

import type { Card, Step } from "./card";
import { box, count, icon, newSlot, newStep } from "./card";

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
            extras: [box([icon("gaia-deer"), icon("gaia-deer"), icon("gaia-boar")])],
          }),
          // The one number the card states outright: twelve on food, not the
          // six on sheep plus twelve more.
          row(newStep(newSlot([count("12", "12"), icon("gaia-boar")])), {
            from: newSlot([icon("gaia-sheep")]),
          }),
          row(newStep(newSlot([icon("resource-wood")])), {
            from: newSlot([icon("building-house")]),
            extras: [icon("building-barracks"), icon("building-house"), icon("resource-wood")],
          }),
        ],
      },
      {
        id: crypto.randomUUID(),
        label: "Going Feudal",
        tone: "transition",
        numbered: true,
        steps: [
          row(newStep(newSlot([count("3"), icon("resource-stone")])), {
            via: newSlot([count("3"), { ...icon("resource-gold"), caption: "50" }]),
            from: newSlot([icon("gaia-boar")]),
          }),
          // A tower and a militia name no resource, so these two numbers carry
          // no total at all rather than a meaningless one.
          row(newStep(newSlot([count("5"), icon("building-watch_tower")])), {
            from: newSlot([icon("gaia-boar")]),
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
