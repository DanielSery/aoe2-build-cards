/**
 * The card itself — the only thing that ends up in the PNG.
 *
 * Editing affordances are all class names and handlers passed in from above,
 * so the same component renders the finished image: drop `edit` and what is
 * left is exactly what exports.
 */

import { useLayoutEffect, useRef } from "react";
import type { JSX } from "react";
import type { Card, Item, Part, Section, Slot, Step, Where } from "../model/card";
import { movesAnyone, newSlot, numbering, slotIsEmpty, totals } from "../model/card";
import { iconLabel, iconUrl } from "../icons";

export type Edit = {
  selected: Where | null;
  /** Something is being dragged, so the empty places are drawn to drop on. */
  dragging: boolean;
  select: (where: Where | null) => void;
  relocate: (from: Where, to: Where) => void;
  relocateStep: (from: Where, to: Where) => void;
  addIcon: (where: Where, key: string) => void;
  addNumber: (where: Where, value: string) => void;
  addRow: (where: Where) => void;
};

export const DRAG_ITEM = "application/x-aoe2-card-item";
export const DRAG_ROW = "application/x-aoe2-card-row";
export const DRAG_ICON = "application/x-aoe2-icon";
export const DRAG_NUMBER = "application/x-aoe2-number";
/** Both come off the shelf, so both are a copy rather than a move. */
const FROM_SHELF = [DRAG_ICON, DRAG_NUMBER];

const same = (a: Where | null, b: Where) =>
  !!a && a.section === b.section && a.step === b.step && a.item === b.item
  && (a.item !== undefined || a.part === b.part);

/** Which edge of an element the pointer is nearer. Halves rather than a narrow
 *  strip between items: the whole tile aims, so there is nothing to hit. */
const sideOf = (event: React.DragEvent, element: Element): "before" | "after" => {
  const box = element.getBoundingClientRect();
  return event.clientX < box.left + box.width / 2 ? "before" : "after";
};

/** One place to read a drop, because three things can be dragged onto the same
 *  target and only the type tells them apart.
 *
 *  Over an item the target is an *edge* — `data-drop` draws the caret there
 *  and the same reading decides where it lands, so what you saw is what you
 *  get. Over anything else it is the whole box, outlined. */
function dropHandlers(edit: Edit | undefined, where: Where, kinds: string[]) {
  if (!edit) return {};
  const mine = (event: React.DragEvent) => kinds.find((k) => event.dataTransfer.types.includes(k));
  const aim = (event: React.DragEvent): Where =>
    (where.item ? { ...where, side: sideOf(event, event.currentTarget) } : where);
  const clear = (element: HTMLElement) => {
    element.classList.remove("is-over");
    element.removeAttribute("data-drop");
  };
  return {
    onDragOver: (event: React.DragEvent) => {
      const kind = mine(event);
      if (!kind) return;
      event.preventDefault();
      event.stopPropagation();
      // Has to match the `effectAllowed` the drag started with, or the browser
      // refuses the drop and nothing says why.
      event.dataTransfer.dropEffect = FROM_SHELF.includes(kind) ? "copy" : "move";
      const node = event.currentTarget as HTMLElement;
      if (where.item) node.dataset.drop = sideOf(event, node);
      else node.classList.add("is-over");
    },
    onDragLeave: (event: React.DragEvent) => clear(event.currentTarget as HTMLElement),
    onDrop: (event: React.DragEvent) => {
      const kind = mine(event);
      if (!kind) return;
      event.preventDefault();
      event.stopPropagation();
      const landing = aim(event);
      clear(event.currentTarget as HTMLElement);
      const payload = event.dataTransfer.getData(kind);
      if (kind === DRAG_ICON) edit.addIcon(landing, payload);
      else if (kind === DRAG_NUMBER) edit.addNumber(landing, payload);
      else if (kind === DRAG_ROW) edit.relocateStep(JSON.parse(payload) as Where, landing);
      else edit.relocate(JSON.parse(payload) as Where, landing);
    },
  };
}

