/**
 * What can be done to the selection, above the shelf. There is no panel of
 * fields: words and numbers are typed on the card itself, so this holds only
 * what has nothing on the card to click — a phase's colour, a copy of a row,
 * the card's running totals — and buttons for what the keys do.
 */

import type { ReactNode } from "react";
import type { Card, Where } from "../model/card";
import { TONES, addItem, addSection, findItem, findSection, findStep, mapSection, text } from "../model/card";
import { typing } from "../render/CardView";

type Props = {
  card: Card;
  selected: Where | null;
  apply: (f: (card: Card) => Card) => void;
  addRow: (at: Where) => void;
  duplicate: (at: Where) => void;
  /** The arrow keys: an item along its place, a row or a phase up and down. */
  nudge: (by: -1 | 1) => void;
  remove: () => void;
  /** Opens the selection's own words on the card for typing (F2). */
  typeSelection: () => void;
  type: (key: string) => void;
};

const KINDS = { icon: ["Icon", "Caption"], count: ["Number", "Number"], text: ["Note", "Words"] } as const;

export function Actions({ card, selected, apply, addRow, duplicate, nudge, remove, typeSelection, type }: Props) {
  const section = selected ? findSection(card, selected) : null;
  const step = selected?.step ? findStep(card, selected) : null;
  const item = selected?.item ? findItem(card, selected) : null;

  let title: string;
  let buttons: ReactNode;
  if (item && selected) {
    const [name, words] = KINDS[item.kind];
    title = name;
    buttons = (
      <>
        <button onClick={typeSelection} title="F2, or double-click it">{words}…</button>
        <button onClick={() => nudge(-1)} title="Move left (←)">←</button>
        <button onClick={() => nudge(1)} title="Move right (→)">→</button>
        <button className="danger" onClick={remove} title="Del">Delete</button>
      </>
    );
  } else if (step && selected) {
    const place = selected.part && selected.part !== "extras";
    title = place ? "Place" : "Row";
    buttons = (
      <>
        {place && <button onClick={typeSelection} title="F2">Words…</button>}
        <button title="A note in the row's extras" onClick={() => {
          const note = text("note");
          apply((c) => addItem(c, { ...selected, part: "extras", item: undefined }, note));
          type(typing("text", note.id));
        }}>+ Note</button>
        <button onClick={() => addRow(selected)} title="Enter">+ Row</button>
        <button onClick={() => duplicate(selected)} title="Ctrl D">Duplicate</button>
        <button onClick={() => nudge(-1)} title="Move up (↑)">↑</button>
        <button onClick={() => nudge(1)} title="Move down (↓)">↓</button>
        <button className="danger" onClick={remove} title="Del">Delete row</button>
      </>
    );
  } else if (section && selected) {
    title = "Phase";
    buttons = (
      <>
        <span className="tones">
          {TONES.map(([tone, label]) => (
            <button key={tone} title={label}
                    className={`tone phase--${tone}${section.tone === tone ? " on" : ""}`}
                    onClick={() => apply((c) => mapSection(c, section.id, (s) => ({ ...s, tone })))} />
          ))}
        </span>
        <button onClick={() => addRow({ section: section.id })} title="Enter">+ Row</button>
        <button onClick={() => nudge(-1)} title="Move up (↑)">↑</button>
        <button onClick={() => nudge(1)} title="Move down (↓)">↓</button>
        <button className="danger" onClick={remove} title="Del">Delete phase</button>
      </>
    );
  } else {
    title = "Card";
    buttons = (
      <>
        <button onClick={() => apply((c) => addSection(c, null))}>+ Phase</button>
        <label className="row tight">
          <input type="checkbox" checked={card.totals} style={{ width: "auto" }}
                 onChange={(e) => apply((c) => ({ ...c, totals: e.target.checked }))} />
          <span>Running totals</span>
        </label>
      </>
    );
  }

  return (
    <div className="actions">
      <h2 className="section">{title}</h2>
      <div className="row tight">{buttons}</div>
      <p className="hint">
        Double-click a title, a label, a number or an icon on the card to type. Del deletes,
        the arrows move, Enter adds a row and Ctrl D copies it.
      </p>
    </div>
  );
}