function itemHandlers(edit: Edit | undefined, where: Where) {
  if (!edit) return {};
  return {
    draggable: true,
    onClick: (event: React.MouseEvent) => { event.stopPropagation(); edit.select(where); },
    onDragStart: (event: React.DragEvent) => {
      event.stopPropagation();
      event.dataTransfer.setData(DRAG_ITEM, JSON.stringify(where));
      event.dataTransfer.effectAllowed = "move";
    },
    ...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF]),
  };
}

function ItemView({ item, where, edit, total }: {
  item: Item; where: Where; edit?: Edit; total?: string;
}) {
  const classes = ["item", `item--${item.kind}`];
  if (same(edit?.selected ?? null, where)) classes.push("is-selected");
  const common = { className: classes.join(" "), ...itemHandlers(edit, where) };

  switch (item.kind) {
    case "icon":
      return (
        <span {...common} title={iconLabel(item.icon)}>
          {/* Out of flow on purpose: a caption must not make its row taller
              than the rows around it, or the icons stop lining up. */}
          {item.caption && <span className="cap">{item.caption}</span>}
          <span className="tile">
            <img src={iconUrl(item.icon)} alt={iconLabel(item.icon)} draggable={false} />
          </span>
        </span>
      );
    case "count": {
      // A word in a number's place — "All" — carries no figure: under a word
      // it reads as a count of the word.
      const word = /[a-z]/i.test(item.value);
      return (
        <span {...common}>
          <span className={`countbox${word ? " countbox--word" : ""}`}>
            <b>{item.value}</b>
            {total !== undefined && !word && <i>{total}</i>}
          </span>
        </span>
      );
    }
    case "text":
      return <span {...common}><span className="phrase">{item.text}</span></span>;
  }
}

/** One of the places. */
function SlotView({ slot, part, hint, step, section, edit, sums }: {
  slot: Slot; part: Part; hint: string; step: Step; section: Section;
  edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id, part };
  const classes = ["slot", `slot--${part}`];
  if (same(edit?.selected ?? null, where)) classes.push("is-selected");
  return (
    <span className={classes.join(" ")} data-hint={hint}
          onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
          {...dropHandlers(edit, where, [DRAG_ITEM, ...FROM_SHELF])}>
      {slot.items.map((item) => (
        <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]}
                  where={{ ...where, item: item.id }} />
      ))}
      {slot.label && <span className="phrase">{slot.label}</span>}
    </span>
  );
}

/**
 * Whether an empty place is drawn. Only while something is being dragged — it
 * is somewhere to drop — or while it is the selection, so a click on the
 * shelf has somewhere visible to land; and the end of a selected row that has
 * nothing yet, or a new row would be an empty strip.
 */
function offered(edit: Edit | undefined, step: Step, section: Section, part: Part): boolean {
  if (!edit) return false;
  if (edit.dragging || same(edit.selected, { section: section.id, step: step.id, part })) return true;
  return part === "to" && same(edit.selected, { section: section.id, step: step.id });
}

function Chain({ places, step, section, edit, sums }: {
  places: [Part, Slot | null, string][]; step: Step; section: Section;
  edit?: Edit; sums: Record<string, string>;
}) {
  const shown = places.filter(([part, slot]) => !slotIsEmpty(slot) || offered(edit, step, section, part));
  return (
    <span className="chain">
      {shown.map(([part, slot, hint], index) => (
        <span className="link" key={part}>
          {index > 0 && <span className="arrow">←</span>}
          <SlotView slot={slot ?? newSlot()} part={part} hint={hint} step={step}
                    section={section} edit={edit} sums={sums} />
        </span>
      ))}
    </span>
  );
}

/** A row: the new villagers, the ones moved off other work, and what the row
 *  only mentions — three columns. */
function StepRow({ step, section, number, edit, sums }: {
  step: Step; section: Section; number?: number;
  edit?: Edit; sums: Record<string, string>;
}) {
  const where: Where = { section: section.id, step: step.id };
  const selected = same(edit?.selected ?? null, where);
  const extrasAt: Where = { ...where, part: "extras" };
  const moves = movesAnyone(step);
  const mentions = step.extras.length > 0;
  const columns = [moves && "step--moves", mentions && "step--extras", selected && "is-selected"];

  return (
    <div className={["step", ...columns].filter(Boolean).join(" ")}
         onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
         {...dropHandlers(edit, where, [DRAG_ROW])}>
      {edit && (
        <span className="grip" title="Drag to move this row" draggable
              onDragStart={(event) => {
                event.stopPropagation();
                event.dataTransfer.setData(DRAG_ROW, JSON.stringify(where));
                event.dataTransfer.effectAllowed = "move";
              }}>⠿</span>
      )}
      {section.numbered && <span className="step-no">{number}</span>}
      <span className="column column--new">
        <Chain step={step} section={section} edit={edit} sums={sums}
               places={[["to", step.to, "end"], ["via", step.via, "before"]]} />
      </span>
      <span className="column column--move">
        <Chain step={step} section={section} edit={edit} sums={sums}
               places={[["moveTo", step.moveTo, "moved to"], ["moveVia", step.moveVia, "before"],
                        ["from", step.from, "source"]]} />
      </span>
      {(mentions || offered(edit, step, section, "extras")) &&
        <span className={`extras${same(edit?.selected ?? null, extrasAt) ? " is-selected" : ""}`}
            data-hint="extras"
            onClick={edit && ((event) => { event.stopPropagation(); edit.select(extrasAt); })}
            {...dropHandlers(edit, extrasAt, [DRAG_ITEM, DRAG_ICON, DRAG_NUMBER])}>
        {step.extras.map((item) => (
          <ItemView key={item.id} item={item} edit={edit} total={sums[item.id]}
                    where={{ ...extrasAt, item: item.id }} />
        ))}
      </span>}
    </div>
  );
}

/**
 * The moves line up down the card: every row with one has its new villagers'
 * column as wide as the widest such column on the card. A row with no move is
 * left out of the measure — an age-up row's long label would otherwise push
 * every move on the card to the right.
 *
 * Measured rather than laid out as a grid, because the rows sit in separate
 * phase boxes; set as a variable on the card itself, so the off-screen copy
 * the PNG is taken from measures and carries its own.
 */
function useColumns(card: Card) {
  const node = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const root = node.current;
    if (!root) return;
    const widths = [...root.querySelectorAll<HTMLElement>(".step--moves > .column--new > .chain")]
      .map((chain) => chain.offsetWidth);
    root.style.setProperty("--new-column", widths.length ? `${Math.max(...widths)}px` : "auto");
  }, [card]);
  return node;
}

export function CardView({ card, edit }: { card: Card; edit?: Edit }): JSX.Element {
  const numbers = numbering(card);
  const sums = card.totals ? totals(card) : {};
  const node = useColumns(card);
  return (
    <div ref={node} className={`card${edit ? " card--edit" : ""}`}
         onClick={edit && (() => edit.select(null))}>
      <header className="card-head">
        <h1>{card.title || card.name}</h1>
        {card.subtitle && <p>{card.subtitle}</p>}
      </header>
      {card.sections.map((section) => {
        const where: Where = { section: section.id };
        const selected = same(edit?.selected ?? null, where);
        return (
          <section key={section.id}
                   className={`phase phase--${section.tone}${selected ? " is-selected" : ""}`}
                   onClick={edit && ((event) => { event.stopPropagation(); edit.select(where); })}
                   {...dropHandlers(edit, { section: section.id }, [DRAG_ROW])}>
            <div className="phase-label">{section.label}</div>
            <div className="phase-steps">
              {section.steps.map((step) => (
                <StepRow key={step.id} step={step} section={section} edit={edit} sums={sums}
                         number={numbers[step.id]} />
              ))}
              {edit && (
                <button className="add-row" title="Add a row (Enter)"
                        onClick={(event) => {
                          event.stopPropagation();
                          edit.addRow({ section: section.id });
                        }}>+ row</button>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
